# -*- coding: utf-8 -*-
"""Ferramenta `remote_media` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Print, tela ao vivo e webcam no celular, pelo Controle Remoto do NEXUS.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

import base64
import threading
import time

_AO_VIVO = {}          # "tela" | "camera" -> threading.Event (parar)


def _mandar(speak, tipo: str, jpeg: bytes, legenda: str) -> bool:
    import asyncio
    live = P.assistente(speak)
    dash = getattr(live, "_dashboard", None)
    loop = getattr(live, "_loop", None)
    if dash is None or loop is None or not hasattr(dash, "push_media"):
        return False
    msg = {"type": "image", "kind": tipo, "caption": legenda,
           "data": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}
    try:
        asyncio.run_coroutine_threadsafe(dash.push_media(msg), loop).result(timeout=10)
        return True
    except Exception:
        return False


def _foto_camera(indice: int = 0) -> bytes | None:
    try:
        import cv2
        cam = cv2.VideoCapture(indice, cv2.CAP_DSHOW)
        ok, quadro = cam.read()
        cam.release()
        if not ok:
            return None
        ok, buf = cv2.imencode(".jpg", quadro, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        return buf.tobytes() if ok else None
    except Exception:
        return None


def _ao_vivo(speak, tipo: str, parar: threading.Event) -> None:
    import cv2
    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW) if tipo == "camera" else None
    try:
        while not parar.is_set():
            if cam is not None:
                ok, quadro = cam.read()
                jpeg = cv2.imencode(".jpg", quadro, [int(cv2.IMWRITE_JPEG_QUALITY), 60])[1].tobytes() if ok else None
            else:
                jpeg = P.foto_da_tela_jpeg(55)[0]
            if jpeg and not _mandar(speak, tipo, jpeg, "ao vivo"):
                break
            parar.wait(1.2)
    finally:
        if cam is not None:
            cam.release()


def _rodar(parameters=None, player=None, speak=None):
    acao = str((parameters or {}).get("action") or "").strip().lower()
    live = P.assistente(speak)
    if getattr(live, "_dashboard", None) is None:
        return "O Controle Remoto nao esta ligado agora. Abra o Controle Remoto no NEXUS primeiro."
    if acao in ("screenshot", "print", "screen_capture", "send_screenshot"):
        jpeg = P.foto_da_tela_jpeg(75)[0]
        return ("Mandei o print da tela para o celular." if _mandar(speak, "tela", jpeg, "print da tela")
                else "Nao consegui mandar o print: o celular esta conectado ao Controle Remoto?")
    if acao in ("webcam_photo", "camera_photo", "webcam_snapshot", "photo"):
        jpeg = _foto_camera()
        if not jpeg:
            return "Nao consegui abrir a webcam."
        return "Mandei a foto da webcam para o celular." if _mandar(speak, "camera", jpeg, "webcam") else \
            "Nao consegui mandar a foto: o celular esta conectado?"
    for tipo, chaves in (("tela", ("screen", "tela")), ("camera", ("webcam", "camera"))):
        if any(c in acao for c in chaves):
            if any(x in acao for x in ("stop", "close", "parar", "fechar", "off")):
                ev = _AO_VIVO.pop(tipo, None)
                if ev:
                    ev.set()
                return f"Parei a transmissao da {'tela' if tipo == 'tela' else 'webcam'}."
            if tipo in _AO_VIVO:
                return "Ja esta transmitindo."
            ev = threading.Event()
            _AO_VIVO[tipo] = ev
            threading.Thread(target=_ao_vivo, args=(speak, tipo, ev), daemon=True,
                             name=f"remote-{tipo}").start()
            return f"Comecei a transmitir a {'tela' if tipo == 'tela' else 'webcam'} ao vivo para o celular."
    return f"Acao de midia desconhecida: {acao or '(vazia)'}"


TOOL = {'name': 'remote_media',
 'description': 'Sends a PC screenshot, opens/closes the PC screen live stream, or controls the '
                'webcam live view in the authenticated Remote Control dashboard. Use ONLY for '
                'media explicitly requested on the phone/Remote Control. For ordinary visual '
                'analysis use screen_process. Live screen and webcam remain active until their '
                'matching stop action is called.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING',
                                          'description': 'screenshot | screen_live_start | '
                                                         'screen_live_stop | webcam_start | '
                                                         'webcam_stop'}},
                'required': ['action']},
    "handler": _rodar,
}
