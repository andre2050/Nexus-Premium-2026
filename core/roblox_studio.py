"""Descoberta e controle do Roblox Studio.

Cuida do que é específico do Studio nesta máquina: achar a instalação, instalar
o plugin da ponte em %LOCALAPPDATA%\\Roblox\\Plugins e abrir um lugar (.rbxl).
Nada aqui escreve dentro do jogo — isso é o plugin que faz, do lado de dentro.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PLUGIN_FONTE = BASE / "assets" / "roblox" / "NexusBridge.lua"


def _localappdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def pasta_plugins() -> Path:
    """Onde o Studio procura plugins locais (dá para sobrescrever por env)."""
    env = os.environ.get("NEXUS_ROBLOX_PLUGINS")
    if env:
        return Path(env)
    return _localappdata() / "Roblox" / "Plugins"


def executavel() -> Path | None:
    """RobloxStudioBeta.exe, procurando nas versões instaladas."""
    candidatos: list[Path] = []
    base = _localappdata() / "Roblox" / "Versions"
    if base.is_dir():
        for versao in sorted(base.iterdir(), reverse=True):
            exe = versao / "RobloxStudioBeta.exe"
            if exe.exists():
                candidatos.append(exe)
    for raiz in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")):
        if raiz:
            for sub in ("Roblox", "Roblox Studio"):
                p = Path(raiz) / sub / "RobloxStudioBeta.exe"
                if p.exists():
                    candidatos.append(p)
    return candidatos[0] if candidatos else None


def instalado() -> bool:
    return executavel() is not None or sys.platform != "win32" and _mac_instalado()


def _mac_instalado() -> bool:
    return Path("/Applications/RobloxStudio.app").exists()


def plugin_instalado() -> Path | None:
    destino = pasta_plugins() / "NexusBridge.lua"
    return destino if destino.exists() else None


def instalar_plugin(porta: int, token: str) -> tuple[bool, str]:
    """Grava o plugin (com porta e token já embutidos) na pasta de plugins."""
    if not PLUGIN_FONTE.exists():
        return False, "o arquivo do plugin não veio no pacote (assets/roblox/NexusBridge.lua)"
    try:
        texto = PLUGIN_FONTE.read_text(encoding="utf-8")
    except OSError as e:
        return False, f"não consegui ler o plugin: {e}"

    conteudo = texto.replace("__PORTA__", str(porta)).replace("__TOKEN__", token)
    destino = pasta_plugins() / "NexusBridge.lua"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
    except OSError as e:
        return False, f"não consegui gravar em {destino}: {e}"
    return True, str(destino)


def abrir(lugar: str | None = None) -> tuple[bool, str]:
    """Abre o Studio (com um lugar, se indicado)."""
    if sys.platform == "darwin" and Path("/Applications/RobloxStudio.app").exists():
        cmd = ["open", "-a", "RobloxStudio", str(Path(lugar).expanduser())] if lugar else ["open", "-a", "RobloxStudio"]
        try:
            subprocess.Popen(cmd)
            return True, "abri o Roblox Studio"
        except Exception as e:
            return False, f"não consegui abrir o Studio: {e}"

    exe = executavel()
    if exe is None:
        return False, ("não achei o Roblox Studio instalado (procurei em "
                       "%LOCALAPPDATA%\\Roblox\\Versions). Instale em roblox.com/create.")
    cmd = [str(exe)]
    if lugar:
        alvo = Path(lugar).expanduser()
        if not alvo.exists():
            return False, f"o lugar '{lugar}' não existe"
        cmd.append(str(alvo))
    try:
        subprocess.Popen(cmd, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return False, f"não consegui abrir o Studio: {e}"
    return True, "abri o Roblox Studio"


def status() -> dict:
    exe = executavel()
    plugin = plugin_instalado()
    return {
        "instalado": instalado(),
        "executavel": str(exe) if exe else "",
        "plugin": str(plugin) if plugin else "",
        "pasta_plugins": str(pasta_plugins()),
    }
