"""JARVIS COWORK — o programador do JARVIS (05/10/2026).

O dono escolhe uma pasta (o "projeto aberto") e pede por voz ou por escrito:
"faz um jogo da cobrinha", "a cor do botao esta errada", "deu erro ao abrir".

Um pedido, do comeco ao fim:
  1. Se o projeto ja roda, testa como ele esta AGORA (erros + foto da tela), para
     o Codex ver o que o dono esta vendo.
  2. Compacta a pasta (sem node_modules, .git...) e manda para o Codex da VPS
     (jarvis-cowork.js), que trabalha numa copia e devolve SO o que mudou.
  3. Aplica na pasta, guardando antes um ponto de "desfaz".
  4. Roda o projeto escondido (pagina no navegador sem janela, ou o programa),
     le os erros, tira a foto da tela.
  5. Se achou erro (ou foi um trabalho grande), manda uma rodada de verificacao
     com o relatorio e a foto; o Codex corrige ou responde OK. Ate 3 rodadas.
  6. Abre o resultado para o dono ver e devolve a frase para ser falada.

Nada disto toca no resto do JARVIS: roda numa thread propria, fala com a VPS
por mensagens proprias (cw_*) e so escreve dentro da pasta do projeto.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG = BASE_DIR / "config" / "cowork.json"

PASTA_INTERNA = ".jarvis_cowork"          # desfaz e historico, dentro do projeto
ARQ_COMO_RODAR = ".jarvis-cowork.json"    # o Codex escreve como rodar o projeto

# Nunca sobem (pesadas, geradas por ferramenta ou do proprio Cowork).
_IGNORAR_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env",
    PASTA_INTERNA, ".pytest_cache", ".mypy_cache", ".idea", ".vs", ".next", ".nuxt",
    ".cache", ".parcel-cache", ".turbo", "dist", "build", "out", "bin", "obj",
    "target", ".gradle", ".dart_tool", "Pods", ".expo",
}
_IGNORAR_ARQ = {"thumbs.db", "desktop.ini", ".ds_store"}
# Codigo e texto sobem sempre; o resto (imagem, som...) so se for pequeno.
_TEXTO = {
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".js", ".mjs", ".cjs", ".jsx",
    ".ts", ".tsx", ".vue", ".svelte", ".json", ".jsonc", ".md", ".txt", ".py", ".pyw",
    ".java", ".kt", ".kts", ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".go", ".rs",
    ".rb", ".php", ".swift", ".dart", ".lua", ".sql", ".sh", ".bat", ".cmd", ".ps1",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".svg", ".csv", ".env.example",
    ".gitignore", ".editorconfig", ".gd", ".tscn", ".godot", ".shader", ".glsl",
}
_MAX_ZIP = 38 * 1024 * 1024
_MAX_ARQUIVOS = 6000
_MAX_BINARIO = 1024 * 1024
_RODADAS_EXTRAS = 3
_CONTINUACOES_MAX = 4                # rodadas automaticas extras enquanto faltar parte do pedido
# Luna no MAX (16/10/2026) demora mais: a VPS corta em 60 min para quem manda
# o prazo (cw_submit.prazo_s); folga para fila e envio.
_TIMEOUT_RODADA = 65 * 60.0
_MAX_PONTOS = 30
_MAX_DESCRICAO = 7600                # a VPS recusa pedido com mais de 8000 letras
_MARCA_BAT = "REM INICIAR.bat feito pelo JARVIS Cowork"


class CoworkCancelado(Exception):
    pass


# O modelo as vezes conclui que "nao tem acesso" sem nem tentar (pasta vazia).
_ACHOU_QUE_NAO_PODIA = re.compile(
    r"somente leitura|read[- ]?only|n[aã]o consegui acessar|sem (?:acesso|permiss)|"
    r"permiss[aã]o de escrita|acesso de escrita|n[aã]o (?:tenho|tive) (?:acesso|permiss)|"
    r"bloquead[ao] pelo ambiente|(?:grava[cç][aã]o|escrita)[^.]{0,40}bloquead", re.I)

# PROJETO PELA METADE (16/10/2026): o Codex do servidor (esforco baixo) entregou
# o "Operacao Omega" como "estrutura inicial" -- 490 linhas e um CHECKLIST.md
# cheio de [ ]. O dono teve de pedir "continua" a mao. Agora, enquanto o proprio
# Codex disser que falta coisa, o PC manda continuar sozinho.
_ITEM_ABERTO = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*\[\s\]\s*(.+?)\s*$", re.M)
# O que so o PC faz (testar, gerar o .exe): nao vale rodada de continuacao.
_SO_NO_PC = re.compile(
    r"\.exe\b|execut[aá]vel|empacot|build_apps|pyinstaller|instalador|\btest|valida|comprovad|"
    r"garantid|ambiente|python 3|instalad|no pc do cliente|no windows real", re.I)
_ARQS_PENDENCIA = ("checklist.md", "todo.md", "pendencias.md", "pendente.md", "faltando.md")
# Frases do Codex sobre o AMBIENTE DELE ("Python nao esta disponivel neste
# ambiente", "nao consegui iniciar o jogo"): o PC testa logo depois, entao isso
# so confunde o dono -- ele ouviu e achou que estava quebrado.
_FRASE_DO_AMBIENTE = re.compile(
    r"neste ambiente|nesse ambiente|deste ambiente|no ambiente d[oe]|"
    r"n[aã]o (?:est[aá]|estava|estavam|est[aã]o) dispon[ií]ve|n[aã]o (?:tem|tinha|h[aá]) (?:o )?python|"
    r"python (?:e [^.]{0,40})?n[aã]o (?:est[aá]|estava|existe|foi encontrad)|sem python|"
    r"n[aã]o (?:consegui|pude|foi poss[ií]vel) (?:o )?(?:testar|rodar|executar|iniciar|abrir|validar|"
    r"checar|conferir|compilar|verificar|confirmar)|ficaram? pendentes? porque|"
    r"(?:teste|checagem|verifica[cç][aã]o)[^.]{0,60}pendente|pelo ambiente|ambiente (?:bloque|imped|nao permit)|"
    r"(?:grava[cç][aã]o|escrita|altera[cç][oõ]es|arquivos?)[^.]{0,50}bloquead", re.I)
# "faz um jogo...", "cria um editor...": pedido de projeto NOVO.
_RE_CRIAR = re.compile(
    r"\b(?:cria|crie|criar|faz|faca|fazer|monta|monte|montar|desenvolve|desenvolva|gera|gere|programa|"
    r"programe)\b.{0,80}?\b(?:jogo|game|app|aplicativo|sistema|site|programa|painel|editor|calculadora|"
    r"loja|agenda|relogio|projeto|ferramenta|bot)\b|\bdo zero\b")
_RE_CONTINUA = re.compile(
    r"^\W*(?:(?:pode|por favor|agora|entao|jarvis)\W+)*(?:continua|continue|continuar|termina|termine|"
    r"terminar|completa|complete|completar|finaliza|finalize|finalizar)\b")


def _agora() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _sem_acento(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _dentro(pasta: Path, alvo: Path) -> bool:
    try:
        alvo.resolve().relative_to(pasta.resolve())
        return True
    except Exception:
        return False


def _nome_do_zip(info: zipfile.ZipInfo) -> str:
    """Nome do arquivo DENTRO do zip, com acento certo.

    O tar da VPS gravava nomes na codificacao antiga do Windows (cp850) sem a
    marca de UTF-8: "acao.txt" com cedilha chegava embaralhado. Sem a marca,
    o Python le como cp437; aqui volta aos bytes e tenta UTF-8, depois cp850."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        bruto = info.filename.encode("cp437")
    except UnicodeEncodeError:
        return info.filename
    for cod in ("utf-8", "cp850"):
        try:
            return bruto.decode(cod)
        except UnicodeDecodeError:
            continue
    return info.filename


def _nome_seguro(rel: str) -> str | None:
    """Caminho relativo vindo da VPS: so aceita o que fica DENTRO do projeto."""
    r = str(rel or "").replace("\\", "/").strip()
    while r.startswith("./"):
        r = r[2:]
    if not r or r.endswith("/") or r.startswith("/") or re.match(r"^[A-Za-z]:", r):
        return None
    partes = [p for p in r.split("/") if p not in ("", ".")]
    if not partes or any(p == ".." for p in partes):
        return None
    if partes[0] in (PASTA_INTERNA, "_jarvis_cowork") or partes[0] in {".git"}:
        return None
    return "/".join(partes)


