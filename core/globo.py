# -*- coding: utf-8 -*-
"""GLOBO (02/11/2026): a ponte entre o JARVIS e a janela do globo (globo/janela.py).

A janela roda em processo separado (o porque esta no janela.py). Daqui so' sai:
abrir, mandar comando e fechar. Nada aqui importa Qt nem carrega nada pesado: o
custo do globo so' existe enquanto ele esta aberto.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARQ_ESTADO = RAIZ / "config" / ".globo.json"
JANELA = RAIZ / "globo" / "janela.py"

_trava = threading.Lock()
_ultimo_abrir = 0.0
# Direto, sem proxy do sistema: e' o proprio PC falando com ele mesmo.
_abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def disponivel() -> bool:
    return JANELA.is_file()


def _pid_vivo(pid: int) -> bool:
    try:
        import psutil  # noqa: PLC0415
        return psutil.pid_exists(int(pid))
    except Exception:
        return True


def _estado() -> dict | None:
    try:
        dados = json.loads(ARQ_ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not dados.get("porta") or not _pid_vivo(dados.get("pid", 0)):
        try:
            ARQ_ESTADO.unlink()     # sobrou de um globo que caiu
        except OSError:
            pass
        return None
    return dados


def aberto() -> bool:
    """Barato de proposito: e' perguntado a cada frase falada."""
    return ARQ_ESTADO.exists() and _estado() is not None


def _post(caminho: str, corpo: dict, espera: float) -> dict:
    e = _estado()
    if not e:
        return {"ok": False, "erro": "o globo nao esta aberto"}
    req = urllib.request.Request(
        f"http://127.0.0.1:{e['porta']}{caminho}",
        data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Token": e["token"]},
        method="POST",
    )
    try:
        with _abridor.open(req, timeout=espera) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"ok": False, "erro": str(exc)[:160]}


def focar() -> None:
    """Traz o globo para a frente. No Windows, quem esta na frente tem de dar licenca."""
    e = _estado()
    if not e:
        return
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415
            ctypes.windll.user32.AllowSetForegroundWindow(int(e["pid"]))
        except Exception:
            pass
    _post("/api/host", {"acao": "focar"}, 2.0)


def abrir(geo: tuple | None = None, maximizada: bool = False, lugar: str = "", depois_foca: bool = True) -> bool:
    """Abre (ou traz para a frente). Devolve True se a janela esta de pe."""
    global _ultimo_abrir
    if aberto():
        if depois_foca:
            focar()
        return True
    if not disponivel():
        return False
    with _trava:
        if aberto():
            return True
        # Dois cliques seguidos nao abrem dois globos.
        if time.monotonic() - _ultimo_abrir < 6.0:
            return True
        _ultimo_abrir = time.monotonic()
        cmd = [sys.executable, str(JANELA), "--pai", str(os.getpid())]
        if geo:
            cmd += ["--geo", ",".join(str(int(v)) for v in geo)]
        if maximizada:
            cmd.append("--maximizada")
        if lugar:
            cmd += ["--lugar", str(lugar)]
        opcoes: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                        "cwd": str(JANELA.parent)}
        if sys.platform == "win32":
            opcoes["creationflags"] = 0x08000000      # CREATE_NO_WINDOW
        # O filho nao herda as bibliotecas do JARVIS: abre limpo.
        subprocess.Popen(cmd, **opcoes)
    return True


def _esperar_janela(segundos: float = 12.0) -> bool:
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        if aberto():
            return True
        time.sleep(0.12)
    return False


def comando(acao: str, dados: dict | None = None, espera: float = 12.0) -> dict:
    return _post("/api/cmd", {"acao": acao, "dados": dados or {}, "espera": espera}, espera + 2.0)


def existe(lugar: str, so_grandes: bool = False) -> bool:
    """A frase ambigua ("mostra o Japao") so' vira comando se o lugar existir de verdade."""
    r = comando("tem_lugar", {"lugar": lugar, "so_grandes": so_grandes}, 1.5)
    return bool(r.get("existe"))


def fechar() -> None:
    if not ARQ_ESTADO.exists():
        return
    _post("/api/host", {"acao": "fechar"}, 2.0)


def pedir(pedido: dict, ouvido: str = "", geo: tuple | None = None, maximizada: bool = False) -> dict:
    """Executa um pedido de `core.globo_voz` (ou da ferramenta do cerebro)."""
    pedido = dict(pedido)
    acao = str(pedido.pop("acao", ""))
    pedido.pop("so_se_existir", None)
    pedido.pop("so_grandes", None)
    if acao == "fechar":
        fechar()
        return {"ok": True}
    estava_aberto = aberto()
    if not estava_aberto:
        if not abrir(geo, maximizada):
            return {"ok": False, "erro": "o globo nao esta instalado"}
        if not _esperar_janela():
            return {"ok": False, "erro": "o globo nao abriu"}
    if acao == "abrir":
        if estava_aberto:
            focar()
        return {"ok": True}
    if ouvido:
        # Aparece na tela na hora: se a transcricao errou, o dono ve o que foi entendido.
        threading.Thread(target=comando, args=("ouvi", {"texto": ouvido}, 1.0), daemon=True).start()
    # A primeira abertura carrega o mundo inteiro: o comando espera na fila do servidor.
    # Aberto ha pouco tambem (PC lento leva dezenas de segundos): quem responde antes, nao espera nada.
    espera = 45.0
    return comando(acao, pedido, espera)
