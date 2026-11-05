"""vscode — abre e cria projetos no Visual Studio Code (4.7).

    "abre o projeto da padaria no VS Code"        "abre o index.html na linha 40"
    "cria um site novo chamado Portfólio"         "cria um app em Python chamado Controle"
    "quais projetos eu tenho?"                    "o VS Code está instalado?"

A pasta de projetos é a mesma do dev_agent: Desktop\\NexusProjects.
Criar um modelo base é rápido e NÃO usa IA — para um site/app feito sob medida,
com telas e lógica próprias, o certo é o dev_agent ou o Forge.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


_CRIADORES = [
    "index.html", "styles.css", "app.js", "README.md",
]

_SITE_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{nome}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="topo">
    <h1>{nome}</h1>
    <p>Edite este arquivo e veja o resultado no navegador.</p>
  </header>

  <main class="conteudo">
    <section class="cartao">
      <h2>Primeira seção</h2>
      <p>Comece por aqui.</p>
      <button id="botao">Clique</button>
    </section>
  </main>

  <script src="app.js"></script>
</body>
</html>
"""

_SITE_CSS = """:root {
  --fundo: #0b0c10;
  --texto: #f4f5f7;
  --destaque: #4da3ff;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  min-height: 100vh;
  background: var(--fundo);
  color: var(--texto);
  font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
}

.topo { padding: 4rem 1.5rem 2rem; text-align: center; }
.topo h1 { margin: 0 0 .5rem; font-size: clamp(2rem, 6vw, 3.5rem); }
.topo p { margin: 0; color: #9aa3b2; }

.conteudo { max-width: 900px; margin: 0 auto; padding: 0 1.5rem 4rem; }

.cartao {
  background: #14161c;
  border: 1px solid #232733;
  border-radius: 14px;
  padding: 1.5rem;
}

button {
  margin-top: 1rem;
  padding: .7rem 1.2rem;
  border: 0;
  border-radius: 10px;
  background: var(--destaque);
  color: #06121f;
  font-weight: 600;
  cursor: pointer;
}
button:hover { filter: brightness(1.1); }
"""

_SITE_JS = """const botao = document.getElementById("botao");

botao?.addEventListener("click", () => {
  botao.textContent = "Funcionou!";
  console.log("clique registrado");
});
"""

_APP_PY = '''"""Ponto de entrada do projeto. Rode com:  python main.py"""


def main() -> None:
    print("Olá! Edite main.py para começar.")


if __name__ == "__main__":
    main()
'''

_LEIAME = """# {nome}

Projeto criado pelo NEXUS.

## Como rodar

{rodar}
"""

_RODAR_SITE = "Abra `index.html` no navegador (duplo clique) ou use a extensão Live Server do VS Code."

_RODAR_APP = """```bash
python -m venv .venv
.venv\\Scripts\\activate      # Windows
pip install -r requirements.txt
python main.py
```"""


# ── VS Code ─────────────────────────────────────────────────────────────────

def _candidatos_code() -> list[list[str]]:
    """Formas de abrir o VS Code, da mais confiável para a mais improvisada."""
    saida: list[list[str]] = []

    for nome in ("code", "code.cmd", "code-insiders", "codium"):
        achado = shutil.which(nome)
        if achado:
            saida.append([achado])

    if sys.platform == "win32":
        for base in (
            os.environ.get("LOCALAPPDATA"),
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
        ):
            if not base:
                continue
            for exe in ("Programs/Microsoft VS Code/Code.exe", "Microsoft VS Code/Code.exe"):
                p = Path(base) / exe
                if p.exists():
                    saida.append([str(p)])
    elif sys.platform == "darwin":
        saida.append(["open", "-a", "Visual Studio Code"])
    return saida


