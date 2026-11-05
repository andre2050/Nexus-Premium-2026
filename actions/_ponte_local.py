# -*- coding: utf-8 -*-
"""Ponte local: o "servidor" das funcoes que vieram do JARVIS, rodando no PC.

O JARVIS mandava parte do trabalho para um servidor privado (a VPS do
fornecedor): decidir o proximo passo do `usar_computador`, criar site e
imagem, editar foto, buscar leads e o programador `cowork`. No NEXUS esse
trabalho e feito aqui, com a chave do Gemini do proprio usuario
(`core/gemini.py`), sem depender de servidor de terceiros.

Os modulos do JARVIS continuam iguais: eles pedem `player._codex_relay` e
recebem um `PonteLocal`, que responde com os MESMOS formatos da ponte antiga:

    pedir_passo_na_tela(...)  -> {"acoes": [...], "fala", "vi", "avaliacao", "memoria"}
    submit_codex_job(...)     -> {"ok": True, "path": "<arquivo criado>"}
    cowork_pela_ponte(...)    -> {"zip": "<zip com o que mudou>", "resumo": "..."}

Arquivo com "_" no comeco: o carregador de acoes do NEXUS pula, porque isto e
peca de apoio, nao ferramenta.
"""
from __future__ import annotations

import io
import json
import re
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

from core import gemini as G

# ── modelos ───────────────────────────────────────────────────────────────────
# Trabalho longo ou com imagem vai primeiro para um modelo REST (o "Live" so
# devolve o que fala, e corta respostas grandes); se ele falhar, a escada
# SMART do core/gemini.py assume.
_MODELO_LONGO = "gemini-3.5-flash"
_MODELO_VISAO = "gemini-3.5-flash"
# Modelos de imagem verificados na lista desta chave (04/11/2026).
_MODELOS_IMAGEM = (
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
    "gemini-3-pro-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
)

_PASTA_CRIACOES = Path.home() / "Desktop" / "NEXUS Criacoes"
_PASTA_LEADS = Path.home() / "Desktop" / "NEXUS Leads"


def _types():
    from google.genai import types  # noqa: PLC0415
    return types


def _config(instrucao: str = "", max_tokens: int = 0, json_mime: bool = False,
            ferramentas=None, modalidades=None):
    types = _types()
    kw = {}
    if instrucao:
        kw["system_instruction"] = instrucao
    if max_tokens:
        kw["max_output_tokens"] = int(max_tokens)
    if json_mime:
        kw["response_mime_type"] = "application/json"
    if ferramentas:
        kw["tools"] = ferramentas
    if modalidades:
        kw["response_modalities"] = modalidades
    return types.GenerateContentConfig(**kw) if kw else None


def _sem_cerca(texto: str) -> str:
    """Tira ```cercas``` que o modelo poe em volta de codigo/JSON."""
    t = str(texto or "").strip()
    m = re.match(r"^```[\w+-]*\s*\n(.*?)\n?```\s*$", t, re.S)
    return m.group(1) if m else t


def _json_de(texto: str):
    t = _sem_cerca(texto)
    if "{" in t and "}" in t:
        t = t[t.find("{"): t.rfind("}") + 1]
    try:
        return json.loads(t)
    except Exception:
        return None


