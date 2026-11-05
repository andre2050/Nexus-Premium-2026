# -*- coding: utf-8 -*-
"""GLOBO (02/11/2026): o servidor local que entrega a pagina do globo.

Por que um servidor, e nao abrir o arquivo direto: o motor do globo usa "workers"
e carrega JSON, e o navegador proibe os dois em pagina aberta de file://.

So' escuta em 127.0.0.1, numa porta escolhida na hora. Arquivo e' publico (so' tem
mapa e bandeira); tudo que MUDA alguma coisa pede o TOKEN, gerado a cada abertura,
e nao tem CORS: outro site aberto no PC nao consegue mandar comando para ca.

    pagina  <--- /api/eventos (SSE) ---  JARVIS: "mostra o Japao"
    pagina  ---> /api/resposta --------> quem pediu o comando recebe o resultado
    pagina  ---> /api/host ------------> a janela (fechar, tela cheia, navegador)
    pagina  ---> /api/log -------------> logs/globo.log (erro de cliente)

Tambem roda sozinho, so' para desenvolver:  python servidor.py --porta 8799
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import queue
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

RAIZ = Path(__file__).resolve().parent
WEB = RAIZ / "web"
LOG = RAIZ.parent / "logs" / "globo.log"
_LOG_MAX = 256 * 1024

_TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".wasm": "application/wasm",
    ".bin": "application/octet-stream",
    ".md": "text/plain; charset=utf-8",
}
# O que nunca muda entre uma abertura e outra pode ficar no cache do navegador.
_FIXOS = ("cesium/", "img/", "dados/")

# Unicos enderecos que a pagina pode pedir para abrir no navegador de verdade.
_EXTERNOS_OK = (
    "https://www.google.com/maps", "https://maps.google.com/",
    "https://pt.wikipedia.org/", "https://en.wikipedia.org/",
    "https://www.openstreetmap.org/", "https://www.geonames.org/",
    "https://www.naturalearthdata.com/", "https://www.esri.com/", "https://cesium.com/",
)


def registrar(linha: str) -> None:
    """Nunca derruba nada: sem log e' so' sem log."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > _LOG_MAX:
            LOG.replace(LOG.with_suffix(".log.1"))
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%d/%m %H:%M:%S')} {linha[:2000]}\n")
    except Exception:
        pass


