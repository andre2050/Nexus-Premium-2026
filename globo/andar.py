# -*- coding: utf-8 -*-
"""ANDAR NO STREET VIEW (02/11/2026): as pernas do passeio guiado.

O Street View incorporado nao tem comando nenhum por fora: e' uma pagina do Google.
Mas a janela e' nossa: pela porta de depuracao do proprio Chromium (so' em 127.0.0.1,
porta sorteada a cada abertura) da para apertar a seta para cima de verdade, que anda
com a transicao suave do Google, e ler o link "Ver no Google Maps", que traz a posicao
exata a cada passo. Testado na Av. Paulista: 2300 -> 2306 -> 2310 -> 2350 -> 2378.

Se o Google mudar a pagina, `posicao` passa a devolver None e o passeio avisa e para.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request

_abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# .../maps/@-23.556862,-46.6614427,0a,73.7y,313.69h,90t/... : posicao e rumo da camera.
_RE_LINK = re.compile(r"maps/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),")
_RE_RUMO = re.compile(r",(\d+(?:\.\d+)?)h,")
_RE_TILT = re.compile(r",(\d+(?:\.\d+)?)t[/?]")
_RE_PANO = re.compile(r"!1s([\w-]+)!2e")

_LER = """(()=>{
  const links=[...document.querySelectorAll('a')].map(a=>a.href||'').filter(h=>h.includes('/maps/@'));
  const curto=document.querySelector('.gm-iv-short-address-description');
  const sub=document.querySelector('.gm-iv-long-address-description');
  const sem=(document.body&&document.body.innerText||'').slice(0,200);
  return JSON.stringify({links,rua:curto?curto.textContent.trim():'',lugar:sub?sub.textContent.trim():'',texto:sem,foco:document.hasFocus()});
})()"""

_CORPO = """(()=>{const r=document.querySelector('#rua-corpo').getBoundingClientRect();
return JSON.stringify({x:r.x,y:r.y,l:r.width,a:r.height})})()"""


SINAL_INCLINAR = -1.0     # medido em teste_tilt: arrastar para cima baixa a camera


class _Sessao:
    def __init__(self, url: str):
        from websockets.sync.client import connect  # noqa: PLC0415
        self.ws = connect(url, max_size=None, open_timeout=6, close_timeout=1)
        self.n = 0

    def pede(self, metodo: str, **params) -> dict:
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": metodo, "params": params}))
        fim = time.monotonic() + 8.0
        while True:
            r = json.loads(self.ws.recv(timeout=max(0.1, fim - time.monotonic())))
            if r.get("id") == self.n:
                if "error" in r:
                    raise RuntimeError(str(r["error"])[:200])
                return r.get("result", {})

    def fechar(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


class Andarilho:
    def __init__(self, porta: int):
        self.porta = porta
        self._trava = threading.Lock()
        self._pagina: _Sessao | None = None
        self._frame_ses: _Sessao | None = None   # navegador comum: o quadro do Google e' outro alvo
        self._frame_id = ""
        self._ctx = 0

    # ── ligacao ───────────────────────────────────────────────────────────
    def _alvos(self) -> list:
        with _abridor.open(f"http://127.0.0.1:{self.porta}/json", timeout=3) as r:
            return json.load(r)

    def _ligar(self) -> None:
        if self._pagina is not None:
            return
        pagina = [a for a in self._alvos() if a.get("type") == "page" and "127.0.0.1" in a.get("url", "")]
        if not pagina:
            raise RuntimeError("pagina do globo nao encontrada")
        self._pagina = _Sessao(pagina[0]["webSocketDebuggerUrl"])
        self._pagina.pede("Page.enable")
        self._pagina.pede("Runtime.enable")

    def _largar(self) -> None:
        for s in (self._pagina, self._frame_ses):
            if s is not None:
                s.fechar()
        self._pagina = None
        self._frame_ses = None
        self._frame_id = ""
        self._ctx = 0

    def _quadro_do_google(self):
        """Devolve o id do quadro do Street View, ou "" se ele nao esta aberto."""
        def achar(no):
            f = no["frame"]
            if "google.com/maps/embed" in f.get("url", ""):
                return f["id"]
            for filho in no.get("childFrames", []):
                r = achar(filho)
                if r:
                    return r
            return ""
        return achar(self._pagina.pede("Page.getFrameTree")["frameTree"])

    def _avaliar_no_google(self, js: str):
        # Edge/Chrome: o quadro de outro site e' um alvo separado, que nem aparece na
        # arvore da pagina. No Chromium do Qt ele mora junto com a pagina.
        alvo = [a for a in self._alvos() if a.get("type") == "iframe" and "maps/embed" in a.get("url", "")]
        if alvo:
            url = alvo[0]["webSocketDebuggerUrl"]
            if self._frame_id != url or self._frame_ses is None:
                if self._frame_ses is not None:
                    self._frame_ses.fechar()
                self._frame_ses = _Sessao(url)
                self._frame_id = url
            r = self._frame_ses.pede("Runtime.evaluate", expression=js, returnByValue=True)
            return r.get("result", {}).get("value")
        if self._frame_ses is not None:
            self._frame_ses.fechar()
            self._frame_ses = None
            self._frame_id = ""
        fid = self._quadro_do_google()
        if not fid:
            return None
        if fid != self._frame_id or not self._ctx:
            r = self._pagina.pede("Page.createIsolatedWorld", frameId=fid, worldName="jarvis")
            self._frame_id = fid
            self._ctx = r.get("executionContextId", 0)
        r = self._pagina.pede("Runtime.evaluate", expression=js, contextId=self._ctx, returnByValue=True)
        return r.get("result", {}).get("value")

    def _corpo(self) -> dict:
        r = self._pagina.pede("Runtime.evaluate", expression=_CORPO, returnByValue=True)
        return json.loads(r["result"]["value"])

    def _com_ligacao(self, func, *args):
        with self._trava:
            for tentativa in (1, 2):
                try:
                    self._ligar()
                    return func(*args)
                except Exception:
                    self._largar()
                    if tentativa == 2:
                        return None
        return None

    # ── o que o passeio usa ───────────────────────────────────────────────
    def _posicao(self):
        bruto = self._avaliar_no_google(_LER)
        if not bruto:
            return None
        d = json.loads(bruto)
        for link in d.get("links", []):
            m = _RE_LINK.search(link)
            if m:
                p = _RE_PANO.search(link)
                h = _RE_RUMO.search(link)
                inc = _RE_TILT.search(link)
                return {"lat": float(m.group(1)), "lon": float(m.group(2)), "rua": d.get("rua", ""),
                        "lugar": d.get("lugar", ""), "pano": p.group(1) if p else "", "foco": d.get("foco", False),
                        "h": float(h.group(1)) if h else None, "t": float(inc.group(1)) if inc else None}
        return {"sem_imagem": True} if "No Street View" in d.get("texto", "") or "Street View" in d.get("texto", "")[:40] else None

    def posicao(self):
        return self._com_ligacao(self._posicao)

    def _setas(self) -> list:
        """As setas da rua aqui: ["Go Northwest, Av. Paulista", ...]. Elas dizem a direcao e o nome."""
        js = """JSON.stringify([...document.querySelectorAll('[aria-label]')].map(x=>x.getAttribute('aria-label'))
            .filter(t=>/^(go |ir |siga |v[aá] )/i.test(t)))"""
        bruto = self._avaliar_no_google(js)
        return json.loads(bruto) if bruto else []

    def setas(self) -> list:
        return self._com_ligacao(self._setas) or []

    def _clicar_seta(self, rotulo: str) -> bool:
        # ANDAR PELA SETA, POR DENTRO DA PAGINA (02/11/2026). A primeira versao apertava a
        # seta do teclado, que precisa de foco, e para ter foco clicava no alto da imagem:
        # cada clique inclinava a camera para cima, e com a janela sem foco era a cada passo.
        js = """(()=>{const e=[...document.querySelectorAll('[aria-label]')].find(x=>x.getAttribute('aria-label')===%s);
          if(!e) return false;
          for(const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
            e.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window}));
          return true})()""" % json.dumps(rotulo)
        return bool(self._avaliar_no_google(js))

    def clicar_seta(self, rotulo: str) -> bool:
        return bool(self._com_ligacao(self._clicar_seta, rotulo))

    def _clicar_no_chao(self, fracao: float) -> bool:
        """Clica no chao a frente, na altura `fracao` do quadro: o Street View anda ate la' com
        a mesma transicao da seta. E' o que atravessa um cruzamento que nao tem seta."""
        c = self._corpo()
        x = c["x"] + c["l"] * 0.5
        y = c["y"] + c["a"] * float(fracao)
        p = self._pagina
        p.pede("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        time.sleep(0.2)     # parado em cima, ele descobre onde e' o chao
        p.pede("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
        time.sleep(0.05)
        p.pede("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
        # Tira da imagem o circulo que marca o chao.
        p.pede("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=c["y"] + 2)
        return True

    def clicar_no_chao(self, fracao: float) -> bool:
        return bool(self._com_ligacao(self._clicar_no_chao, fracao))

    def _olhar(self, alvo: float, horizonte: float = 90.0) -> bool:
        """Vira ate o rumo exato e deixa a camera na altura do horizonte, conferindo:
        arrasta, le o rumo e a inclinacao que o proprio Street View informa, e corrige."""
        for _ in range(5):
            bruto = self._posicao()
            if not bruto or bruto.get("h") is None:
                return False
            erro = (float(alvo) - bruto["h"] + 540) % 360 - 180
            erro_t = (float(bruto["t"]) - horizonte) if bruto.get("t") is not None else 0.0
            if abs(erro) < 4 and abs(erro_t) < 3:
                return True
            if abs(erro) >= 4:
                self._girar(erro)
            if abs(erro_t) >= 3:
                self._inclinar(erro_t)
            time.sleep(0.3)
        return True

    def olhar(self, alvo: float) -> bool:
        return bool(self._com_ligacao(self._olhar, alvo))

    def _inclinar(self, graus: float) -> None:
        """Positivo = baixa a camera (ela esta olhando para cima demais)."""
        c = self._corpo()
        py = float(graus) * c["a"] / 66.0 * SINAL_INCLINAR
        p = self._pagina
        x = c["x"] + c["l"] * 0.5
        y0 = c["y"] + c["a"] * 0.5 - py / 2
        p.pede("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y0)
        p.pede("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y0, button="left", clickCount=1)
        for i in range(1, 11):
            p.pede("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y0 + py * i / 10, button="left", buttons=1)
            time.sleep(0.018)
        p.pede("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y0 + py, button="left", clickCount=1)

    def _girar(self, graus: float) -> bool:
        """Arrasta a imagem, como quem olha para o lado. Positivo = para a direita."""
        c = self._corpo()
        # Medido: 437 px num quadro de 808 de altura viraram 35,55 graus.
        px = -float(graus) * c["a"] / 66.0
        limite = c["l"] * 0.42
        p = self._pagina
        # Alto da imagem: longe das setas do chao, que andariam em vez de girar.
        y = c["y"] + c["a"] * 0.30
        restante = px
        while abs(restante) > 1:
            d = max(-limite, min(limite, restante))
            x0 = c["x"] + c["l"] / 2 - d / 2
            p.pede("Input.dispatchMouseEvent", type="mouseMoved", x=x0, y=y)
            p.pede("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y, button="left", clickCount=1)
            fatias = 18
            for i in range(1, fatias + 1):
                p.pede("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + d * i / fatias, y=y,
                       button="left", buttons=1)
                time.sleep(0.022)
            p.pede("Input.dispatchMouseEvent", type="mouseReleased", x=x0 + d, y=y, button="left", clickCount=1)
            restante -= d
        return True

    def girar(self, graus: float) -> bool:
        return bool(self._com_ligacao(self._girar, graus))
