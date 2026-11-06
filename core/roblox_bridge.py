"""Ponte local entre o NEXUS e o Roblox Studio.

O Roblox Studio não aceita comandos de fora: nada pode escrever um script dentro
de um lugar aberto no Studio a não ser que rode DENTRO dele. Então a conversa é
ao contrário — o plugin (assets/roblox/NexusBridge.lua) roda dentro do Studio e
pergunta ao NEXUS, a cada segundo, se há trabalho; o NEXUS responde e o plugin
executa, devolvendo o resultado.

Esta ponte é esse lado do NEXUS:

  • escuta SÓ em 127.0.0.1 (nunca na rede) numa porta própria;
  • exige um token que o instalador grava dentro do plugin;
  • guarda uma fila de comandos em memória, com prazo, e registra o resultado
    de cada um para você poder dizer "deu certo?".

Endpoints (consumidos pelo plugin):
  GET  /ping                      → está vivo?
  GET  /next?token=...            → próximo comando (ou {"comando": null})
  POST /result?token=...          → resultado da execução
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent.parent
STATE_FILE = BASE / "memory" / "roblox_bridge.json"
PORT_PADRAO = 8899
VALIDADE_S = 120          # comando não aplicado em 2 min é descartado
MAX_RESULTADOS = 40

_lock = threading.Lock()
_fila: list[dict] = []
_resultados: list[dict] = []
_servidor: ThreadingHTTPServer | None = None
_thread: threading.Thread | None = None
_seq = 0


# ── estado persistido (token e porta) ───────────────────────────────────────
def estado() -> dict:
    """Token e porta, criados na primeira vez e reaproveitados depois."""
    try:
        d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict) and d.get("token"):
            d.setdefault("porta", PORT_PADRAO)
            return d
    except Exception:
        pass
    d = {"token": secrets.token_hex(16), "porta": PORT_PADRAO, "criado": time.time()}
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return d


def _token() -> str:
    return estado()["token"]


# ── fila ────────────────────────────────────────────────────────────────────
def enfileirar(tipo: str, dados: dict) -> int:
    """Coloca um comando na fila. Devolve o id."""
    global _seq
    with _lock:
        _seq += 1
        cmd = {"id": _seq, "tipo": tipo, "dados": dados or {}, "criado": time.time()}
        _fila.append(cmd)
        # descarta o que ficou velho demais sem ser pego
        agora = time.time()
        _fila[:] = [c for c in _fila if agora - c["criado"] <= VALIDADE_S]
        return _seq


def pendentes() -> list[dict]:
    with _lock:
        return list(_fila)


def resultados() -> list[dict]:
    with _lock:
        return list(_resultados)


def _pegar_proximo() -> dict | None:
    with _lock:
        agora = time.time()
        while _fila:
            cmd = _fila.pop(0)
            if agora - cmd["criado"] <= VALIDADE_S:
                return cmd
        return None


def _registrar_resultado(corpo: dict) -> None:
    with _lock:
        _resultados.append({
            "id": corpo.get("id"),
            "ok": bool(corpo.get("ok")),
            "mensagem": str(corpo.get("mensagem") or "")[:600],
            "quando": time.time(),
        })
        del _resultados[:-MAX_RESULTADOS]


# ── HTTP ────────────────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):        # silêncio: o log do NEXUS é outro
        pass

    def _json(self, dados: dict, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(corpo)

    def _token_ok(self) -> bool:
        q = parse_qs(urlparse(self.path).query)
        return (q.get("token") or [""])[0] == _token()

    def do_GET(self):
        rota = urlparse(self.path).path
        if rota == "/ping":
            return self._json({"ok": True, "nexus": "6.1.8"})
        if rota == "/next":
            if not self._token_ok():
                return self._json({"erro": "token inválido"}, 403)
            cmd = _pegar_proximo()
            return self._json({"comando": cmd})
        return self._json({"erro": "rota desconhecida"}, 404)

    def do_POST(self):
        rota = urlparse(self.path).path
        if rota != "/result":
            return self._json({"erro": "rota desconhecida"}, 404)
        if not self._token_ok():
            return self._json({"erro": "token inválido"}, 403)
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(tamanho) or b"{}")
        except Exception:
            return self._json({"erro": "JSON inválido"}, 400)
        _registrar_resultado(corpo if isinstance(corpo, dict) else {})
        return self._json({"ok": True})


# ── ciclo de vida ───────────────────────────────────────────────────────────
def ativa() -> bool:
    return _servidor is not None and _thread is not None and _thread.is_alive()


def iniciar(porta: int | None = None) -> str:
    """Sobe a ponte (idempotente). Devolve uma frase para o usuário."""
    global _servidor, _thread
    if ativa():
        return f"A ponte já está ativa na porta {_servidor.server_port}."
    porta = int(porta or estado().get("porta") or PORT_PADRAO)
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", porta), _Handler)
    except OSError as e:
        return f"Não consegui abrir a porta {porta} ({e}). Feche o outro programa que a usa ou mude a porta."
    srv.daemon_threads = True
    _servidor = srv
    _thread = threading.Thread(target=srv.serve_forever, name="nexus-roblox-bridge", daemon=True)
    _thread.start()
    return f"Ponte ativa em http://127.0.0.1:{porta} (o plugin do Studio busca comandos a cada segundo)."


def parar() -> str:
    global _servidor, _thread
    if not ativa():
        return "A ponte já estava parada."
    try:
        _servidor.shutdown()
        _servidor.server_close()
    except Exception:
        pass
    _servidor = None
    _thread = None
    return "Ponte encerrada."


def porta_atual() -> int | None:
    return _servidor.server_port if _servidor is not None else None