class Cowork:
    """Uma sessao de Cowork por JARVIS (um projeto aberto de cada vez)."""

    def __init__(self):
        self.pasta: Path | None = None
        self._ocupado = False
        self._trava = threading.Lock()
        self._cancelar = threading.Event()
        self._ouvintes: list = []
        self.etapa = ""
        self.linhas: list[str] = []
        self._servidor = None
        self._servidor_pasta: Path | None = None
        self._servidor_porta = 0
        self._processo = None            # o programa aberto para o dono ver
        self._ultimo_teste: dict | None = None
        self._ultimo_teste_em = 0.0
        self._janela_app = None          # janela propria do projeto web (Edge/Chrome --app)
        self._carregar_config()

    # ── estado para a tela ──────────────────────────────────────────────────
    def ouvir(self, funcao) -> None:
        if funcao not in self._ouvintes:
            self._ouvintes.append(funcao)

    def estado(self) -> dict:
        return {
            "pasta": str(self.pasta) if self.pasta else "",
            "nome": self.pasta.name if self.pasta else "",
            "ocupado": self._ocupado,
            "etapa": self.etapa,
            "linhas": list(self.linhas[-5:]),
            "pode_desfazer": bool(self._pontos()) if self.pasta else False,
        }

    def _avisar(self, etapa: str | None = None, linha: str | None = None) -> None:
        if etapa is not None:
            self.etapa = etapa
            if etapa:
                self.linhas.append(etapa)
        if linha:
            linha = str(linha).strip()[:150]
            if linha and (not self.linhas or self.linhas[-1] != linha):
                self.linhas.append(linha)
        self.linhas = self.linhas[-30:]
        est = self.estado()
        for f in list(self._ouvintes):
            try:
                f(est)
            except Exception:
                pass

    def _checar_cancelado(self) -> None:
        if self._cancelar.is_set():
            raise CoworkCancelado()

    # ── configuracao (lembra o ultimo projeto) ──────────────────────────────
    def _carregar_config(self) -> None:
        try:
            dados = json.loads(_CONFIG.read_text(encoding="utf-8"))
            p = Path(str(dados.get("pasta") or ""))
            if str(p) and p.is_dir() and not self._proibida(p):
                self.pasta = p
        except Exception:
            pass

    def _salvar_config(self) -> None:
        try:
            _CONFIG.parent.mkdir(parents=True, exist_ok=True)
            recentes = []
            try:
                recentes = json.loads(_CONFIG.read_text(encoding="utf-8")).get("recentes") or []
            except Exception:
                pass
            if self.pasta:
                recentes = [str(self.pasta)] + [r for r in recentes if r != str(self.pasta)]
            _CONFIG.write_text(json.dumps({"pasta": str(self.pasta or ""), "recentes": recentes[:10]},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass

    # ── escolher / criar o projeto ──────────────────────────────────────────
    @staticmethod
    def _proibida(p: Path) -> str:
        """Pastas que NAO podem virar projeto (o Codex mexeria em tudo)."""
        try:
            r = p.resolve()
        except Exception:
            return "pasta invalida"
        casa = Path.home().resolve()
        if r.parent == r:
            return "a raiz do disco"
        largas = {casa, casa / "Desktop", casa / "Documents", casa / "Downloads",
                  casa / "Pictures", casa / "Music", casa / "Videos", casa / "OneDrive",
                  casa / "OneDrive" / "Desktop", casa / "OneDrive" / "Documentos",
                  casa / "OneDrive" / "Documents", casa / "Área de Trabalho"}
        if r in {x.resolve() if x.exists() else x for x in largas}:
            return "uma pasta pessoal inteira"
        baixo = str(r).lower().replace("\\", "/")
        for proibido in ("c:/windows", "c:/program files", "c:/programdata",
                         "/appdata/local/microsoft", "/appdata/roaming/microsoft"):
            if baixo.startswith(proibido) or proibido in baixo and proibido.startswith("/"):
                return "uma pasta do sistema"
        try:
            r.relative_to(BASE_DIR.resolve())
            return "a pasta do próprio JARVIS"
        except Exception:
            pass
        return ""

    def abrir_pasta(self, caminho, criar: bool = False) -> str:
        if self._ocupado:
            return "Espera eu terminar o trabalho atual do Cowork antes de trocar de projeto."
        p = Path(str(caminho or "").strip().strip('"').strip("'")).expanduser()
        if criar and not p.exists():
            try:
                p.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                return f"Não consegui criar a pasta: {str(exc)[:80]}"
        if not p.is_dir():
            return "Não achei essa pasta."
        motivo = self._proibida(p)
        if motivo:
            return (f"Essa pasta é {motivo}. Para o Cowork, escolha ou crie uma pasta "
                    "só do projeto (por exemplo, dentro de Documentos).")
        self._parar_processo()
        self.pasta = p.resolve()
        self._ultimo_teste = None
        self.linhas = []
        self._salvar_config()
        self._avisar(etapa="")
        return f"Cowork aberto na pasta {self.pasta.name}. Pode pedir o que quer que eu faça nela."

    def fechar_janela(self) -> str:
        """Fecha a janela/programa do projeto que o Cowork abriu."""
        self._parar_processo()
        return "Fechei a janela do projeto."

    def fechar(self) -> str:
        if self._ocupado:
            return "Estou no meio de um trabalho; diga parar o cowork antes."
        self._parar_processo()
        self._parar_servidor()
        self.pasta = None
        self._salvar_config()
        self._avisar(etapa="")
        return "Fechei o projeto do Cowork."

    @staticmethod
    def pasta_de_projetos() -> Path:
        docs = Path.home() / "Documents"
        if not docs.is_dir():
            docs = Path.home()
        return docs / "JARVIS Cowork"

    def novo_projeto(self, pedido: str) -> Path:
        """Pasta nova para um pedido sem projeto aberto ("faz um jogo...")."""
        t = _sem_acento(pedido).lower()
        m = re.search(r"\b(jogo|game|app|aplicativo|sistema|site|programa|painel|calculadora|loja|agenda)"
                      r"(?:\s+(?:de|da|do|dos|das|para|pra))?\s+([a-z0-9 ]{2,30})", t)
        base = f"{m.group(1)} {m.group(2)}" if m else "Projeto"
        base = re.sub(r"\b(um|uma|o|a|os|as|pra|para|mim|me|bem|bonito|bonita|simples|novo|nova)\b", " ", base)
        nome = re.sub(r"[^A-Za-z0-9 ]", "", base).strip().title() or "Projeto"
        nome = re.sub(r"\s+", " ", nome)[:40]
        raiz = self.pasta_de_projetos()
        alvo = raiz / nome
        n = 2
        while alvo.exists():
            alvo = raiz / f"{nome} {n}"
            n += 1
        alvo.mkdir(parents=True, exist_ok=True)
        return alvo

    # ── empacotar a pasta ───────────────────────────────────────────────────
    def _empacotar(self, extras: dict) -> bytes:
        assert self.pasta is not None
        raiz = self.pasta
        buf = io.BytesIO()
        grandes: list[str] = []
        total = 0
        qtd = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for dirpath, dirnames, filenames in os.walk(raiz):
                self._checar_cancelado()
                dirnames[:] = sorted(d for d in dirnames
                                     if d not in _IGNORAR_DIRS
                                     and not os.path.islink(os.path.join(dirpath, d)))
                for nome in sorted(filenames):
                    if nome.lower() in _IGNORAR_ARQ:
                        continue
                    cheio = Path(dirpath) / nome
                    if cheio.is_symlink() or not cheio.is_file():
                        continue
                    rel = cheio.relative_to(raiz).as_posix()
                    if rel.lower().startswith("_jarvis_cowork/"):
                        continue
                    try:
                        tam = cheio.stat().st_size
                    except OSError:
                        continue
                    qtd += 1
                    if qtd > _MAX_ARQUIVOS:
                        raise RuntimeError(
                            f"essa pasta tem arquivos demais (mais de {_MAX_ARQUIVOS}). "
                            "Escolha a pasta só do projeto")
                    texto = cheio.suffix.lower() in _TEXTO or nome.lower() in (".gitignore",)
                    if (not texto and tam > _MAX_BINARIO) or total + tam > _MAX_ZIP * 0.9:
                        grandes.append(f"{rel} ({tam // 1024} KB)")
                        continue
                    try:
                        z.write(cheio, rel)
                    except (OSError, ValueError):
                        continue
                    total += tam
            if grandes:
                extras = dict(extras)
                extras["arquivos_grandes.txt"] = "\n".join(grandes[:300])
            for nome, conteudo in extras.items():
                if conteudo is None or conteudo == "" or conteudo == b"":
                    continue
                dado = conteudo.encode("utf-8") if isinstance(conteudo, str) else conteudo
                z.writestr(f"_jarvis_cowork/{nome}", dado)
        dados = buf.getvalue()
        if len(dados) > _MAX_ZIP:
            raise RuntimeError("o projeto compactado passou de 38 MB")
        return dados

    # ── desfaz ──────────────────────────────────────────────────────────────
    def _dir_pontos(self) -> Path:
        assert self.pasta is not None
        return self.pasta / PASTA_INTERNA / "desfazer"

    def _pontos(self) -> list[Path]:
        try:
            d = self._dir_pontos()
            return sorted((p for p in d.iterdir() if (p / "manifesto.json").is_file()),
                          key=lambda p: p.name)
        except Exception:
            return []

    def _novo_ponto(self, pedido: str) -> Path:
        d = self._dir_pontos() / _agora()
        n = 2
        while d.exists():
            d = d.with_name(f"{_agora()}-{n}")
            n += 1
        (d / "arquivos").mkdir(parents=True, exist_ok=True)
        (d / "manifesto.json").write_text(json.dumps(
            {"pedido": pedido[:300], "criados": [], "guardados": []}, ensure_ascii=False),
            encoding="utf-8")
        return d

    def _limpar_pontos(self) -> None:
        pontos = self._pontos()
        for p in pontos[:-_MAX_PONTOS]:
            shutil.rmtree(p, ignore_errors=True)

    def desfazer(self) -> str:
        if not self.pasta:
            return "Não tem projeto aberto no Cowork."
        if self._ocupado:
            return "Espera eu terminar o trabalho atual; depois eu desfaço."
        pontos = self._pontos()
        if not pontos:
            return "Não tem nada para desfazer neste projeto."
        ponto = pontos[-1]
        try:
            man = json.loads((ponto / "manifesto.json").read_text(encoding="utf-8"))
        except Exception:
            shutil.rmtree(ponto, ignore_errors=True)
            return "O ponto de desfazer estava estragado; apaguei ele."
        self._parar_processo()
        for rel in man.get("criados") or []:
            alvo = self.pasta / rel
            if _dentro(self.pasta, alvo) and alvo.is_file():
                try:
                    alvo.unlink()
                except OSError:
                    pass
        for rel in man.get("guardados") or []:
            copia = ponto / "arquivos" / rel
            alvo = self.pasta / rel
            if copia.is_file() and _dentro(self.pasta, alvo):
                alvo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(copia, alvo)
        shutil.rmtree(ponto, ignore_errors=True)
        self._ultimo_teste = None
        self._avisar(etapa="")
        pedido = str(man.get("pedido") or "").strip()
        return ("Desfiz a última mudança do Cowork" + (f" ({pedido[:60]})" if pedido else "") + ".")

    # ── aplicar o que voltou da VPS ─────────────────────────────────────────
    def _aplicar(self, zip_path: Path, ponto: Path) -> dict:
        assert self.pasta is not None
        man_ponto = json.loads((ponto / "manifesto.json").read_text(encoding="utf-8"))
        criados = set(man_ponto.get("criados") or [])
        guardados = set(man_ponto.get("guardados") or [])

        def guardar(rel: str) -> None:
            if rel in guardados or rel in criados:
                return
            origem = self.pasta / rel
            if origem.is_file():
                destino = ponto / "arquivos" / rel
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origem, destino)
                guardados.add(rel)
            else:
                criados.add(rel)

        alterados, removidos = [], []
        with zipfile.ZipFile(zip_path) as z:
            nomes = {}
            for info in z.infolist():
                if info.is_dir():
                    continue
                rel = _nome_seguro(_nome_do_zip(info))
                if rel:
                    nomes[rel] = info
            manifesto = {}
            for rel, info in list(nomes.items()):
                if rel.endswith("_jarvis_mudancas.json") and "/" not in rel:
                    try:
                        manifesto = json.loads(z.read(info).decode("utf-8", errors="replace"))
                    except Exception:
                        manifesto = {}
                    nomes.pop(rel)
            for rel, info in nomes.items():
                alvo = self.pasta / rel
                if not _dentro(self.pasta, alvo):
                    continue
                guardar(rel)
                alvo.parent.mkdir(parents=True, exist_ok=True)
                tmp = alvo.with_name(alvo.name + ".jarvis-tmp")
                with z.open(info) as src, open(tmp, "wb") as dst:
                    if alvo.suffix.lower() == ".json":
                        # BOM (que o PowerShell da VPS poe) quebra JSON.parse.
                        dado = src.read()
                        dst.write(dado[3:] if dado.startswith(b"\xef\xbb\xbf") else dado)
                    else:
                        shutil.copyfileobj(src, dst)
                # Antivirus/indexador as vezes segura o arquivo por um instante.
                for tentativa in range(5):
                    try:
                        os.replace(tmp, alvo)
                        break
                    except PermissionError:
                        if tentativa == 4:
                            raise RuntimeError(f"o arquivo {rel} esta aberto/travado por outro programa")
                        time.sleep(0.4)
                alterados.append(rel)
            for rel_bruto in manifesto.get("removidos") or []:
                rel = _nome_seguro(rel_bruto)
                if not rel:
                    continue
                alvo = self.pasta / rel
                if not _dentro(self.pasta, alvo) or not alvo.is_file():
                    continue
                guardar(rel)
                try:
                    alvo.unlink()
                    removidos.append(rel)
                except OSError:
                    pass
        man_ponto["criados"] = sorted(criados)
        man_ponto["guardados"] = sorted(guardados)
        (ponto / "manifesto.json").write_text(json.dumps(man_ponto, ensure_ascii=False), encoding="utf-8")
        return {"resumo": str(manifesto.get("resumo") or "").strip(),
                "alterados": alterados, "removidos": removidos,
                "criados": [r for r in alterados if r in criados]}

    # ── historico do projeto (contexto para o Codex) ────────────────────────
    def _historico(self) -> list:
        try:
            return json.loads((self.pasta / PASTA_INTERNA / "historico.json").read_text(encoding="utf-8"))
        except Exception:
            return []

    def _registrar(self, pedido: str, resumo: str) -> None:
        try:
            h = self._historico()
            h.append({"quando": time.strftime("%d/%m %H:%M"), "pedido": pedido[:400], "resumo": resumo[:400]})
            d = self.pasta / PASTA_INTERNA
            d.mkdir(parents=True, exist_ok=True)
            (d / "historico.json").write_text(json.dumps(h[-20:], ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass

    def _historico_txt(self) -> str:
        linhas = []
        for item in self._historico()[-8:]:
            linhas.append(f"- [{item.get('quando', '')}] pedido: {item.get('pedido', '')}"
                          f" | feito: {item.get('resumo', '')}")
        return "\n".join(linhas)

    # ── o que ainda falta do pedido (continuacao automatica) ────────────────
    def _faltando(self) -> list[str]:
        """Itens que o PROPRIO Codex disse que faltam.

        Primeiro o campo "faltando" do .jarvis-cowork.json (lista vazia = acabou);
        sem ele, as linhas "[ ]" do CHECKLIST.md / TODO.md da raiz. O que so o
        PC faz (testar, gerar .exe) nao conta."""
        if not self.pasta:
            return []
        itens: list[str] = []
        cfg = None
        try:
            cfg = json.loads((self.pasta / ARQ_COMO_RODAR).read_text(encoding="utf-8-sig"))
        except Exception:
            cfg = None
        if isinstance(cfg, dict) and isinstance(cfg.get("faltando"), list):
            itens = [str(x).strip() for x in cfg["faltando"] if str(x).strip()]
        else:
            try:
                arquivos = {p.name.lower(): p for p in self.pasta.iterdir() if p.is_file()}
            except Exception:
                arquivos = {}
            for nome in _ARQS_PENDENCIA:
                arq = arquivos.get(nome)
                if arq is None:
                    continue
                try:
                    itens += _ITEM_ABERTO.findall(arq.read_text(encoding="utf-8-sig", errors="replace"))
                except Exception:
                    continue
        return [re.sub(r"\s+", " ", i)[:220] for i in itens if not _SO_NO_PC.search(i)][:40]

    @staticmethod
    def _toca_pendencias(alterados: list) -> bool:
        """A rodada mexeu na lista do que falta? (so assim ela vale para ESTE pedido)."""
        return any(str(r).lower() in _ARQS_PENDENCIA or str(r).lower() == ARQ_COMO_RODAR
                   for r in alterados or [])

    @staticmethod
    def _pedido_continuacao(original: str, faltas: list, n: int) -> str:
        cab = (f"[CONTINUAÇÃO AUTOMÁTICA {n} de {_CONTINUACOES_MAX} do MESMO pedido] Você já começou este "
               "trabalho nesta pasta, mas ainda faltam partes. Leia o que já existe; NÃO recomece do zero e "
               "NÃO desfaça o que funciona. Implemente AGORA, de verdade e por completo, o máximo possível dos "
               "itens que faltam abaixo. Depois atualize o CHECKLIST (marque [x] só o que funciona) e o campo "
               "\"faltando\" do .jarvis-cowork.json (tire o que terminou; lista vazia quando acabar). Testar e "
               "gerar o .exe não contam: o PC do cliente faz isso sozinho depois.\n"
               "ITENS QUE FALTAM:\n" + "\n".join(f"- {i}" for i in faltas[:25])
               + "\n\nPEDIDO ORIGINAL DO CLIENTE:\n")
        resto = _MAX_DESCRICAO - len(cab)
        texto = str(original or "").strip()
        if len(texto) > resto:
            texto = texto[:max(0, resto - 8)].rstrip() + " [...]"
        return cab + texto

    def _guardar_pedido(self, pedido: str) -> None:
        """O pedido INTEIRO (o historico guarda so 400 letras): o "continua" usa."""
        try:
            d = self.pasta / PASTA_INTERNA
            d.mkdir(parents=True, exist_ok=True)
            (d / "ultimo_pedido.txt").write_text(pedido, encoding="utf-8")
        except Exception:
            pass

    def _ultimo_pedido(self) -> str:
        try:
            return (self.pasta / PASTA_INTERNA / "ultimo_pedido.txt").read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    @staticmethod
    def _limpar_resumo(texto: str) -> str:
        """Tira do resumo as frases sobre o ambiente do servidor (ver _FRASE_DO_AMBIENTE)."""
        t = re.sub(r"\s+", " ", str(texto or "")).strip()
        if not t:
            return ""
        frases = re.split(r"(?<=[.!?])\s+", t)
        boas = [f for f in frases if not _FRASE_DO_AMBIENTE.search(_sem_acento(f).lower())
                and not _FRASE_DO_AMBIENTE.search(f)]
        return " ".join(boas).strip()

    # ── INICIAR.bat (16/10/2026, pedido do dono) ────────────────────────────
    # "Todo executavel que ele fizer pelo Windows ou site pelo navegador tem que
    # ter um .bat para iniciar, mesmo que o cliente nao peca." Quem escreve e o
    # PC (e nao o Codex): so aqui se sabe onde esta o Python do JARVIS. O .bat e
    # so ASCII (o cmd le .bat na pagina de codigo antiga) e usa %~dp0 para a
    # pasta, entao acento no caminho nao quebra.
    def _garantir_iniciar(self, ponto: Path | None = None) -> None:
        if not self.pasta or os.name != "nt":
            return
        try:
            cfg = self.como_rodar()
            if not cfg:
                return
            alvo = self.pasta / "INICIAR.bat"
            velho = None
            if alvo.exists():
                velho = alvo.read_text(encoding="utf-8", errors="replace")
                if _MARCA_BAT not in velho:
                    return                      # o .bat e do dono (ou feito a mao): nao mexe
            texto = self._texto_iniciar(cfg)
            if not texto or texto.replace("\r\n", "\n") == (velho or "").replace("\r\n", "\n"):
                return
            alvo.write_bytes(texto.replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii", "replace"))
            if velho is None and ponto is not None:
                man_arq = ponto / "manifesto.json"
                man = json.loads(man_arq.read_text(encoding="utf-8"))
                if "INICIAR.bat" not in (man.get("criados") or []):
                    man["criados"] = sorted(set(man.get("criados") or []) | {"INICIAR.bat"})
                    man_arq.write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _precisa_servidor(self, abrir: str) -> bool:
        """Pagina com modulo JS / fetch nao abre por file://: precisa do servidor local."""
        padrao = re.compile(r"type\s*=\s*[\"']module|\bfetch\s*\(|^\s*import\s.+\sfrom\s|import\s*\(", re.I | re.M)
        try:
            if padrao.search((self.pasta / abrir).read_text(encoding="utf-8", errors="replace")):
                return True
            for n, js in enumerate(self.pasta.rglob("*.js")):
                if n > 60 or any(parte in _IGNORAR_DIRS for parte in js.parts):
                    continue
                if padrao.search(js.read_text(encoding="utf-8", errors="replace")[:200000]):
                    return True
        except Exception:
            pass
        return False

    def _texto_iniciar(self, cfg: dict) -> str:
        cab = ["@echo off", _MARCA_BAT + " (refeito sozinho a cada mudanca; para usar o seu, apague esta linha)",
               f"title {re.sub(r'[^A-Za-z0-9 _.-]', '', _sem_acento(self.pasta.name))[:40] or 'Projeto'}",
               'cd /d "%~dp0"']
        jarvis_py = r'%LOCALAPPDATA%\Programs\JARVIS-CyberBot\runtime\python'
        if cfg["tipo"] == "web":
            abrir = cfg["abrir"].replace("/", "\\")
            if not self._precisa_servidor(cfg["abrir"]):
                return "\n".join(cab + [f'start "" "%~dp0{abrir}"', ""])
            from urllib.parse import quote
            import zlib
            porta = 8700 + zlib.crc32(_sem_acento(self.pasta.name).encode("utf-8", "ignore")) % 250
            url = f"http://127.0.0.1:{porta}/{quote(cfg['abrir'])}"
            return "\n".join(cab + [
                f'set "PYEXE={jarvis_py}\\python.exe"',
                'set "PYARG="',
                'if exist "%PYEXE%" goto servidor',
                'where py >nul 2>nul || goto direto',
                'set "PYEXE=py"',
                'set "PYARG=-3"',
                ':servidor',
                'REM a pagina usa modulos JS: precisa de um servidor local (fecha junto com a janela "Servidor")',
                f'start "Servidor do projeto" /min "%PYEXE%" %PYARG% -m http.server {porta} --bind 127.0.0.1',
                'ping -n 2 127.0.0.1 >nul',
                f'start "" "{url}"',
                'exit /b',
                ':direto',
                f'start "" "%~dp0{abrir}"',
                ""])
        comando = str(cfg.get("comando") or "").strip()
        partes = comando.split()
        if not partes:
            return ""
        primeiro = Path(partes[0]).name.lower().removesuffix(".exe")
        resto = comando.split(None, 1)[1] if len(partes) > 1 else ""
        if primeiro in ("python", "python3", "py", "pythonw"):
            if primeiro == "py":
                resto = re.sub(r"^-3(\.\d+)?\s*", "", resto)
            janela = bool(self._ultimo_teste and self._ultimo_teste.get("tipo") == "comando"
                          and self._ultimo_teste.get("tela") is not None)
            linhas = cab + [
                f'set "PYEXE={jarvis_py}\\python.exe"',
                f'set "PYWEXE={jarvis_py}\\pythonw.exe"',
                'set "PYARG="',
                'set "LIBS=%~dp0.jarvis_cowork\\pylibs"',
                'if not exist ".jarvis_cowork" mkdir ".jarvis_cowork"',
                'if exist "%PYEXE%" goto jarvis',
                'where py >nul 2>nul || goto sempython',
                'set "PYEXE=py"',
                'set "PYWEXE=pyw"',
                'set "PYARG=-3"',
                'if not exist "requirements.txt" goto rodar',
                'if exist ".jarvis_cowork\\iniciar_instalou.txt" goto rodar',
                'echo Instalando o que o programa precisa, so na primeira vez...',
                'py -3 -m pip install --user --prefer-binary -r requirements.txt && echo ok>".jarvis_cowork\\iniciar_instalou.txt"',
                'goto rodar',
                ':jarvis',
                'if not exist "requirements.txt" goto comlibs',
                'if exist "%LIBS%" goto comlibs',
                'echo Instalando o que o programa precisa, so na primeira vez...',
                '"%PYEXE%" -m pip install --disable-pip-version-check --prefer-binary --target "%LIBS%" -r requirements.txt',
                ':comlibs',
                'set "PYTHONPATH=%LIBS%;%PYTHONPATH%"',
                ':rodar',
            ]
            if janela:
                linhas += [f'start "" "%PYWEXE%" %PYARG% {resto}', "exit /b"]
            else:
                linhas += [f'"%PYEXE%" %PYARG% {resto}',
                           'if errorlevel 1 pause', "exit /b"]
            linhas += [":sempython",
                       "echo Este programa precisa do Python ou do JARVIS instalado neste computador.",
                       "pause", ""]
            return "\n".join(linhas)
        if primeiro == "node":
            return "\n".join(cab + [
                r'set "NODEEXE=%LOCALAPPDATA%\Programs\JARVIS-CyberBot\runtime\node\node.exe"',
                'if not exist "%NODEEXE%" set "NODEEXE=node"',
                f'"%NODEEXE%" {resto}',
                "if errorlevel 1 pause", ""])
        return "\n".join(cab + [comando, "if errorlevel 1 pause", ""])

    def _contar_arquivos(self, limite: int) -> int:
        """Quantos arquivos o Cowork mandaria (para no limite+1)."""
        qtd = 0
        try:
            for dirpath, dirnames, filenames in os.walk(self.pasta):
                dirnames[:] = [d for d in dirnames if d not in _IGNORAR_DIRS]
                qtd += sum(1 for n in filenames if n.lower() not in _IGNORAR_ARQ)
                if qtd > limite:
                    break
        except Exception:
            pass
        return qtd

    # ── como rodar o projeto ────────────────────────────────────────────────
    def como_rodar(self) -> dict | None:
        if not self.pasta:
            return None
        cfg = None
        try:
            bruto = (self.pasta / ARQ_COMO_RODAR).read_text(encoding="utf-8-sig")
            cfg = json.loads(bruto)
        except Exception:
            cfg = None
        if isinstance(cfg, dict):
            tipo = str(cfg.get("tipo") or "").lower()
            if tipo == "web":
                abrir = _nome_seguro(str(cfg.get("abrir") or "index.html")) or "index.html"
                if (self.pasta / abrir).is_file():
                    return {"tipo": "web", "abrir": abrir}
            if tipo == "comando" and str(cfg.get("comando") or "").strip():
                return {"tipo": "comando", "comando": str(cfg["comando"]).strip()[:300],
                        "instalar": str(cfg.get("instalar") or "").strip()[:300]}
        # Sem o arquivo: adivinha pelo que existe na pasta.
        if (self.pasta / "index.html").is_file():
            return {"tipo": "web", "abrir": "index.html"}
        pkg = self.pasta / "package.json"
        if pkg.is_file():
            try:
                scripts = json.loads(pkg.read_text(encoding="utf-8-sig")).get("scripts") or {}
            except Exception:
                scripts = {}
            for s in ("dev", "start"):
                if s in scripts:
                    return {"tipo": "comando", "comando": f"npm run {s}" if s == "dev" else "npm start",
                            "instalar": "npm install"}
        for nome in ("main.py", "app.py", "jogo.py", "game.py", "run.py"):
            if (self.pasta / nome).is_file():
                req = "pip install -r requirements.txt" if (self.pasta / "requirements.txt").is_file() else ""
                return {"tipo": "comando", "comando": f"python {nome}", "instalar": req}
        htmls = sorted(self.pasta.glob("*.html"))
        if htmls:
            return {"tipo": "web", "abrir": htmls[0].name}
        return None

    # ── servidor local (pagina com modulos JS nao abre por file://) ─────────
    def _url_web(self, abrir: str) -> str:
        if self._servidor is None or self._servidor_pasta != self.pasta:
            self._parar_servidor()
            import functools
            from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

            class _Silencioso(SimpleHTTPRequestHandler):
                def log_message(self, *a):
                    pass

                def end_headers(self):
                    # sempre a versao nova depois de cada mudanca
                    self.send_header("Cache-Control", "no-store")
                    super().end_headers()

            handler = functools.partial(_Silencioso, directory=str(self.pasta))
            srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, daemon=True, name="cowork-web").start()
            self._servidor = srv
            self._servidor_pasta = self.pasta
            self._servidor_porta = srv.server_address[1]
        from urllib.parse import quote
        return f"http://127.0.0.1:{self._servidor_porta}/{quote(abrir)}"

    def _parar_servidor(self) -> None:
        srv = self._servidor
        self._servidor = None
        self._servidor_pasta = None
        if srv is not None:
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass

    # ── teste: roda escondido, junta erros e a foto da tela ─────────────────
    def testar(self) -> dict:
        cfg = self.como_rodar()
        if not cfg:
            return {"tipo": "nenhum", "erros": [], "tela": None,
                    "relatorio": "Ainda nao ha como rodar o projeto (nenhum index.html nem comando)."}
        try:
            if cfg["tipo"] == "web":
                r = self._testar_web(self._url_web(cfg["abrir"]))
            else:
                r = self._testar_comando(cfg)
        except CoworkCancelado:
            raise
        except Exception as exc:
            r = {"tipo": cfg["tipo"], "erros": [], "tela": None,
                 "relatorio": f"O teste automatico nao conseguiu rodar: {type(exc).__name__}: {str(exc)[:300]}"}
        self._ultimo_teste = r
        self._ultimo_teste_em = time.time()
        return r

    @staticmethod
    def _tela_lisa(jpeg: bytes | None) -> bool:
        if not jpeg:
            return False
        try:
            from PIL import Image, ImageStat
            img = Image.open(io.BytesIO(jpeg)).convert("L").resize((64, 40))
            return ImageStat.Stat(img).stddev[0] < 4.0
        except Exception:
            return False

    def _testar_web(self, url: str, tempo: float = 3.0) -> dict:
        self._avisar(etapa="testando no navegador (escondido)")
        pw_dir = BASE_DIR / "runtime" / "playwright"
        if pw_dir.is_dir():
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(pw_dir))
        from playwright.sync_api import sync_playwright
        erros, avisos, falhas = [], [], []
        interacao: list[str] = []
        tela = None
        texto = ""
        with sync_playwright() as pw:
            navegador = None
            for opcoes in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
                try:
                    navegador = pw.chromium.launch(headless=True, **opcoes)
                    break
                except Exception:
                    continue
            if navegador is None:
                raise RuntimeError("nenhum navegador disponivel para o teste")
            try:
                pagina = navegador.new_page(viewport={"width": 1280, "height": 800})
                pagina.on("pageerror", lambda e: erros.append(f"erro de JavaScript: {str(e)[:300]}"))

                def _console(msg):
                    try:
                        if msg.type == "error":
                            erros.append(f"console.error: {msg.text[:300]}")
                        elif msg.type == "warning" and len(avisos) < 10:
                            avisos.append(f"console.warn: {msg.text[:200]}")
                    except Exception:
                        pass
                pagina.on("console", _console)

                def _resposta(resp):
                    try:
                        if resp.status >= 400 and not resp.url.endswith("favicon.ico"):
                            falhas.append(f"{resp.status} {resp.url.split('/', 3)[-1][:120]}")
                    except Exception:
                        pass
                pagina.on("response", _resposta)
                pagina.on("requestfailed", lambda r: falhas.append(
                    f"falhou {r.url.split('/', 3)[-1][:120]}") if not r.url.endswith("favicon.ico") else None)
                pagina.goto(url, wait_until="load", timeout=25000)
                pagina.wait_for_timeout(int(tempo * 1000))
                self._checar_cancelado()
                tela = pagina.screenshot(type="jpeg", quality=72)
                try:
                    texto = pagina.inner_text("body", timeout=3000)[:1200]
                except Exception:
                    texto = ""
                # USAR UM POUCO, como gente: clica no primeiro botao (o "Comecar"
                # de um jogo, por exemplo) e aperta umas teclas. Erro que so
                # aparece com o jogo rodando passaria batido so com a tela inicial.
                antes_uso = len(erros)
                try:
                    botao = pagina.locator("button:visible, [role=button]:visible, .btn:visible").first
                    if botao.count():
                        botao.click(timeout=2000)
                        interacao.append("cliquei no primeiro botao")
                except Exception:
                    pass
                try:
                    for tecla in ("Enter", "ArrowRight", "ArrowUp", "Space"):
                        pagina.keyboard.press(tecla)
                        pagina.wait_for_timeout(250)
                    interacao.append("apertei Enter, setas e espaco")
                    pagina.wait_for_timeout(1800)
                    tela_uso = pagina.screenshot(type="jpeg", quality=72)
                except Exception:
                    tela_uso = None
                if len(erros) > antes_uso:
                    interacao.append(f"{len(erros) - antes_uso} erro(s) apareceram DEPOIS de usar")
                tela = _lado_a_lado(tela, tela_uso)
            finally:
                try:
                    navegador.close()
                except Exception:
                    pass
        partes = [f"Teste automatico no navegador (Chromium sem janela, 1280x800) em {url}."]
        if interacao:
            partes.append("Depois de abrir: " + "; ".join(interacao) + ". A imagem mostra lado a lado "
                          "a tela inicial (esquerda) e a tela depois de usar (direita).")
        partes.append("Erros: " + ("; ".join(erros[:12]) if erros else "nenhum."))
        if falhas:
            partes.append("Arquivos/recursos que nao carregaram: " + "; ".join(falhas[:12]))
        if avisos:
            partes.append("Avisos do console: " + "; ".join(avisos[:6]))
        if self._tela_lisa(tela):
            partes.append("ATENCAO: a tela capturada esta praticamente lisa (pode estar em branco).")
        partes.append("Texto visivel na pagina: " + (re.sub(r"\s+", " ", texto).strip()[:800] or "(nenhum)"))
        return {"tipo": "web", "erros": erros + falhas, "tela": tela, "relatorio": "\n".join(partes), "url": url}

    # ── projetos que rodam por comando (python, node...) ────────────────────
    _PERMITIDOS = {"python", "python3", "py", "pythonw", "node", "npm", "npx", "pnpm", "yarn",
                   "deno", "bun", "dotnet", "java", "go", "cargo", "flutter", "love", "godot", "ruby", "php"}

    def _python(self) -> tuple[list, bool]:
        """(comando do python, e o python embutido do JARVIS?).

        SEMPRE o Python do proprio JARVIS quando ele existe (16/10/2026): o
        cliente pode nao ter Python nenhum, e o do dono (3.14 do sistema) fazia
        o teste aqui passar com bibliotecas que o cliente nao tem. Assim o que
        o dono testa e exatamente o que o cliente roda, e nada vai para o
        Python do sistema (as bibliotecas ficam em .jarvis_cowork\\pylibs)."""
        embutido = BASE_DIR / "runtime" / "python" / "python.exe"
        if embutido.is_file():
            return [str(embutido)], True
        # Linux/Mac (17/10/2026): o Python do JARVIS e o venv que roda este
        # processo (~/.local/share/JARVIS-CyberBot/venv); sem isto caia no
        # python3 do sistema, sem as bibliotecas e com o pip travado (PEP 668).
        if os.name != "nt" and sys.executable and Path(sys.executable).is_file():
            return [sys.executable], True
        py = shutil.which("py")
        if py:
            return [py, "-3"], False
        for cand in [shutil.which("python")] + [shutil.which("python3")]:
            if cand and "windowsapps" not in cand.lower():
                return [cand], False
        return [str(embutido)], True

    def _montar_comando(self, comando: str) -> tuple[str, dict, str]:
        """Comando seguro + ambiente. Devolve ("", env, motivo) se recusar."""
        cmd = comando.strip()
        if re.search(r"[&|;<>`]|\b(del|erase|rd|rmdir|format|shutdown|reg|takeown|icacls|"
                     r"remove-item|invoke-webrequest|curl|wget)\b", cmd, re.I):
            return "", {}, "o comando tinha partes perigosas"
        primeiro = cmd.split()[0].lower() if cmd.split() else ""
        primeiro_base = Path(primeiro).name.lower().removesuffix(".exe").removesuffix(".cmd")
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        node_dir = BASE_DIR / "runtime" / "node"
        if node_dir.is_dir():
            env["PATH"] = env.get("PATH", "") + os.pathsep + str(node_dir)
        if primeiro_base in ("python", "python3", "py", "pythonw"):
            exe, embutido = self._python()
            resto = cmd.split(None, 1)[1] if len(cmd.split()) > 1 else ""
            if primeiro_base == "py":
                resto = re.sub(r"^-3(\.\d+)?\s*", "", resto)
            cmd = subprocess.list2cmdline(exe) + (" " + resto if resto else "")
            if embutido:
                libs = self.pasta / PASTA_INTERNA / "pylibs"
                env["PYTHONPATH"] = str(libs) + os.pathsep + env.get("PYTHONPATH", "")
            return cmd, env, ""
        if primeiro_base in self._PERMITIDOS:
            # O programa existe neste PC? Sem ele, nao e defeito do projeto (e
            # nao vale gastar rodada de correcao): e so avisar o que falta.
            achou = shutil.which(primeiro_base, path=env.get("PATH"))
            if not achou:
                return "", env, (f"o {primeiro_base} nao esta instalado neste computador "
                                 f"(precisa instalar para rodar este projeto)")
            return cmd, env, ""
        # .bat/.cmd/.ps1 NAO rodam sozinhos: seriam qualquer comando que o
        # servidor escrevesse, executado no PC do dono sem ele ver.
        return "", env, f"o comando '{primeiro}' nao esta na lista dos que eu rodo sozinho"

    def _instalar(self, cfg: dict, env: dict) -> str:
        """Instala dependencias quando o arquivo delas mudou. Devolve o relato."""
        inst = str(cfg.get("instalar") or "").strip()
        if not inst:
            return ""
        alvo = None
        for nome in ("package.json", "requirements.txt", "pyproject.toml"):
            if (self.pasta / nome).is_file():
                alvo = self.pasta / nome
                break
        marca = self.pasta / PASTA_INTERNA / "instalado.json"
        # O Python que vai rodar entra na conta: trocar de Python (o do sistema
        # -> o do JARVIS) tem de instalar de novo, senao falta biblioteca.
        assinatura = hashlib.sha1((alvo.read_bytes() if alvo else b"") + inst.encode()
                                  + " ".join(self._python()[0]).encode()).hexdigest()
        try:
            if json.loads(marca.read_text(encoding="utf-8")).get("assinatura") == assinatura:
                return ""
        except Exception:
            pass
        m = re.match(r"^(?:(?:python3?|py)(?:\s+-3(?:\.\d+)?)?\s+-m\s+)?pip3?\s+install\s+(.+)$", inst, re.I)
        if m:
            # pip: sempre pelo python que vai RODAR o projeto. Se for o embutido
            # do JARVIS, instala numa pasta do projeto (--target) para nao mexer
            # no proprio JARVIS.
            if re.search(r"[&|;<>`]", m.group(1)):
                return "Nao instalei as dependencias: o comando tinha partes perigosas."
            exe, embutido = self._python()
            # --prefer-binary: PC de cliente nao tem compilador; versao com roda
            # pronta para Windows ganha da que precisaria compilar.
            args = exe + ["-m", "pip", "install", "--disable-pip-version-check", "--prefer-binary",
                          "--no-warn-script-location"]
            if embutido:
                # --upgrade: sem ele o pip mantem a versao velha que ja esta na
                # pasta quando o requirements muda.
                args += ["--upgrade", "--target", str(self.pasta / PASTA_INTERNA / "pylibs")]
            cmd = subprocess.list2cmdline(args + m.group(1).split())
            env2 = dict(env)
        else:
            cmd, env2, motivo = self._montar_comando(inst)
            if not cmd:
                return f"Nao instalei as dependencias: {motivo}."
        self._avisar(etapa="instalando as dependências do projeto")
        # Popen + espera em pedacos: o "parar" funciona no meio da instalacao
        # (um npm install pode levar minutos).
        log = self.pasta / PASTA_INTERNA / "instalacao.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "wb") as saida_arq:
            proc = subprocess.Popen(cmd, cwd=str(self.pasta), shell=True, env=env2, stdout=saida_arq,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            fim = time.time() + 900
            try:
                while proc.poll() is None:
                    if self._cancelar.is_set():
                        _matar_arvore(proc.pid)
                        raise CoworkCancelado()
                    if time.time() > fim:
                        _matar_arvore(proc.pid)
                        return f"A instalacao ({inst}) passou de 15 minutos e foi parada."
                    time.sleep(0.5)
            finally:
                if proc.poll() is None:
                    _matar_arvore(proc.pid)
        try:
            saida = log.read_text(encoding="utf-8", errors="replace")
        except Exception:
            saida = ""
        if proc.returncode == 0:
            marca.write_text(json.dumps({"assinatura": assinatura}), encoding="utf-8")
            return ""
        return f"A instalacao ({inst}) falhou (codigo {proc.returncode}):\n" + saida[-3000:]

    def _testar_comando(self, cfg: dict) -> dict:
        cmd, env, motivo = self._montar_comando(cfg["comando"])
        if not cmd:
            return {"tipo": "comando", "erros": [], "tela": None,
                    "relatorio": f"Nao rodei o projeto: {motivo}. Comando: {cfg['comando']}"}
        relato_inst = self._instalar(cfg, env)
        self._checar_cancelado()
        self._avisar(etapa="rodando o projeto para testar")
        log = self.pasta / PASTA_INTERNA / "ultimo_teste.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        erros: list[str] = []
        tela = None
        url = ""
        interacao: list[str] = []
        fechei = False            # o teste mandou fechar a janela (o X), como gente
        fechou_no_x = False
        inicio = time.time()
        fim_em = None
        with open(log, "wb") as saida:
            proc = subprocess.Popen(cmd, cwd=str(self.pasta), shell=True, env=env, stdout=saida,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                fim = time.time() + 12.0
                while time.time() < fim and proc.poll() is None:
                    self._checar_cancelado()
                    time.sleep(0.4)
                    try:
                        m = re.search(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d+[^\s'\"]*",
                                      log.read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        m = None
                    if m:
                        url = m.group(0).replace("0.0.0.0", "127.0.0.1")
                        time.sleep(1.5)
                        break
                codigo = proc.poll()
                if codigo is None:
                    if url:
                        web = self._testar_web(url)
                        erros += web["erros"]
                        tela = web["tela"]
                    else:
                        time.sleep(2.0)
                        pids = _arvore(proc.pid)
                        tela = _foto_das_janelas(pids)
                        hwnd = _janela_principal(pids)
                        if hwnd:
                            # USAR UM POUCO (16/10/2026), igual ao teste web: Enter
                            # sai do menu e comeca o jogo. Erro que so aparece
                            # depois do JOGAR passava batido (o dono achava).
                            _apertar_tecla(hwnd, 0x0D)
                            interacao.append("apertei Enter na janela")
                            time.sleep(2.5)
                            self._checar_cancelado()
                            if proc.poll() is not None:
                                interacao.append("o programa FECHOU logo depois do Enter")
                                erros.append("o programa fechou depois de apertar Enter (tela inicial -> jogo)")
                            else:
                                tela_uso = _foto_das_janelas(_arvore(proc.pid))
                                tela = _lado_a_lado(tela, tela_uso)
                                # FECHAR PELO X: erro ao sair (o "nao esta abrindo"
                                # do Serpente era uma excecao no fechamento) so
                                # aparece se o programa fechar sozinho.
                                fechei = _fechar_janela(_janela_principal(_arvore(proc.pid)) or hwnd)
                                if fechei:
                                    fim_x = time.time() + 5.0
                                    while time.time() < fim_x and proc.poll() is None:
                                        time.sleep(0.25)
                                    fechou_no_x = proc.poll() is not None
                                    interacao.append("cliquei no X da janela" + (
                                        "" if fechou_no_x else " e ele NAO fechou em 5 s"))
                                    if not fechou_no_x:
                                        # O dono clica no X e nada acontece = "travou".
                                        erros.append("a janela NAO fecha ao clicar no X (botao fechar): "
                                                     "fechar a janela tem que encerrar o programa")
            finally:
                codigo = proc.poll()
                fim_em = time.time()
                _matar_arvore(proc.pid)
        try:
            texto = log.read_text(encoding="utf-8", errors="replace")
        except Exception:
            texto = ""
        # ERRO ESCONDIDO EM ARQUIVO (17/10/2026): o Operacao Omega dava
        # AttributeError ao iniciar, gravava no %APPDATA%\OperacaoOmega\erros.log
        # e saia com codigo 0 -- o teste via "terminou com codigo 0" e dizia que
        # estava tudo certo. Agora o log de erro novo do programa entra no relatorio.
        logs_erro = _logs_de_erro(self.pasta, inicio)
        cauda = "\n".join(texto.strip().splitlines()[-80:])[-6000:]
        if fechou_no_x:
            if codigo not in (None, 0):
                erros.append(f"ao fechar a janela pelo X o programa saiu com erro (codigo {codigo})")
        elif codigo not in (None, 0):
            erros.append(f"o programa fechou sozinho com codigo {codigo}")
        elif codigo == 0 and tela is None and not url:
            # Jogo/app que abre e some com codigo 0 nao "terminou bem": fechou ao abrir.
            dur = max(0.0, (fim_em or time.time()) - inicio)
            erros.append(f"o programa FECHOU SOZINHO {dur:.1f} s depois de abrir (codigo 0) e nao ficou "
                         "com janela aberta: se e jogo/app, ele esta fechando ao abrir (erro escondido)")
        for caminho_log, conteudo in logs_erro:
            erros.append(f"o programa gravou um erro no arquivo {caminho_log.name}")
        for padrao in (r"Traceback \(most recent call last\)", r"\b\w*Error:", r"Cannot find module",
                       r"ModuleNotFoundError", r"SyntaxError", r"Unhandled", r"Exception in"):
            if re.search(padrao, texto):
                erros.append(f"a saida tem erro ({padrao.strip(chr(92))})")
                break
        partes = [f"Teste automatico rodando: {cfg['comando']}"]
        if relato_inst:
            partes.append(relato_inst)
            erros.append("a instalacao das dependencias falhou")
        if fechou_no_x:
            situacao = (f"abriu, rodou, e fechou quando cliquei no X (codigo {codigo})")
        elif codigo is None:
            situacao = "continuou rodando (normal para app/jogo/servidor)"
        else:
            situacao = f"terminou com codigo {codigo}"
        partes.append("Situacao: " + situacao)
        if interacao:
            partes.append("Depois de abrir: " + "; ".join(interacao) + ". A imagem mostra lado a lado "
                          "a tela inicial (esquerda) e a tela depois do Enter (direita).")
        if url:
            partes.append(f"Endereco que ele abriu: {url}")
        partes.append("Saida do programa (fim):\n" + (cauda or "(nada)"))
        for caminho_log, conteudo in logs_erro:
            partes.append(f"ARQUIVO DE ERRO que o programa gravou durante o teste ({caminho_log}):\n"
                          + conteudo[-3500:])
        if tela is None and codigo is None and not url:
            partes.append("Nao encontrei janela do programa para fotografar.")
        if self._tela_lisa(tela):
            partes.append("ATENCAO: a janela capturada esta praticamente lisa (pode estar em branco).")
        return {"tipo": "comando", "erros": erros, "tela": tela, "relatorio": "\n".join(partes), "url": url}

    # ── abrir para o dono ver ───────────────────────────────────────────────
    def _parar_processo(self) -> None:
        proc = self._processo
        self._processo = None
        if proc is not None and proc.poll() is None:
            _matar_arvore(proc.pid)
        self._fechar_janela_app()

    @staticmethod
    def _navegador() -> str | None:
        """Edge ou Chrome instalados (para abrir o projeto como PROGRAMA)."""
        candidatos = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            shutil.which("msedge") or "", shutil.which("chrome") or "",
        ]
        for c in candidatos:
            if c and os.path.isfile(c):
                return c
        return None

    def _fechar_janela_app(self) -> None:
        janela = getattr(self, "_janela_app", None)
        self._janela_app = None
        if janela is not None and janela.poll() is None:
            _matar_arvore(janela.pid)

    def _abrir_janela_app(self, url: str) -> bool:
        """JANELA PROPRIA, sem barra de endereco nem abas (05/10/2026).

        O Diego pediu um jogo e ele abriu numa aba do Chrome dele, no meio das
        abas pessoais — "ele criou no navegador". Agora o projeto abre como um
        programa: Edge/Chrome no modo --app, com um perfil SO do Cowork (nao
        mexe no navegador do dono). A cada mudanca a janela velha fecha e a
        nova abre ja com a versao atualizada."""
        exe = self._navegador()
        if not exe:
            return False
        self._fechar_janela_app()
        perfil = BASE_DIR / "cache" / "cowork_janela"
        try:
            perfil.mkdir(parents=True, exist_ok=True)
            self._janela_app = subprocess.Popen(
                [exe, f"--app={url}", f"--user-data-dir={perfil}", "--window-size=1280,860",
                 "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
                 "--autoplay-policy=no-user-gesture-required"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            self._janela_app = None
            return False

    def rodar(self) -> str:
        """Abre o projeto para o dono ver — pedido pelo dono (botao/voz)."""
        if self._ocupado:
            return "Espera eu terminar o trabalho do Cowork; no fim eu mesmo abro para você."
        self._garantir_iniciar()
        self.falha_ao_abrir = ""
        r = self._abrir_resultado()
        if r.startswith("Abri o projeto para"):
            self.falha_ao_abrir = self.conferir_aberto(7.0)
            if self.falha_ao_abrir:
                return "O programa fechou sozinho logo depois de abrir. Vou corrigir o erro."
        return r

    def _abrir_resultado(self) -> str:
        """Abre o projeto para o dono ver (janela propria ou o programa)."""
        if not self.pasta:
            return "Não tem projeto aberto no Cowork."
        cfg = self.como_rodar()
        if not cfg:
            return "Esse projeto ainda não tem o que abrir."
        if cfg["tipo"] == "web":
            url = self._url_web(cfg["abrir"])
            if self._abrir_janela_app(url):
                return "Abri o projeto numa janela própria."
            try:
                if os.name == "nt":
                    os.startfile(url)  # noqa: S606
                else:
                    subprocess.Popen(["xdg-open", url])
                return "Abri o projeto no navegador."
            except Exception as exc:
                return f"Não consegui abrir o navegador: {str(exc)[:80]}"
        cmd, env, motivo = self._montar_comando(cfg["comando"])
        if not cmd:
            return f"Não rodei o projeto: {motivo}."
        self._parar_processo()
        console = bool(self._ultimo_teste and self._ultimo_teste.get("tipo") == "comando"
                       and self._ultimo_teste.get("tela") is None
                       and not self._ultimo_teste.get("url"))
        flags = (getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if console
                 else getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._log_execucao = self.pasta / PASTA_INTERNA / "execucao.log"
        try:
            self._log_execucao.parent.mkdir(parents=True, exist_ok=True)
            saida = open(self._log_execucao, "wb")
        except Exception:
            saida = subprocess.DEVNULL
        try:
            self._aberto_em = time.time()
            self._processo = subprocess.Popen(cmd, cwd=str(self.pasta), shell=True, env=env,
                                              creationflags=flags, stdout=saida,
                                              stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        except Exception as exc:
            return f"Não consegui abrir o projeto: {str(exc)[:80]}"
        finally:
            if saida is not subprocess.DEVNULL:
                saida.close()           # o filho ficou com a copia dele
        url = (self._ultimo_teste or {}).get("url") or ""
        if url:
            time.sleep(2.5)
            if not self._abrir_janela_app(url):
                try:
                    os.startfile(url)  # noqa: S606
                except Exception:
                    pass
        return "Abri o projeto para você ver."

    def conferir_aberto(self, espera: float = 8.0) -> str:
        """O programa que abri para o dono CONTINUA aberto? "" = sim.

        Pedido do Diego (17/10/2026): "o jogo que ele fez nao funciona, nao abre;
        tem que identificar quando ele abrir, ver se esta rodando e, se nao
        esta, corrigir o erro". Devolve o relatorio para a rodada de correcao."""
        proc = self._processo
        if proc is None:
            return ""
        fim = time.time() + espera
        while time.time() < fim and proc.poll() is None:
            time.sleep(0.3)
        if proc.poll() is None:
            return ""
        dur = time.time() - float(getattr(self, "_aberto_em", time.time()))
        saida = ""
        try:
            saida = self._log_execucao.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
        partes = [f"O JARVIS abriu o programa para o dono ({self.como_rodar() or ''}) e ele FECHOU "
                  f"SOZINHO {dur:.1f} s depois (codigo {proc.returncode}). Ele tem que abrir e continuar "
                  "aberto. Ache o erro e corrija de verdade.",
                  "Saida do programa (fim):\n" + ("\n".join(saida.strip().splitlines()[-60:])[-5000:] or "(nada)")]
        for caminho_log, conteudo in _logs_de_erro(self.pasta, float(getattr(self, "_aberto_em", 0.0))):
            partes.append(f"ARQUIVO DE ERRO que o programa gravou ({caminho_log}):\n" + conteudo[-3500:])
        self._processo = None
        return "\n".join(partes)

    def abrir_pasta_no_explorer(self) -> str:
        if not self.pasta:
            return "Não tem projeto aberto no Cowork."
        try:
            os.startfile(str(self.pasta))  # noqa: S606
            return "Abri a pasta do projeto."
        except Exception as exc:
            return f"Não consegui abrir a pasta: {str(exc)[:80]}"

    # ── o pedido ────────────────────────────────────────────────────────────
    def ocupado(self) -> bool:
        return self._ocupado

    def parar(self) -> str:
        if not self._ocupado:
            return "O Cowork não está trabalhando agora."
        self._cancelar.set()
        self._avisar(etapa="parando...")
        return "Certo, estou parando o trabalho do Cowork."

    def _rodada(self, ponte, pedido: str, modo: str, teste: dict | None, ponto: Path) -> dict:
        extras = {"historico.txt": self._historico_txt()}
        if teste:
            extras["relatorio.txt"] = teste.get("relatorio") or ""
            if teste.get("tela"):
                extras["tela.jpg"] = teste["tela"]
        self._avisar(etapa="preparando a cópia do projeto")
        dados = self._empacotar(extras)
        self._checar_cancelado()
        self._avisar(etapa=("conferindo o teste com o servidor" if modo == "revisao"
                            else "trabalhando no servidor"))
        r = ponte.cowork_pela_ponte(
            dados, pedido, self.pasta.name, modo, timeout=_TIMEOUT_RODADA,
            ao_progresso=lambda t: self._avisar(linha=t), cancelar=self._cancelar)
        self._checar_cancelado()
        caminho = Path(r["zip"])
        try:
            self._avisar(etapa="aplicando as mudanças na pasta")
            aplicado = self._aplicar(caminho, ponto)
        finally:
            try:
                caminho.unlink()
            except OSError:
                pass
        if not aplicado["resumo"]:
            aplicado["resumo"] = str(r.get("resumo") or "").strip()
        return aplicado

    def executar_pedido(self, pedido: str, ponte) -> str:
        """Faz o pedido inteiro. BLOQUEIA (minutos): chamar numa thread."""
        pedido = str(pedido or "").strip()
        if not pedido:
            return "Diga o que você quer que eu faça no projeto."
        if ponte is None:
            return "O Cowork precisa da conexão com o servidor do JARVIS, e ela não está ativa agora."
        with self._trava:
            if self._ocupado:
                return ("Ainda estou trabalhando no pedido anterior do Cowork. "
                        "Assim que terminar eu te aviso.")
            self._ocupado = True
        self._cancelar.clear()
        self.linhas = []
        aviso_pasta = ""
        try:
            if not self.pasta:
                nova = self.novo_projeto(pedido)
                self.pasta = nova
                self._salvar_config()
                aviso_pasta = f"Criei o projeto na pasta {nova.name}, dentro de Documentos, JARVIS Cowork. "
            elif self._contar_arquivos(_MAX_ARQUIVOS) > _MAX_ARQUIVOS:
                # PASTA GRANDE DEMAIS (10/10/2026): o Diego pediu o Bomberman com a
                # pasta "Meus Projeto" aberta e o Cowork so dizia "arquivos demais",
                # tres vezes seguidas. Pedido de coisa NOVA vai para pasta nova.
                if _RE_CRIAR.search(_sem_acento(pedido).lower()):
                    antiga = self.pasta.name
                    nova = self.novo_projeto(pedido)
                    self._parar_processo()
                    self.pasta = nova
                    self._ultimo_teste = None
                    self._salvar_config()
                    aviso_pasta = (f"A pasta {antiga} tem arquivos demais para o Cowork, então criei o "
                                   f"projeto na pasta {nova.name}, dentro de Documentos, JARVIS Cowork. ")
                else:
                    return (f"A pasta {self.pasta.name} tem arquivos demais para o Cowork (mais de "
                            f"{_MAX_ARQUIVOS}). Clique em PASTA e escolha a pasta só do projeto.")
            self._avisar(etapa="começando")
            self._limpar_pontos()
            ponto = self._novo_ponto(pedido)

            # Como o projeto esta AGORA (para "a cor esta errada" fazer sentido).
            teste_antes = None
            if self.como_rodar():
                teste_antes = self.testar()
                self._checar_cancelado()

            # PASTA VAZIA = PROJETO NOVO, dito com todas as letras (05/10/2026).
            # Numa pasta vazia o primeiro comando do Codex (listar arquivos)
            # volta vazio com codigo 1, e o modelo chegou a concluir "estou em
            # modo somente leitura" e devolver sem fazer nada.
            vazio = not any(p.name != PASTA_INTERNA for p in self.pasta.iterdir())
            # "continua" / "termina": o pedido de verdade e o ANTERIOR (inteiro).
            original = pedido
            descricao = pedido
            if _RE_CONTINUA.match(_sem_acento(pedido).lower()) and len(pedido) < 200 and self._ultimo_pedido():
                original = self._ultimo_pedido()
                faltas0 = self._faltando()
                if faltas0:
                    descricao = self._pedido_continuacao(original, faltas0, 1)
                else:
                    descricao = (pedido + "\n\nO PEDIDO ANTERIOR, que é para continuar e terminar:\n"
                                 + original)[:_MAX_DESCRICAO]
            elif len(pedido) > 400 or _RE_CRIAR.search(_sem_acento(pedido).lower()):
                # So o pedido GRANDE fica guardado: "muda a cor" ou a correcao
                # automatica nao podem virar o "continua" do jogo inteiro.
                self._guardar_pedido(pedido)
            if vazio:
                descricao = ("[PROJETO NOVO: esta pasta esta VAZIA. Crie todos os arquivos do zero "
                             "nela. Voce TEM permissao de escrita; listagem vazia ou 'rg' com codigo 1 "
                             "so quer dizer que ainda nao ha arquivos.]\n" + descricao)
            feito = self._rodada(ponte, descricao, "trabalho", teste_antes, ponto)
            if (not feito["alterados"] and not feito["removidos"]
                    and _ACHOU_QUE_NAO_PODIA.search(feito["resumo"] or "")):
                self._avisar(etapa="o servidor se confundiu; mandando de novo")
                feito = self._rodada(ponte, (
                    "[ATENCAO: na tentativa anterior voce concluiu que nao tinha acesso de escrita. "
                    "Isso estava ERRADO: a pasta aceita escrita normalmente. Faca o pedido agora, "
                    "criando e alterando os arquivos de verdade.]\n" + descricao),
                    "trabalho", teste_antes, ponto)
            if not feito["alterados"] and not feito["removidos"]:
                # Nada mudou: so repassa o que o servidor disse, sem testar,
                # sem abrir, sem registrar no historico e sem deixar um
                # "desfaz" vazio para tras.
                shutil.rmtree(ponto, ignore_errors=True)
                return (self._limpar_resumo(feito["resumo"])
                        or "O servidor terminou sem mudar nada no projeto.")

            # CONTINUA SOZINHO enquanto o proprio Codex disser que falta parte
            # (ver _ITEM_ABERTO). So vale se esta rodada mexeu na lista do que
            # falta: um CHECKLIST velho de outro pedido nao puxa trabalho novo.
            resumos = [feito["resumo"]]
            continuacoes = 0
            insistiu = False
            faltas = self._faltando() if self._toca_pendencias(feito["alterados"]) else []
            while faltas and continuacoes < _CONTINUACOES_MAX:
                self._checar_cancelado()
                continuacoes += 1
                self._avisar(etapa=f"continuando sozinho ({continuacoes} de {_CONTINUACOES_MAX}): "
                                   f"ainda faltam {len(faltas)} partes")
                pedido_cont = self._pedido_continuacao(original, faltas, continuacoes)
                mais = self._rodada(ponte, pedido_cont, "trabalho", None, ponto)
                if _ACHOU_QUE_NAO_PODIA.search(mais["resumo"] or "") and not insistiu:
                    # 16/10/2026: "a gravacao das alteracoes foi bloqueada pelo
                    # ambiente" -- o modelo concluiu isso sozinho; manda de novo.
                    insistiu = True
                    self._avisar(etapa="o servidor se confundiu; mandando de novo")
                    mais2 = self._rodada(ponte, (
                        "[ATENCAO: na tentativa anterior voce concluiu que a gravacao estava bloqueada. "
                        "Isso estava ERRADO: a pasta aceita escrita (use a ferramenta apply_patch). "
                        "Faca agora, criando e alterando os arquivos de verdade.]\n" + pedido_cont)[:_MAX_DESCRICAO],
                        "trabalho", None, ponto)
                    for chave in ("alterados", "removidos", "criados"):
                        mais2[chave] = sorted(set(mais2[chave]) | set(mais[chave]))
                    mais = mais2
                if _ACHOU_QUE_NAO_PODIA.search(mais["resumo"] or ""):
                    mais["resumo"] = ""
                if not mais["alterados"] and not mais["removidos"]:
                    break
                for chave in ("alterados", "removidos", "criados"):
                    feito[chave] = sorted(set(feito[chave]) | set(mais[chave]))
                if mais["resumo"]:
                    resumos.append(mais["resumo"])
                novas = self._faltando()
                if novas == faltas:
                    break                       # nao andou: nao insiste
                faltas = novas

            faltam_no_fim = self._faltando() if (continuacoes or faltas) else []
            resumo = self._limpar_resumo(resumos[0]) or "Terminei o que você pediu."
            if continuacoes:
                ultimo = self._limpar_resumo(resumos[-1]) if len(resumos) > 1 else ""
                resumo += (f" Depois continuei sozinho mais {continuacoes} "
                           f"{'vez' if continuacoes == 1 else 'vezes'} "
                           f"{'para avançar' if faltam_no_fim else 'para completar'}")
                resumo += (": " + _primeiras_frases(ultimo, 2)) if ultimo else "."
            mudou_muito = bool(feito["criados"]) or len(feito["alterados"]) >= 3

            correcoes = 0
            teste = None
            for rodada in range(_RODADAS_EXTRAS):
                self._checar_cancelado()
                teste = self.testar()
                if teste["tipo"] == "nenhum":
                    break
                visual = rodada == 0 and mudou_muito and teste.get("tela") is not None
                if not teste["erros"] and not visual:
                    break
                self._avisar(etapa=("corrigindo o que o teste encontrou" if teste["erros"]
                                    else "conferindo a tela do resultado"))
                rev = self._rodada(ponte, pedido, "revisao", teste, ponto)
                if not rev["alterados"] and not rev["removidos"]:
                    break                       # o Codex olhou e disse que esta OK
                correcoes += 1
                teste = None                    # precisa testar de novo

            if teste is None and self.como_rodar():
                teste = self.testar()
            self._registrar(pedido, resumo)
            self._checar_cancelado()
            abriu = ""
            self._garantir_iniciar(ponto)
            fechou_ao_abrir = ""
            if self.como_rodar():
                self._avisar(etapa="abrindo para você ver")
                abriu = self._abrir_resultado()
                for _volta in range(2):
                    if not abriu.startswith("Abri o projeto para"):
                        break
                    self._avisar(etapa="conferindo se o programa ficou aberto")
                    fechou_ao_abrir = self.conferir_aberto(8.0)
                    if not fechou_ao_abrir:
                        break
                    self._checar_cancelado()
                    self._avisar(etapa="o programa fechou sozinho ao abrir; corrigindo")
                    rev = self._rodada(ponte, pedido, "revisao",
                                       {"relatorio": fechou_ao_abrir, "tela": None}, ponto)
                    if not rev["alterados"] and not rev["removidos"]:
                        break
                    correcoes += 1
                    teste = self.testar()
                    self._garantir_iniciar(ponto)
                    abriu = self._abrir_resultado()
                    fechou_ao_abrir = ""
                if abriu.startswith("Abri o projeto para") and not fechou_ao_abrir:
                    fechou_ao_abrir = self.conferir_aberto(4.0)

            frase = aviso_pasta + resumo
            if correcoes:
                frase += (" Testei, encontrei o que precisava ajustar e corrigi."
                          if correcoes == 1 else f" Testei e fiz {correcoes} rodadas de correção.")
            if teste and teste.get("erros"):
                frase += " Ainda apareceu um erro no teste; se quiser, peça para eu corrigir."
            if faltam_no_fim:
                frase += (f" Ainda ficaram {len(faltam_no_fim)} partes por fazer; "
                          "é só dizer continua que eu termino.")
            if fechou_ao_abrir:
                frase += (" Mas o programa ainda fecha sozinho logo depois de abrir; "
                          "diga corrige que eu continuo consertando.")
            elif abriu.startswith("Abri"):
                frase += " Já abri para você ver."
            return frase
        except CoworkCancelado:
            return "Parei o trabalho do Cowork. O que já tinha sido aplicado pode ser desfeito com 'desfaz'."
        except Exception as exc:
            msg = re.sub(r"(?i)codex|openai", "JARVIS", str(exc).strip())[:220]
            # A VPS ja manda "O Cowork nao concluiu: ..." -- nao repetir.
            msg = re.sub(r"^\s*O Cowork n[aã]o (?:concluiu|conseguiu concluir)\s*:\s*", "", msg, flags=re.I)
            if msg.lower() == "cancelado":
                return "Parei o trabalho do Cowork."
            if re.search(r"agente encerrou com codigo", msg):
                msg = ("o servidor parou no meio do trabalho (pode ser o limite de uso de agora); "
                       "tente de novo daqui a alguns minutos")
            return f"O Cowork não conseguiu concluir: {msg}"
        finally:
            self._ocupado = False
            self._avisar(etapa="")


def _logs_de_erro(pasta: Path | None, desde: float) -> list[tuple[Path, str]]:
    """Arquivos de ERRO que o programa gravou desde `desde` (o dele: na pasta do
    projeto ou numa pasta propria do %APPDATA% / %LOCALAPPDATA%)."""
    achados: list[tuple[Path, str]] = []
    nome_ok = re.compile(r"err|crash|falha|exce|trace", re.I)
    conteudo_ok = re.compile(r"Traceback|\w+Error\b|Exception|Erro\b|Falha\b")

    def olhar(arq: Path) -> None:
        try:
            st = arq.stat()
            if st.st_mtime < desde - 1 or st.st_size <= 0 or st.st_size > 50 * 1024 * 1024:
                return
            with open(arq, "rb") as f:
                if st.st_size > 8000:
                    f.seek(-8000, os.SEEK_END)
                texto = f.read().decode("utf-8", errors="replace")
            if conteudo_ok.search(texto):
                achados.append((arq, texto))
        except Exception:
            pass

    try:
        if pasta is not None:
            for raiz, pastas, arqs in os.walk(pasta):
                prof = len(Path(raiz).relative_to(pasta).parts)
                pastas[:] = [d for d in pastas if d not in _IGNORAR_DIRS and not d.startswith(".")] if prof < 3 else []
                for a in arqs:
                    if a.lower().endswith((".log", ".txt")) and (nome_ok.search(a) or a.lower().endswith(".log")):
                        olhar(Path(raiz) / a)
        for var in ("APPDATA", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if not base or not os.path.isdir(base):
                continue
            for d in os.scandir(base):
                if not d.is_dir(follow_symlinks=False):
                    continue
                try:
                    for a in os.scandir(d.path):
                        if a.is_file(follow_symlinks=False) and a.name.lower().endswith((".log", ".txt")) \
                                and nome_ok.search(a.name):
                            olhar(Path(a.path))
                except OSError:
                    continue
    except Exception:
        pass
    return achados[:3]


def _primeiras_frases(texto: str, n: int) -> str:
    frases = re.split(r"(?<=[.!?])\s+", str(texto or "").strip())
    return " ".join(f for f in frases[:n] if f).strip()


def _lado_a_lado(a: bytes | None, b: bytes | None) -> bytes | None:
    """Junta duas fotos (antes e depois de usar) numa so, para o Codex ver as duas."""
    if not a or not b:
        return a or b
    try:
        from PIL import Image
        ia = Image.open(io.BytesIO(a)).convert("RGB")
        ib = Image.open(io.BytesIO(b)).convert("RGB")
        h = max(ia.height, ib.height)
        junta = Image.new("RGB", (ia.width + ib.width + 8, h), (40, 40, 40))
        junta.paste(ia, (0, 0))
        junta.paste(ib, (ia.width + 8, 0))
        junta.thumbnail((1800, 900))
        saida = io.BytesIO()
        junta.save(saida, format="JPEG", quality=72)
        return saida.getvalue()
    except Exception:
        return a


# ── utilidades de processo e janela (Windows) ──────────────────────────────
def _arvore(pid: int) -> list[int]:
    try:
        import psutil
        p = psutil.Process(pid)
        return [pid] + [c.pid for c in p.children(recursive=True)]
    except Exception:
        return [pid]


def _matar_arvore(pid: int) -> None:
    try:
        import psutil
        p = psutil.Process(pid)
        filhos = p.children(recursive=True)
        for c in filhos:
            try:
                c.kill()
            except Exception:
                pass
        try:
            p.kill()
        except Exception:
            pass
        psutil.wait_procs(filhos + [p], timeout=3)
    except Exception:
        pass


def _janelas_visiveis(pids: list[int]) -> list[tuple]:
    """(area, hwnd, largura, altura) das janelas visiveis desses processos, maior primeiro."""
    if os.name != "nt" or not pids:
        return []
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        alvo = set(pids)
        achadas = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _cada(h, _):
            if not user32.IsWindowVisible(h):
                return True
            dono = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(dono))
            if dono.value in alvo:
                r = wintypes.RECT()
                user32.GetWindowRect(h, ctypes.byref(r))
                area = (r.right - r.left) * (r.bottom - r.top)
                if area > 40000:
                    achadas.append((area, h, r.right - r.left, r.bottom - r.top))
            return True
        user32.EnumWindows(_cada, 0)
        achadas.sort(key=lambda a: a[0], reverse=True)
        return achadas
    except Exception:
        return []


def _user32_proprio():
    """user32 so nosso: argtypes no windll.user32 compartilhado mudaria as
    chamadas do resto do JARVIS."""
    global _USER32
    if _USER32 is None:
        import ctypes
        u = ctypes.WinDLL("user32")
        u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        u.PostMessageW.restype = ctypes.c_int
        u.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
        u.MapVirtualKeyW.restype = ctypes.c_uint
        _USER32 = u
    return _USER32


_USER32 = None


def _janela_principal(pids: list[int]):
    achadas = _janelas_visiveis(pids)
    return achadas[0][1] if achadas else None


def _apertar_tecla(hwnd, vk: int) -> None:
    """Tecla SO para aquela janela (PostMessage), sem mexer no foco nem no
    teclado do dono."""
    try:
        user32 = _user32_proprio()
        scan = user32.MapVirtualKeyW(vk, 0) & 0xFF
        user32.PostMessageW(hwnd, 0x0100, vk, 1 | (scan << 16))                         # WM_KEYDOWN
        if vk == 0x0D:
            user32.PostMessageW(hwnd, 0x0102, 0x0D, 1 | (scan << 16))                   # WM_CHAR
        time.sleep(0.08)
        user32.PostMessageW(hwnd, 0x0101, vk, 1 | (scan << 16) | (1 << 30) | (1 << 31))  # WM_KEYUP
    except Exception:
        pass


def _fechar_janela(hwnd) -> bool:
    """O mesmo que clicar no X (WM_CLOSE)."""
    if not hwnd:
        return False
    try:
        user32 = _user32_proprio()
        return bool(user32.PostMessageW(hwnd, 0x0010, 0, 0))
    except Exception:
        return False


def _foto_das_janelas(pids: list[int]) -> bytes | None:
    """Foto da maior janela visivel desses processos (PrintWindow: funciona
    mesmo com a janela atras de outras)."""
    if os.name != "nt" or not pids:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        from PIL import Image
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        achadas = _janelas_visiveis(pids)
        if not achadas:
            return None
        _, hwnd, w, h = achadas[0]
        hdc = user32.GetWindowDC(hwnd)
        mdc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(mdc, bmp)
        user32.PrintWindow(hwnd, mdc, 2)

        class _BIH(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
        bi = _BIH(ctypes.sizeof(_BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, hdc)
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
        img.thumbnail((1280, 900))
        saida = io.BytesIO()
        img.save(saida, format="JPEG", quality=75)
        return saida.getvalue()
    except Exception:
        return None


# Um Cowork por JARVIS.
COWORK = Cowork()