def _abrir_no_code(*alvos: str) -> tuple[bool, str]:
    """Abre o VS Code nos alvos. Devolve (conseguiu, frase para o usuário)."""
    erros = []
    for cmd in _candidatos_code():
        try:
            flags = getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen(cmd + list(alvos), creationflags=flags,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, "abri no VS Code"
        except Exception as e:              # tenta o próximo caminho
            erros.append(f"{cmd[0]}: {e}")
    return False, ("mas não achei o VS Code instalado neste computador"
                   f"{f' ({erros[0]})' if erros else ''}")


def _raiz_projetos() -> Path:
    try:
        from actions.dev_agent import _projects_root
        return Path(_projects_root())
    except Exception:
        return Path.home() / "Desktop" / "NexusProjects"


def _nome_seguro(nome: str) -> str:
    limpo = re.sub(r"[^\w\s.-]", "", nome, flags=re.UNICODE).strip(" .")
    return " ".join(limpo.split())[:60] or "projeto"


def _resolver_projeto(nome: str) -> Path | None:
    """Aceita caminho completo, nome de pasta ou pedaço do nome."""
    bruto = (nome or "").strip().strip('"')
    if not bruto:
        return None
    p = Path(bruto).expanduser()
    if p.is_dir():
        return p.resolve()

    raiz = _raiz_projetos()
    alvo = raiz / bruto
    if alvo.is_dir():
        return alvo.resolve()

    baixo = bruto.lower()
    if raiz.is_dir():
        candidatos = [d for d in raiz.iterdir() if d.is_dir() and baixo in d.name.lower()]
        if len(candidatos) == 1:
            return candidatos[0].resolve()
    return None


# ── ação ────────────────────────────────────────────────────────────────────

def vscode(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    nome = str(parameters.get("project") or "").strip()
    arquivo = str(parameters.get("file") or "").strip()
    linha = parameters.get("line")

    try:
        if acao in ("status", "situacao"):
            modos = [c[0] for c in _candidatos_code()]
            raiz = _raiz_projetos()
            qtd = len([d for d in raiz.iterdir() if d.is_dir()]) if raiz.is_dir() else 0
            if not modos:
                return ("O VS Code não está instalado (ou o comando 'code' não está no PATH). "
                        "Instale de code.visualstudio.com e marque 'Add to PATH'.")
            return (f"VS Code disponível ({Path(modos[0]).name}). "
                    f"Pasta de projetos: {raiz} — {qtd} projeto(s).")

        if acao in ("listar", "projetos"):
            raiz = _raiz_projetos()
            if not raiz.is_dir():
                return f"Ainda não existe pasta de projetos em {raiz}."
            nomes = sorted(d.name for d in raiz.iterdir() if d.is_dir())
            return ("Projetos: " + ", ".join(nomes)) if nomes else "Nenhum projeto ainda."

        if acao in ("abrir", "abrir_projeto", "open"):
            caminho = _resolver_projeto(nome)
            if caminho is None:
                return (f"Não achei o projeto '{nome}'. Diga 'quais projetos eu tenho' "
                        f"para eu listar os de {_raiz_projetos()}.")
            if arquivo:
                alvo = caminho / arquivo
                if not alvo.exists():
                    return f"O arquivo '{arquivo}' não existe em {caminho.name}."
                arg = f"{alvo}:{linha}" if str(linha or "").isdigit() else str(alvo)
                ok, frase = _abrir_no_code(arg)
                if ok:
                    return f"Abri {alvo.name} do projeto {caminho.name} no VS Code."
                return f"Encontrei {alvo.name} em {caminho}, {frase}."
            ok, frase = _abrir_no_code(str(caminho))
            if ok:
                return f"Abri o projeto {caminho.name} no VS Code."
            return f"O projeto {caminho.name} está em {caminho}, {frase}."

        if acao in ("novo_site", "criar_site", "site"):
            nome_ok = _nome_seguro(nome or "Meu Site")
            destino = _raiz_projetos() / nome_ok
            destino.mkdir(parents=True, exist_ok=True)
            (destino / "index.html").write_text(_SITE_HTML.format(nome=nome_ok), encoding="utf-8")
            (destino / "styles.css").write_text(_SITE_CSS, encoding="utf-8")
            (destino / "app.js").write_text(_SITE_JS, encoding="utf-8")
            (destino / "README.md").write_text(
                _LEIAME.format(nome=nome_ok, rodar=_RODAR_SITE), encoding="utf-8")
            ok, frase = _abrir_no_code(str(destino))
            return (f"Criei o site '{nome_ok}' em {destino} (index.html, styles.css, app.js). "
                    + ("Já abri no VS Code. " if ok else f"Não abri o editor: {frase}. ")
                    + "Para ver no navegador, abra o index.html.")

        if acao in ("novo_app", "criar_app", "app"):
            nome_ok = _nome_seguro(nome or "Meu App")
            destino = _raiz_projetos() / nome_ok
            destino.mkdir(parents=True, exist_ok=True)
            (destino / "main.py").write_text(_APP_PY, encoding="utf-8")
            (destino / "requirements.txt").write_text("", encoding="utf-8")
            (destino / "README.md").write_text(
                _LEIAME.format(nome=nome_ok, rodar=_RODAR_APP), encoding="utf-8")
            ok, frase = _abrir_no_code(str(destino))
            return (f"Criei o app '{nome_ok}' em {destino} (main.py, requirements.txt). "
                    + ("Já abri no VS Code." if ok else f"Não abri o editor: {frase}."))

        return ("Ações: abrir_projeto, novo_site, novo_app, listar, status. "
                "Diga, por exemplo: abre o projeto Padaria no VS Code.")
    except Exception as e:
        return f"Não consegui falar com o VS Code: {e}"


TOOL = {
    "name": "vscode",
    "description": (
        "VS CODE — abre projetos e arquivos no editor, e cria a base de um site ou de um app em Python. "
        "Use para 'abre o projeto X', 'abre o index.html na linha 40', 'cria um site chamado Y', "
        "'cria um app em Python chamado Z', 'quais projetos eu tenho'. Os projetos ficam em "
        "Desktop\\\\NexusProjects (a mesma pasta do dev_agent). Para um projeto com telas e lógica "
        "próprias, feito por IA, use dev_agent ou forge_app e depois abra aqui para editar."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "abrir_projeto | novo_site | novo_app | listar | status"},
            "project": {"type": "STRING", "description": "Nome do projeto (ou caminho completo)"},
            "file": {"type": "STRING", "description": "Arquivo dentro do projeto, ex: index.html"},
            "line": {"type": "INTEGER", "description": "Linha para posicionar o cursor (opcional)"},
        },
        "required": ["action"],
    },
    "handler": vscode,
}