def _nome_de_arquivo(texto: str, padrao: str = "Projeto") -> str:
    import unicodedata  # noqa: PLC0415
    t = unicodedata.normalize("NFD", str(texto or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\- ]+", "", t).strip().replace(" ", "_")
    return (t[:40] or padrao)


def _carimbo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ── o "cerebro" que os modulos do JARVIS pedem ───────────────────────────────

def gerar(pedido: str, instrucao: str = "", timeout_ms: int = 180_000,
          max_tokens: int = 32_768) -> str:
    """Resposta LONGA de uma vez (plano de desenho, receita de video, codigo).

    Mesmo formato do `escrever_em_camadas(pedido, instrucao)` do JARVIS.
    """
    cfg = _config(instrucao, max_tokens=max_tokens)
    return G.text(str(pedido or ""), tier=_MODELO_LONGO, config=cfg, timeout_ms=timeout_ms)


def gerar_para_digitar(pedido: str, linguagem: str = "") -> str:
    """Conteudo pronto para ser digitado (o `gerar` do `digitar_na_tela`)."""
    ling = f" em {linguagem}" if linguagem else ""
    instrucao = (
        "Voce escreve EXATAMENTE o conteudo pedido, pronto para ser digitado num "
        "editor de texto simples. Responda SO com o conteudo: sem cerca de codigo "
        "(```), sem titulo, sem explicacao antes ou depois, sem markdown. Se for "
        f"codigo{ling}, entregue o programa COMPLETO e funcional, com comentarios "
        "curtos em portugues do Brasil, indentacao com 4 espacos e sem tabulacao. "
        "Se for texto, escreva em portugues do Brasil, direto.")
    return _sem_cerca(gerar(pedido, instrucao))


def ver(imagem: bytes, pergunta: str, mime: str = "image/jpeg",
        timeout_ms: int = 60_000, instrucao: str = "", json_mime: bool = False) -> str:
    """Olha uma imagem e responde (o `ver`/`olhar` dos modulos do JARVIS)."""
    if not imagem:
        return ""
    types = _types()
    partes = [types.Part.from_bytes(data=bytes(imagem), mime_type=mime), str(pergunta or "")]
    cfg = _config(instrucao, json_mime=json_mime)
    return G.text(partes, tier=_MODELO_VISAO, config=cfg, timeout_ms=timeout_ms)


_ERRO_IMAGEM = {"texto": ""}

_SEM_COTA_DE_IMAGEM = (
    "a criacao de imagens do Gemini nao esta liberada nesta chave: o plano gratuito do "
    "Google nao inclui modelos de imagem (cota zero). Para liberar, ative o faturamento do "
    "projeto da chave em aistudio.google.com")


def gerar_imagem(prompt: str, base: bytes | None = None,
                 base_mime: str = "image/png") -> tuple[bytes, str] | None:
    """Cria (ou edita, com `base`) uma imagem. Devolve (bytes, mime) ou None.

    Quando nao der, o motivo fica em `_ERRO_IMAGEM["texto"]` (ex.: chave do plano
    gratuito, que tem cota ZERO para imagem — medido em 04/11/2026).
    """
    _ERRO_IMAGEM["texto"] = ""
    types = _types()
    conteudo = [str(prompt or "")]
    if base:
        conteudo = [types.Part.from_bytes(data=bytes(base), mime_type=base_mime), str(prompt or "")]
    try:
        cl = G.client(timeout_ms=240_000)
    except Exception as exc:
        print(f"[PonteLocal] sem cliente Gemini: {exc}")
        return None
    cfg = _config(modalidades=["TEXT", "IMAGE"])
    ultimo = ""
    so_cota_zero = True
    for modelo in _MODELOS_IMAGEM:
        try:
            resp = cl.models.generate_content(model=modelo, contents=conteudo, config=cfg)
            for cand in getattr(resp, "candidates", None) or []:
                for parte in getattr(getattr(cand, "content", None), "parts", None) or []:
                    blob = getattr(parte, "inline_data", None)
                    dados = getattr(blob, "data", None) if blob is not None else None
                    if dados:
                        return bytes(dados), (getattr(blob, "mime_type", None) or "image/png")
            ultimo = f"{modelo}: respondeu sem imagem"
            so_cota_zero = False
        except Exception as exc:
            msg = str(exc)
            if not ("limit: 0" in msg or "FreeTier" in msg or "NOT_FOUND" in msg or "404" in msg):
                so_cota_zero = False
            ultimo = f"{modelo}: {msg[:160]}"
            print(f"[PonteLocal] imagem {ultimo}")
    print(f"[PonteLocal] nenhum modelo de imagem respondeu ({ultimo})")
    _ERRO_IMAGEM["texto"] = (_SEM_COTA_DE_IMAGEM if so_cota_zero
                             else "o Gemini nao devolveu imagem agora (cota do dia ou pedido recusado)")
    return None


def comando_powershell(tarefa: str) -> str:
    """Escreve UM comando de PowerShell para a tarefa (o `executar_tarefa`)."""
    from actions.tarefa_comando import (  # noqa: PLC0415
        PEDIDO_AO_CODEX, SISTEMA_DO_COMANDO, _limpar_resposta)
    bruto = G.text(PEDIDO_AO_CODEX + str(tarefa or ""), tier=_MODELO_LONGO,
                   config=_config(SISTEMA_DO_COMANDO, max_tokens=8192),
                   timeout_ms=60_000)
    return _limpar_resposta(bruto)


# ── o passo do "usar_computador" ─────────────────────────────────────────────

_INSTRUCAO_PASSO = """\
Voce controla o computador Windows do usuario olhando a tela, um passo por vez,
ate concluir a TAREFA. Cada mensagem traz: a foto da tela (LARGURA x ALTURA em
pixels), a lista NUMERADA dos elementos que o Windows enxerga (o mesmo numero
esta desenhado na foto), o contexto (janela da frente, janelas abertas) e o
historico do que voce ja fez e do que aconteceu.

Responda SO com um objeto JSON, sem texto fora dele:
{
  "vi": "o que voce ve de importante nesta tela (curto)",
  "avaliacao": "o passo anterior deu certo? o que mudou?",
  "memoria": "anotacoes que voce quer lembrar nos proximos passos (curto)",
  "fala": "frase curta para o usuario, ou vazio",
  "acoes": [ {"acao": "...", ...}, ... ]   // de 1 a 4 movimentos, em ordem
}

COMO MIRAR (para clicar, digitar num campo, arrastar, rolar):
  1. "elemento": N   -> o numero da lista (PREFERIDO, e exato);
  2. "nome": "texto" -> o nome visivel do botao/campo/item;
  3. "x": 0, "y": 0  -> pixel da FOTO, so se nao houver elemento nem nome.
Para arrastar, a segunda ponta usa "elemento2" / "nome2" / "x2","y2".

ACOES QUE EXISTEM:
  clicar | clicar_duplo | clicar_direito | mover     (+ alvo; "modificador": "ctrl"|"shift" opcional)
  arrastar                    (+ alvo de origem e alvo2 de destino)
  digitar  {"texto": "...", "limpar": true|false}  (+ alvo do campo, opcional)
  credencial {"apelido": "site", "campo": "usuario"|"senha"}  (preenche dado salvo no PC)
  tecla    {"teclas": "enter" | "ctrl+c" | "alt+tab" | "win+r" ..., "vezes": 1}
  rolar    {"direcao": "baixo"|"cima", "quantidade": 5}  (+ alvo opcional)
  rolar_ate {"nome": "texto que precisa aparecer"}
  clicar_nome {"nome": "texto do item"}     acionar {"nome": "botao"}
  expandir | recolher {"nome": "item da arvore"}
  escolher {"lista": "nome da lista", "opcao": "valor"}
  abrir_programa {"nome": "notepad"}         abrir_url {"url": "https://..."}
  abrir_pasta {"caminho": "C:/..."}          focar_janela {"titulo": "parte do titulo"}
  abrir_config {"pagina": "ms-settings:display" | "control" | "services.msc"}
  janela {"acao": "janela", ...} use maximizar | minimizar | restaurar | fechar_janela como "acao"
  esperar {"segundos": 2}    esperar_elemento {"nome": "...", "segundos": 10}
  ler_tela                   ampliar {"x": 0, "y": 0}   (foto ampliada daquele ponto)
  fechar_erros               pesquisar {"texto": "pergunta para a internet"}
  perguntar {"pergunta": "..."}  (so quando falta um dado que so o usuario sabe)
  responder {"fala": "..."}      (informar algo sem terminar)
  concluido {"fala": "o que foi feito"}   falhou {"fala": "por que nao deu"}

REGRAS:
- Nunca invente que algo deu certo: confira na foto seguinte.
- Prefira atalhos e enderecos diretos (abrir_config, abrir_url, abrir_programa) a
  procurar com o mouse.
- Se a mesma acao nao mudou nada duas vezes, mude de estrategia.
- Nao apague arquivos, nao compre nada, nao envie mensagens e nao mude senhas
  sem que a TAREFA peca isso com todas as letras.
- Quando a tarefa estiver feita, responda com a acao "concluido".
"""


# ── a ponte ──────────────────────────────────────────────────────────────────

class PonteLocal:
    """O lugar do `RelayClient` do JARVIS, resolvido com o Gemini do usuario."""

    connected = True

    def wait_connected(self, timeout: float = 0.0) -> bool:  # noqa: ARG002
        return True

    def encerrar_passos_na_tela(self, job_id: str = "") -> None:  # noqa: ARG002
        """Na VPS isto liberava a fila do trabalho; aqui nao ha fila."""
        return None

    # usar_computador ---------------------------------------------------------
    def pedir_passo_na_tela(self, job_id: str, tarefa: str, passo: int, jpeg: bytes,
                            largura: int, altura: int, historico: list,
                            timeout: float = 90.0, elementos: list | None = None,
                            contexto: dict | None = None, regras: list | None = None,
                            memoria: str = "", historico_seq: int | None = None,
                            cancelar=None) -> dict:
        if cancelar is not None:
            try:
                if cancelar():
                    raise RuntimeError("o usuario mandou parar")
            except RuntimeError:
                raise
            except Exception:
                pass
        texto = [
            f"TAREFA: {str(tarefa or '')[:4000]}",
            f"PASSO: {int(passo)}   FOTO: {int(largura)} x {int(altura)} pixels",
        ]
        if regras:
            texto.append("REGRAS DESTA TAREFA:\n" + "\n".join(str(r)[:4000] for r in regras[:12]))
        if memoria:
            texto.append("SUA MEMORIA: " + str(memoria)[:1500])
        if contexto:
            texto.append("CONTEXTO: " + json.dumps(contexto, ensure_ascii=False)[:3000])
        if elementos:
            texto.append("ELEMENTOS NA TELA:\n" + "\n".join(str(e)[:160] for e in elementos[:60]))
        if historico:
            texto.append("HISTORICO:\n" + "\n".join(str(h)[:1800] for h in historico[-24:]))
        bruto = ver(jpeg, "\n\n".join(texto), mime="image/jpeg",
                    timeout_ms=int(max(20.0, float(timeout)) * 1000),
                    instrucao=_INSTRUCAO_PASSO, json_mime=True)
        dados = _json_de(bruto)
        if not isinstance(dados, dict):
            raise RuntimeError("o Gemini nao decidiu o passo (resposta vazia ou fora do formato)")
        acoes = dados.get("acoes")
        if not isinstance(acoes, list):
            acao = dados.get("acao")
            acoes = [dados] if isinstance(acao, str) else []
        return {"acoes": [a for a in acoes if isinstance(a, dict)][:4],
                "fala": str(dados.get("fala") or ""),
                "vi": str(dados.get("vi") or ""),
                "avaliacao": str(dados.get("avaliacao") or ""),
                "memoria": str(dados.get("memoria") or ""), "v": 3}

    # codex_remote: site / imagem / edicao / leads / conversa ------------------
    def submit_codex_job(self, kind: str, description: str, project_name: str = "Projeto",
                         timeout: float = 960.0, imagem: bytes | None = None) -> dict:
        kind = str(kind or "").strip().lower()
        _PASTA_CRIACOES.mkdir(parents=True, exist_ok=True)
        nome = _nome_de_arquivo(project_name or description, "Criacao")
        if kind in ("image", "image_edit"):
            return self._imagem(kind, description, nome, imagem)
        if kind == "site":
            return self._site(description, nome, timeout)
        if kind == "leads":
            return self._leads(description, timeout)
        if kind == "chat":
            texto = G.text(str(description or ""), tier=_MODELO_LONGO,
                           config=_config(max_tokens=8192),
                           timeout_ms=int(min(timeout, 180) * 1000))
            if not texto:
                raise RuntimeError("o Gemini nao respondeu")
            p = Path(tempfile.gettempdir()) / f"nexus-resposta-{_carimbo()}.txt"
            p.write_text(texto, encoding="utf-8")
            return {"ok": True, "path": str(p)}
        raise RuntimeError(f"tipo de trabalho desconhecido: {kind}")

    def _imagem(self, kind: str, description: str, nome: str, imagem: bytes | None) -> dict:
        if kind == "image_edit":
            if not imagem:
                raise RuntimeError("faltou a imagem para editar")
            prompt = ("Edite esta imagem conforme o pedido, mantendo tudo o que o pedido nao "
                      "manda mudar: " + str(description or ""))
            r = gerar_imagem(prompt, base=imagem, base_mime="image/png")
        else:
            r = gerar_imagem("Crie uma imagem de alta qualidade: " + str(description or ""))
        if not r:
            raise RuntimeError(_ERRO_IMAGEM["texto"] or "o Gemini nao devolveu imagem")
        dados, mime = r
        ext = ".jpg" if "jpeg" in mime or "jpg" in mime else ".png"
        destino = _PASTA_CRIACOES / f"{nome}_{_carimbo()}{ext}"
        destino.write_bytes(dados)
        return {"ok": True, "path": str(destino)}

    def _site(self, description: str, nome: str, timeout: float) -> dict:
        instrucao = (
            "Voce e um desenvolvedor web senior. Crie um site COMPLETO, moderno, bonito e "
            "responsivo em UM UNICO arquivo index.html (CSS e JavaScript embutidos, sem "
            "dependencias locais; fontes do Google Fonts e imagens de https://picsum.photos "
            "ou SVG inline sao permitidas). Textos em portugues do Brasil, com conteudo "
            "realista para o negocio pedido. Responda SO com o HTML, comecando em <!DOCTYPE html>.")
        html = _sem_cerca(gerar(description, instrucao,
                                timeout_ms=int(min(timeout, 300) * 1000), max_tokens=65_536))
        if "<html" not in html.lower():
            raise RuntimeError("o Gemini nao devolveu um HTML valido")
        pasta = _PASTA_CRIACOES / f"{nome}_{_carimbo()}"
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / "index.html"
        destino.write_text(html, encoding="utf-8")
        return {"ok": True, "path": str(destino)}

    def _leads(self, description: str, timeout: float) -> dict:
        types = _types()
        instrucao = (
            "Voce monta listas de empresas REAIS a partir da busca do Google. Use a busca "
            "quantas vezes precisar. NUNCA invente empresa, telefone, site ou nota: so inclua "
            "o que encontrou nos resultados, e deixe o campo como 'nao encontrado' quando "
            "faltar. Respeite TODOS os filtros do pedido (com/sem WhatsApp, com/sem site, nota "
            "minima, bairro...). Formato, uma empresa por bloco, numerado:\n"
            "[1] Nome da empresa\nEndereco: ...\nTelefone: ...\nWhatsApp: ...\nSite: ...\n"
            "Nota: ... (N avaliacoes)\nFonte: link onde achou\n\n"
            "Depois do ultimo bloco, nada mais.")
        cfg = _config(instrucao, ferramentas=[types.Tool(google_search=types.GoogleSearch())])
        texto = G.text(str(description or ""), tier=G.SEARCH, config=cfg,
                       timeout_ms=int(min(timeout, 300) * 1000))
        fonte = "busca do Google"
        if not texto or not re.search(r"(?m)^\s*\[\d+\]", texto):
            # Plano B: a busca com Google tem cota propria e acaba. A mesma busca
            # do `web_search` (DuckDuckGo) traz os resultados, e o Gemini so
            # organiza o que esta NELES — sem inventar.
            texto = self._leads_pela_busca_aberta(description, instrucao, timeout)
            fonte = "busca na internet (DuckDuckGo)"
        if not texto or not re.search(r"(?m)^\s*\[\d+\]", texto):
            raise RuntimeError("a busca nao trouxe nenhuma empresa")
        pasta = _PASTA_LEADS
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"leads_{_nome_de_arquivo(description, 'busca')}_{_carimbo()}.txt"
        cabeca = (f"Leads - {description}\nGerado pelo NEXUS em "
                  f"{datetime.now():%d/%m/%Y %H:%M} a partir da {fonte}.\n"
                  "Confira os dados antes de entrar em contato.\n\n")
        destino.write_text(cabeca + _sem_cerca(texto).strip() + "\n", encoding="utf-8")
        return {"ok": True, "path": str(destino)}

    @staticmethod
    def _leads_pela_busca_aberta(description: str, instrucao: str, timeout: float) -> str:
        try:
            from actions.web_search import _ddg_search  # noqa: PLC0415
        except Exception:
            return ""
        achados, vistos = [], set()
        for consulta in (description, f"{description} telefone endereço",
                         f"{description} whatsapp instagram"):
            for r in _ddg_search(consulta, max_results=12):
                if r.get("url") and r["url"] not in vistos:
                    vistos.add(r["url"])
                    achados.append(r)
        if not achados:
            return ""
        resultados = "\n\n".join(
            f"- {r.get('title', '')}\n  {r.get('snippet', '')}\n  {r.get('url', '')}" for r in achados[:36])
        pedido = (f"PEDIDO: {description}\n\nRESULTADOS DA BUSCA (use SO o que esta aqui):\n"
                  f"{resultados}")
        return G.text(pedido, tier=G.SMART, config=_config(instrucao, max_tokens=8192),
                      timeout_ms=int(min(timeout, 180) * 1000))

    # cowork --------------------------------------------------------------------
    _TEXTO_MAX = 400_000      # caracteres de codigo mandados ao modelo

    def cowork_pela_ponte(self, dados: bytes, pedido: str, projeto: str, modo: str,
                          timeout: float = 1800.0, ao_progresso=None, cancelar=None) -> dict:
        def avisa(t):
            if ao_progresso:
                try:
                    ao_progresso(str(t))
                except Exception:
                    pass

        arquivos: dict[str, str] = {}
        extras: dict[str, str] = {}
        tela = None
        total = 0
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                nome = info.filename
                if nome.startswith("_jarvis_cowork/"):
                    chave = nome.split("/", 1)[1]
                    if chave.endswith(".jpg"):
                        tela = z.read(info)
                    else:
                        extras[chave] = z.read(info).decode("utf-8", errors="replace")
                    continue
                try:
                    conteudo = z.read(info).decode("utf-8")
                except UnicodeDecodeError:
                    continue          # binario: o modelo nao precisa ver
                if total + len(conteudo) > self._TEXTO_MAX:
                    extras.setdefault("arquivos_grandes.txt", "")
                    extras["arquivos_grandes.txt"] += f"\n{nome} (nao enviado: limite de tamanho)"
                    continue
                arquivos[nome] = conteudo
                total += len(conteudo)
        if cancelar is not None and cancelar.is_set():
            raise RuntimeError("cancelado")

        revisao = str(modo or "") == "revisao"
        instrucao = (
            "Voce e o COWORK, um programador senior trabalhando DENTRO da pasta de um projeto "
            "do usuario no Windows. Voce recebe todos os arquivos de texto do projeto e um "
            "pedido. Faca o pedido de verdade: codigo completo e funcionando, sem "
            "'TODO', sem trechos omitidos. Se o projeto estiver vazio, crie-o do zero (prefira "
            "HTML/CSS/JS num index.html para jogos e sites simples, ou Python com um main.py). "
            + ("MODO REVISAO: o projeto foi aberto e testado no PC; leia o relatorio (e a "
               "imagem da tela, se vier) e corrija os erros encontrados. " if revisao else "")
            + "Responda SO com JSON neste formato:\n"
            '{"resumo": "o que voce fez, em 1 ou 2 frases em portugues", '
            '"arquivos": [{"caminho": "pasta/arquivo.ext", "conteudo": "ARQUIVO INTEIRO"}], '
            '"removidos": ["caminho/de/arquivo/apagado"]}\n'
            "Em 'arquivos' entram SO os arquivos criados ou alterados, sempre com o conteudo "
            "COMPLETO. Caminhos relativos a raiz do projeto, com barra normal.")
        partes_txt = [f"PROJETO: {projeto}", f"PEDIDO:\n{str(pedido or '')[:8000]}"]
        for chave in ("historico.txt", "relatorio.txt", "arquivos_grandes.txt"):
            if extras.get(chave):
                partes_txt.append(f"{chave.upper()}:\n{extras[chave][:12000]}")
        if arquivos:
            partes_txt.append("ARQUIVOS DO PROJETO:")
            for nome, conteudo in sorted(arquivos.items()):
                partes_txt.append(f"===== {nome} =====\n{conteudo}")
        else:
            partes_txt.append("O PROJETO ESTA VAZIO.")
        conteudo_msg: list = ["\n\n".join(partes_txt)]
        if tela:
            conteudo_msg.insert(0, _types().Part.from_bytes(data=tela, mime_type="image/jpeg"))

        avisa("o Gemini esta programando")
        bruto = G.text(conteudo_msg, tier=_MODELO_LONGO,
                       config=_config(instrucao, max_tokens=65_536, json_mime=True),
                       timeout_ms=int(min(float(timeout), 900.0) * 1000))
        resposta = _json_de(bruto)
        if not isinstance(resposta, dict):
            raise RuntimeError("o Gemini nao devolveu as mudancas no formato certo")
        if cancelar is not None and cancelar.is_set():
            raise RuntimeError("cancelado")

        saida = Path(tempfile.gettempdir()) / f"nexus-cowork-{_carimbo()}.zip"
        n = 0
        with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
            for arq in resposta.get("arquivos") or []:
                if not isinstance(arq, dict):
                    continue
                caminho = str(arq.get("caminho") or "").replace("\\", "/").lstrip("/")
                if not caminho or ".." in caminho.split("/"):
                    continue
                z.writestr(caminho, str(arq.get("conteudo") or ""))
                n += 1
            removidos = [str(r) for r in (resposta.get("removidos") or []) if r]
            z.writestr("_jarvis_mudancas.json",
                       json.dumps({"removidos": removidos}, ensure_ascii=False))
        avisa(f"{n} arquivo(s) prontos")
        return {"zip": str(saida), "resumo": str(resposta.get("resumo") or "").strip()}


PONTE = PonteLocal()


# ── a janela, vista pelos modulos do JARVIS ──────────────────────────────────

_ESTADOS_NEXUS = {"LISTENING", "THINKING", "SPEAKING", "SLEEPING"}


class JanelaProxy:
    """A `NexusUI` com o que os modulos do JARVIS esperam a mais.

    Tudo o que nao esta aqui vai direto para a janela do NEXUS.
    """

    def __init__(self, ui):
        object.__setattr__(self, "_ui", ui)
        object.__setattr__(self, "_codex_relay", PONTE)
        object.__setattr__(self, "_codex_remote_mode", True)

    def __getattr__(self, nome):
        ui = object.__getattribute__(self, "_ui")
        if ui is None:
            raise AttributeError(nome)
        return getattr(ui, nome)

    def set_state(self, estado: str):
        ui = object.__getattribute__(self, "_ui")
        if ui is None or not hasattr(ui, "set_state"):
            return
        e = str(estado or "").upper()
        if e in ("TAREFA_FIM", "IDLE", "DONE"):
            e = "LISTENING"
        elif e not in _ESTADOS_NEXUS:
            e = "THINKING"
        try:
            ui.set_state(e)
        except Exception:
            pass

    def write_log(self, texto: str):
        ui = object.__getattribute__(self, "_ui")
        if ui is not None and hasattr(ui, "write_log"):
            try:
                ui.write_log(str(texto).replace("[JARVIS]", "[NEXUS]"))
            except Exception:
                pass


def janela(player):
    """Embrulha o `player` que o NEXUS passa para as acoes."""
    if isinstance(player, JanelaProxy):
        return player
    return JanelaProxy(player)


def assistente(speak):
    """O `NexusLive` por tras do `speak` (para dashboard, interromper, etc.)."""
    return getattr(speak, "__self__", None)


def falar_por(speak):
    """Uma funcao `falar(frase)` que nunca levanta erro.

    No NEXUS o `speak` manda o texto para o modelo como se fosse o usuario
    falando; para NARRAR no meio de uma tarefa o canal certo e o `plugin_say`,
    que pede ao modelo para dizer a frase.
    """
    live = assistente(speak)
    dizer = getattr(live, "plugin_say", None) if live is not None else None

    def _falar(frase: str) -> None:
        if not frase:
            return
        try:
            if callable(dizer):
                dizer(f"[AVISO DA TAREFA EM ANDAMENTO] Diga ao usuario, curto e natural, "
                      f"so isto: {frase}")
            elif speak is not None:
                speak(str(frase))
        except Exception:
            pass
    return _falar


def ultima_fala(speak, segundos: float = 90.0) -> str:
    """O que o usuario disse (ou digitou) nos ultimos `segundos`."""
    live = assistente(speak)
    falas = getattr(live, "_falas_recentes", None) or [] if live is not None else []
    agora_ = time.monotonic()
    return " ".join(t for (q, t) in falas if agora_ - q <= segundos).strip()


def esc_apertado() -> bool:
    """True enquanto a tecla ESC estiver apertada (freio das tarefas na tela)."""
    try:
        import ctypes  # noqa: PLC0415
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
    except Exception:
        return False


def esta_falando(speak):
    live = assistente(speak)
    return lambda: bool(getattr(live, "_is_speaking", False)) if live is not None else False


def foto_da_tela_jpeg(qualidade: int = 80) -> tuple[bytes, int, int]:
    """Print da tela inteira em JPEG: (bytes, largura, altura)."""
    import mss  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    with mss.mss() as s:
        mon = s.monitors[1]
        shot = s.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=qualidade)
    return buf.getvalue(), img.width, img.height


def agora_ms() -> int:
    return int(time.time() * 1000)