class Globo:
    """O estado compartilhado entre o servidor, a janela e quem manda comando."""

    def __init__(self, config: dict | None = None, ao_host=None):
        self.token = secrets.token_urlsafe(24)
        self.config = config or {}
        self.ao_host = ao_host          # callable(acao, dados) -> dict, da janela
        self.andarilho = None           # globo/andar.py: as pernas do passeio
        self.pediu_parar = False        # botao PARAR da tela; o passeio confere
        self._assinantes: list[queue.Queue] = []
        self._respostas: dict[str, queue.Queue] = {}
        self._pendentes: list[dict] = []   # comando que chegou antes da pagina
        self._trava = threading.Lock()
        self.ultima_pagina = 0.0        # ultimo sinal de vida da pagina
        self.pagina_pronta = threading.Event()

    # ── pagina ────────────────────────────────────────────────────────────
    def assinar(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._trava:
            self._assinantes.append(q)
        self.ultima_pagina = time.monotonic()
        return q

    def desassinar(self, q: queue.Queue) -> None:
        with self._trava:
            if q in self._assinantes:
                self._assinantes.remove(q)

    def tem_pagina(self) -> bool:
        with self._trava:
            return bool(self._assinantes)

    def _entregar(self, evento: dict) -> None:
        with self._trava:
            for q in self._assinantes:
                q.put(evento)

    def marcar_pronta(self) -> None:
        """A pagina terminou de carregar: entrega o que estava esperando."""
        with self._trava:
            pendentes, self._pendentes = self._pendentes, []
        self.pagina_pronta.set()
        for ev in pendentes:
            self._entregar(ev)

    # ── comandos do JARVIS ────────────────────────────────────────────────
    def comando(self, acao: str, dados: dict | None = None, espera: float = 8.0) -> dict:
        ident = uuid.uuid4().hex
        evento = {"id": ident, "acao": acao, "dados": dados or {}}
        caixa: queue.Queue = queue.Queue(maxsize=1)
        with self._trava:
            self._respostas[ident] = caixa
            pronta = self.pagina_pronta.is_set() and bool(self._assinantes)
            if not pronta:
                self._pendentes.append(evento)
        if pronta:
            self._entregar(evento)
        try:
            return caixa.get(timeout=max(0.1, espera))
        except queue.Empty:
            return {"ok": False, "erro": "o globo nao respondeu a tempo"}
        finally:
            with self._trava:
                self._respostas.pop(ident, None)

    def responder(self, ident: str, dados: dict) -> None:
        with self._trava:
            caixa = self._respostas.get(ident)
        if caixa is not None:
            try:
                caixa.put_nowait(dados)
            except queue.Full:
                pass


def _criar_handler(globo: Globo):
    class Handler(BaseHTTPRequestHandler):
        server_version = "JarvisGlobo"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # sem console: roda em pythonw
            pass

        # ── utilidades ────────────────────────────────────────────────────
        def _host_ok(self) -> bool:
            # Protege contra "DNS rebinding": so' responde para quem pediu pelo
            # endereco local, nunca por um dominio que aponta para ca.
            h = (self.headers.get("Host") or "").split(":")[0].strip().lower()
            return h in ("127.0.0.1", "localhost")

        def _token_ok(self, q: dict) -> bool:
            dado = self.headers.get("X-Token") or (q.get("t") or [""])[0]
            return secrets.compare_digest(str(dado), globo.token)

        def _json(self, dados, codigo: int = 200) -> None:
            corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _corpo(self) -> dict:
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 1_000_000)
                return json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return {}

        # ── GET ───────────────────────────────────────────────────────────
        def do_GET(self):
            if not self._host_ok():
                return self._json({"erro": "host"}, 403)
            u = urlparse(self.path)
            caminho = unquote(u.path)
            if caminho == "/api/ping":
                return self._json({"ok": True, "pagina": globo.tem_pagina()})
            if caminho == "/api/config":
                return self._json(globo.config)
            if caminho == "/api/eventos":
                q = parse_qs(u.query)
                if not self._token_ok(q):
                    return self._json({"erro": "token"}, 403)
                return self._eventos()
            return self._arquivo(caminho)

        def do_HEAD(self):
            self.do_GET()

        def _arquivo(self, caminho: str) -> None:
            rel = caminho.lstrip("/") or "index.html"
            try:
                alvo = (WEB / rel).resolve()
                alvo.relative_to(WEB.resolve())     # nada de ../..
            except Exception:
                return self._json({"erro": "caminho"}, 403)
            if not alvo.is_file():
                return self._json({"erro": "nao existe"}, 404)
            tipo = _TIPOS.get(alvo.suffix.lower()) or mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
            try:
                corpo = alvo.read_bytes()
            except OSError:
                return self._json({"erro": "leitura"}, 500)
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            fixo = any(rel.startswith(p) for p in _FIXOS)
            self.send_header("Cache-Control", "public, max-age=2592000" if fixo else "no-cache")
            self.end_headers()
            if self.command != "HEAD":
                try:
                    self.wfile.write(corpo)
                except (BrokenPipeError, ConnectionError):
                    pass

        def _eventos(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            q = globo.assinar()
            try:
                self.wfile.write(b": oi\n\n")
                self.wfile.flush()
                while True:
                    try:
                        ev = q.get(timeout=5.0)
                        texto = "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
                        self.wfile.write(texto.encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": vivo\n\n")
                    self.wfile.flush()
                    globo.ultima_pagina = time.monotonic()
            except (BrokenPipeError, ConnectionError, OSError):
                pass
            finally:
                globo.desassinar(q)

        # ── POST ──────────────────────────────────────────────────────────
        def do_POST(self):
            if not self._host_ok():
                return self._json({"erro": "host"}, 403)
            u = urlparse(self.path)
            caminho = u.path
            q = parse_qs(u.query)
            if not self._token_ok(q):
                return self._json({"erro": "token"}, 403)
            dados = self._corpo()

            if caminho == "/api/cmd":
                try:
                    espera = float(dados.get("espera") or 8.0)
                except (TypeError, ValueError):
                    espera = 8.0
                r = globo.comando(str(dados.get("acao") or ""), dados.get("dados") or {}, min(espera, 60.0))
                return self._json(r)

            if caminho == "/api/resposta":
                globo.responder(str(dados.get("id") or ""), dados.get("dados") or {})
                return self._json({"ok": True})

            if caminho == "/api/pronta":
                globo.marcar_pronta()
                return self._json({"ok": True})

            if caminho == "/api/log":
                registrar(str(dados.get("linha") or "")[:1800])
                return self._json({"ok": True})

            if caminho == "/api/rua":
                acao = str(dados.get("acao") or "")
                if acao == "estado":
                    parar, globo.pediu_parar = globo.pediu_parar, False
                    return self._json({"ok": True, "parar": parar})
                a = globo.andarilho
                if a is None:
                    return self._json({"ok": False, "erro": "sem pernas"})
                if acao == "pos":
                    return self._json(a.posicao() or {"erro": "sem street view"})
                if acao == "seta":
                    return self._json({"ok": a.clicar_seta(str(dados.get("rotulo") or ""))})
                if acao == "chao":
                    return self._json({"ok": a.clicar_no_chao(float(dados.get("fracao") or 0.56))})
                if acao == "girar":
                    return self._json({"ok": a.girar(float(dados.get("graus") or 0))})
                if acao == "olhar":
                    return self._json({"ok": a.olhar(float(dados.get("graus") or 0))})
                if acao == "setas":
                    return self._json({"ok": True, "setas": a.setas()})
                return self._json({"erro": "nao existe"}, 404)

            if caminho == "/api/host":
                acao = str(dados.get("acao") or "")
                if acao == "passeio_parar":
                    globo.pediu_parar = True
                    return self._json({"ok": True})
                if acao == "externo":
                    url = str(dados.get("url") or "")
                    if not url.startswith(_EXTERNOS_OK):
                        return self._json({"ok": False, "erro": "endereco nao permitido"}, 403)
                if callable(globo.ao_host):
                    try:
                        return self._json(globo.ao_host(acao, dados) or {"ok": True})
                    except Exception as exc:
                        registrar(f"host {acao}: {exc}")
                        return self._json({"ok": False, "erro": str(exc)[:200]})
                return self._json({"ok": False, "erro": "sem janela"})

            return self._json({"erro": "nao existe"}, 404)

    return Handler


class _Servidor(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def handle_error(self, request, client_address):
        # A pagina fechando no meio de um pedido e' normal: nao e' erro de ninguem.
        import sys as _sys  # noqa: PLC0415
        exc = _sys.exc_info()[1]
        if not isinstance(exc, (ConnectionError, TimeoutError)):
            registrar(f"servidor: {type(exc).__name__}: {exc}")


def subir(globo: Globo, porta: int = 0) -> _Servidor:
    srv = _Servidor(("127.0.0.1", porta), _criar_handler(globo))
    threading.Thread(target=srv.serve_forever, name="globo-http", daemon=True).start()
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=8799)
    a = ap.parse_args()
    g = Globo({"idioma": "pt", "dev": True})
    g.token = "dev"
    s = _Servidor(("127.0.0.1", a.porta), _criar_handler(g))
    print(f"globo em http://127.0.0.1:{a.porta}/?t=dev", flush=True)
    s.serve_forever()
