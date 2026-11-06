"""Nexus Premium 2026 — os núcleos do hub (HUD): reator e mais dez formatos.

Cada núcleo é montado com três peças desenhadas (assets/nucleo/<id>/*.png,
fundo preto, 800 px, centro no centro exato da imagem):

    anel_externo.png   o anel de fora — gira devagar
    anel_interno.png   o anel de dentro — gira para o outro lado
    energia.png        a energia do meio — pulsa com cada sílaba da voz

As peças são somadas como LUZ (CompositionMode_Plus): o preto não soma nada,
então não há quadrado nem precisa de transparência. A arte vem do JARVIS (em
azul ciano); o que muda de um núcleo para o outro é a arte e o JEITO DE MEXER:

    reator ...... giro contínuo, o clássico
    hexagono .... a moldura salta 60° a cada sílaba (com estalo)
    prisma ...... o triângulo de dentro salta 120°
    cubo ........ a moldura salta 90° e a energia gira em 3D
    iris ........ as lâminas abrem com a voz e voltam ao soltar
    engrenagem .. os dois anéis engrenados, rastro quando acelera
    atomo ....... três órbitas com elétrons que deixam rastro
    mandala ..... respira devagar, pétalas girando em sentidos opostos
    espectro .... barras em volta do anel, movidas pelo áudio real
    vortice ..... redemoinho ao contrário, rastro de giro rápido

Cores pelo estado: falando/ocioso = a arte original (azul); ouvindo = verde;
pensando = dourado; mudo = vermelho apagado e quase parado. Sem a arte (pasta
apagada), o núcleo cai no orbe clássico — nunca quebra a janela.

Mesma assinatura dos visuais de hud_ultra.py: f(cv, p, W, H, cx, cy, R, main, acc, amp).
"""
from __future__ import annotations

import math
import time
from pathlib import Path

from PyQt6.QtGui import QImage, QPolygonF

from ._qt import *  # noqa: F401,F403
from ._base import C, qcol  # noqa: F401

_PASTA = Path(__file__).resolve().parent.parent / "assets" / "nucleo"
_PECAS = ("anel_externo", "anel_interno", "energia")

# id -> (ícone, nome, descrição, pasta (None = reator), r_int, r_en, extras)
# r_int / r_en: raio do anel de dentro e da energia em relação ao de fora
# (medidos no furo de cada arte pelo JARVIS, 13/10/2026).
_NUCLEOS: dict = {
    "reator":     ("◎", "Reator", "Reator de energia: anéis que giram e energia que pulsa com a voz",
                   None, 0.555, 0.40, {"onda": 0, "centro_int": (0.0, -0.0219)}),
    "hexagono":   ("⬡", "Hexágono", "Moldura hexagonal que salta a cada sílaba",
                   "hexagono", 0.565, 0.48, {"onda": 6, "passo": 60.0}),
    "prisma":     ("△", "Prisma", "Prisma triangular que gira aos saltos",
                   "prisma", 0.50, 0.45, {"onda": 3, "passo_int": 120.0}),
    "cubo":       ("◇", "Cubo", "Cubo que salta 90° e gira em 3D",
                   "cubo", 0.45, 0.40, {"onda": 4, "passo": 90.0}),
    "iris":       ("◉", "Íris", "Íris mecânica que abre com a voz",
                   "iris", 0.46, 0.38, {"onda": 0}),
    "engrenagem": ("⚙", "Engrenagem", "Engrenagens acopladas que aceleram com a voz",
                   "engrenagem", 0.49, 0.42, {"rastro": True}),
    "atomo":      ("⚛", "Átomo", "Núcleo atômico com três órbitas de elétrons",
                   "atomo", 0.42, 0.34, {"orbitas": (0.77, 0.25, (90.0, 30.0, 150.0))}),
    "mandala":    ("✺", "Mandala", "Mandala de luz que respira e gira em camadas",
                   "mandala", 0.42, 0.40, {"onda": 0}),
    "espectro":   ("✹", "Espectro", "Anel de espectro movido pelo áudio real",
                   "espectro", 0.55, 0.48, {"barras": 72}),
    "vortice":    ("🌀", "Vórtice", "Redemoinho de energia com rastro de giro",
                   "vortice", 0.47, 0.40, {"rastro": True, "sentido": -1.0}),
}

_ARTE: dict = {}          # (arquivo) -> QPixmap original (800 px)
_CACHE: dict = {}         # (id, peça, diâmetro, tinta) -> QPixmap pronto
_CACHE_MAX = 12


# ── arte ─────────────────────────────────────────────────────────────────────
def _arquivo(nid: str, peca: str) -> Path:
    pasta = _NUCLEOS[nid][3]
    proprio = (_PASTA / pasta / f"{peca}.png") if pasta else None
    if proprio is not None and proprio.exists():
        return proprio
    return _PASTA / f"{peca}.png"         # a do reator: nunca falta peça


def tem_arte() -> bool:
    return all((_PASTA / f"{p}.png").exists() for p in _PECAS)


def _original(arq: Path) -> QPixmap | None:
    px = _ARTE.get(str(arq))
    if px is None:
        px = QPixmap(str(arq))
        if px.isNull():
            return None
        _ARTE[str(arq)] = px
    return px


def _tingir(px: QPixmap, cor: QColor) -> QPixmap:
    """A arte em tons de cinza multiplicada pela cor (o preto continua preto)."""
    img = px.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    img = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    g = QPainter(img)
    g.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
    g.fillRect(img.rect(), cor)
    g.end()
    return QPixmap.fromImage(img)


def _peca(nid: str, peca: str, diam: int, tinta: str | None) -> QPixmap | None:
    """A peça no tamanho máximo do quadro (o resto é escala do QPainter)."""
    diam = max(16, int(diam) // 8 * 8)            # degraus de 8 px: menos refazer
    chave = (nid, peca, diam, tinta)
    px = _CACHE.get(chave)
    if px is not None:
        return px
    orig = _original(_arquivo(nid, peca))
    if orig is None:
        return None
    px = orig.scaled(diam, diam, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
    if tinta:
        px = _tingir(px, QColor(tinta))
    while len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[chave] = px
    return px


# ── movimento ────────────────────────────────────────────────────────────────
def _estalo(t: float) -> float:
    """0 → 1 passando um pouco do fim e voltando: o estalo suave do salto."""
    t = min(1.0, max(0.0, t)) - 1.0
    return 1.0 + 2.2 * t * t * t + 1.2 * t * t


class _Saltos:
    """Giro aos saltos: cada dar() anda `graus` em `dur` segundos."""

    def __init__(self, graus: float, dur: float = 0.34):
        self.graus, self.dur = graus, dur
        self.de = self.para = 0.0
        self.t = 1.0
        self.desde = 9.0

    def dar(self, sentido: float = 1.0) -> None:
        self.de = self.valor()
        self.para += self.graus * sentido
        self.t, self.desde = 0.0, 0.0

    def andar(self, dt: float) -> None:
        self.desde += dt
        if self.t < 1.0:
            self.t = min(1.0, self.t + dt / self.dur)

    def valor(self) -> float:
        if self.t >= 1.0:
            return self.para
        return self.de + (self.para - self.de) * _estalo(self.t)


class _Motor:
    """Ângulos, escalas e efeitos de um núcleo, quadro a quadro."""

    def __init__(self, nid: str):
        self.nid = nid
        self.ext = self.int = self.en = self.en2 = 0.0
        self.esc_ext = self.esc_int = 1.0
        self.tam = 0.86           # parado fica menor; a voz faz crescer
        self.pulso = 0.0          # salta a cada sílaba, cai rápido
        self.lento = 0.0          # envelope lento da fala
        self.sx_en = 1.0          # largura da energia (giro 3D do cubo)
        self.rastro = 0.0         # graus entre as cópias do rastro
        self.ondas: list[float] = []
        self.eletrons = [0.0, 2.1, 4.2]
        self.fase = 0.0
        self._vale = 0.0
        self._desde_sil = 9.0
        self._t = time.monotonic()
        extras = _NUCLEOS[nid][6]
        self._saltos = _Saltos(float(extras.get("passo", 60.0)))
        self._saltos_int = _Saltos(float(extras.get("passo_int", 120.0)), 0.45)
        self.sentido = float(extras.get("sentido", 1.0))

    def passo(self, modo: str, amp: float) -> None:
        agora = time.monotonic()
        dt = max(0.004, min(0.08, agora - self._t))
        self._t = agora
        self.fase += dt
        v = amp if modo in ("fala", "ouve") else 0.0

        # sílaba = subida rápida do volume
        self._desde_sil += dt
        silaba = False
        self._vale = min(self._vale, v)
        if v - self._vale > 0.18 and self._desde_sil > 0.14:
            silaba, self._vale, self._desde_sil = True, v, 0.0
            self.pulso = min(1.0, self.pulso + 0.55 + 0.6 * v)
            if _NUCLEOS[self.nid][6].get("onda") is not None and len(self.ondas) < 6:
                self.ondas.append(agora)
        if v > self._vale + 0.05:
            pass
        else:
            self._vale = v
        self.pulso *= 0.90
        self.lento += (v - self.lento) * (0.10 if v > self.lento else 0.04)
        alvo_tam = (0.86 + 0.22 * self.lento + 0.03 * math.sin(self.fase * 1.4)) if modo != "mudo" else 0.80
        self.tam += (alvo_tam - self.tam) * 0.18
        self.ondas = [t for t in self.ondas if agora - t < 1.4]

        # velocidades base (graus/s): externo, interno, energia, 2ª energia
        if modo == "fala":
            vel = (10 + 40 * v, -(22 + 90 * v), 25 + 60 * v, -(40 + 80 * v))
        elif modo == "ouve":
            vel = (8 + 20 * v, -(18 + 40 * v), 20, -32)
        elif modo == "pensa":
            vel = (14, -120, 40, -70)
        elif modo == "mudo":
            vel = (2, -4, 4, -6)
        else:
            vel = (6, -14, 18, -28)
        s = self.sentido
        self.ext = (self.ext + vel[0] * dt * s) % 360.0
        self.int = (self.int + vel[1] * dt * s) % 360.0
        self.en = (self.en + vel[2] * dt * s) % 360.0
        self.en2 = (self.en2 + vel[3] * dt * s) % 360.0
        self.esc_ext = self.esc_int = 1.0
        self.sx_en = 1.0
        self.rastro = 0.0

        mexer = getattr(self, "_" + self.nid, None)
        if mexer is not None:
            mexer(dt, modo, v, silaba)

    # cada núcleo mexe do seu jeito ------------------------------------------
    def _hexagono(self, dt, modo, v, silaba):
        sl = self._saltos
        sl.andar(dt)
        if silaba and sl.desde > 0.2:
            sl.dar()
        elif modo not in ("fala", "mudo") and sl.desde > (0.9 if modo == "pensa" else 4.0):
            sl.dar()
        self.ext = sl.valor()
        self.esc_ext = 1.0 + 0.04 * max(0.0, 1.0 - sl.t)

    def _cubo(self, dt, modo, v, silaba):
        self._hexagono(dt, modo, v, silaba)
        self.sx_en = 0.70 + 0.30 * abs(math.cos(self.fase * (0.9 + 2.0 * v)))

    def _prisma(self, dt, modo, v, silaba):
        sl = self._saltos_int
        sl.andar(dt)
        if silaba and sl.desde > 0.25:
            sl.dar()
        elif modo not in ("fala", "mudo") and sl.desde > (1.2 if modo == "pensa" else 5.0):
            sl.dar()
        self.int = sl.valor()
        self.ext *= 0.6

    def _iris(self, dt, modo, v, silaba):
        abre = 18.0 * self.lento + 9.0 * self.pulso
        self.int = (self.ext * 0.4 + abre) % 360.0
        self.esc_int = 1.0 + 0.05 * self.lento

    def _engrenagem(self, dt, modo, v, silaba):
        # os dois anéis engrenados: o de dentro roda ao contrário, mais rápido
        self.int = (-self.ext * 1.75) % 360.0
        self.rastro = min(9.0, 2.0 + 30.0 * v) if modo == "fala" else 0.0

    def _atomo(self, dt, modo, v, silaba):
        vel = (1.2 + 3.5 * v) if modo != "mudo" else 0.3
        if modo == "pensa":
            vel = 3.0
        self.eletrons = [(e + vel * dt * (1.0 + 0.15 * i)) % (2 * math.pi)
                         for i, e in enumerate(self.eletrons)]
        self.ext *= 0.5

    def _mandala(self, dt, modo, v, silaba):
        resp = 0.04 * math.sin(self.fase * 0.9)
        self.esc_ext = 1.0 + resp + 0.06 * self.lento
        self.esc_int = 1.0 - resp + 0.04 * self.pulso

    def _vortice(self, dt, modo, v, silaba):
        self.en = (self.en - (60 + 160 * v) * dt) % 360.0
        self.rastro = min(12.0, 4.0 + 40.0 * v) if modo in ("fala", "pensa") else 2.0


def _modo(cv, amp: float) -> str:
    if getattr(cv, "muted", False):
        return "mudo"
    if getattr(cv, "speaking", False):
        return "fala"
    st = str(getattr(cv, "state", "")).upper()
    if st in ("THINKING", "PROCESSING"):
        return "pensa"
    if st == "LISTENING" and amp > 0.06:
        return "ouve"
    return "ocioso"


def _tinta(modo: str) -> str | None:
    """None = a arte original (azul). Tema fora do azul tinge com a cor do tema."""
    if modo == "ouve":
        return C.GREEN
    if modo == "pensa":
        return C.ACC
    if modo == "mudo":
        return "#7a2a3a"
    pri = QColor(C.PRI)
    h = pri.hsvHue()
    if h < 0 or 175 <= h <= 215:          # o azul do JARVIS: arte sem tinta
        return None
    return C.PRI


# ── desenho ──────────────────────────────────────────────────────────────────
def _poligono(cx: float, cy: float, r: float, lados: int, giro: float) -> QPolygonF:
    pts = []
    for i in range(lados):
        a = math.radians(giro + 360.0 * i / lados - 90.0)
        pts.append(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
    return QPolygonF(pts)


def _desenhar_peca(p: QPainter, px: QPixmap, cx: float, cy: float, ang: float,
                   esc: float, sx: float = 1.0, alpha: float = 1.0,
                   dx: float = 0.0, dy: float = 0.0) -> None:
    p.save()
    p.translate(cx, cy)
    p.rotate(ang)
    p.scale(esc * sx, esc)
    p.setOpacity(max(0.0, min(1.0, alpha)))
    p.drawPixmap(QPointF(-px.width() / 2 + dx * px.width(), -px.height() / 2 + dy * px.height()), px)
    p.restore()


def _desenhar(nid: str, cv, p, W, H, cx, cy, R, main, acc, amp):
    if not tem_arte():
        raise RuntimeError("sem a arte dos núcleos em assets/nucleo")
    modo = _modo(cv, amp)
    ux = cv.__dict__.setdefault("_ux", {})
    mt = ux.get("nucleo")
    if mt is None or mt.nid != nid:
        mt = ux["nucleo"] = _Motor(nid)
    mt.passo(modo, amp)

    _ic, _nm, _ds, _pasta, r_int, r_en, extras = _NUCLEOS[nid]
    tinta = _tinta(modo)
    # diâmetro máximo do anel de fora; o resto é escala do QPainter
    D_max = 2.0 * R * 1.10
    ext = _peca(nid, "anel_externo", D_max, tinta)
    inn = _peca(nid, "anel_interno", D_max * r_int, tinta)
    en = _peca(nid, "energia", D_max * r_en * 1.35, tinta)
    if ext is None or inn is None or en is None:
        raise RuntimeError("peça do núcleo ilegível")
    k = mt.tam / 1.10                         # escala do quadro em relação ao máximo
    cor_onda = QColor(tinta or C.PRI)

    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    # brilho de fundo atrás do núcleo
    g = QRadialGradient(cx, cy, R * 0.95)
    c0 = QColor(cor_onda); c0.setAlpha(int(40 + 70 * mt.lento))
    c1 = QColor(cor_onda); c1.setAlpha(0)
    g.setColorAt(0.0, c0); g.setColorAt(1.0, c1)
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), R * 0.95, R * 0.95)

    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    alpha = 0.45 if modo == "mudo" else 1.0

    # ondas que saem com a voz (no formato do núcleo)
    agora = time.monotonic()
    lados = int(extras.get("onda", 0) or 0)
    for t0 in mt.ondas:
        f = (agora - t0) / 1.4
        rr = R * k * (0.55 + 0.55 * f)
        a = int(170 * (1.0 - f) ** 1.6 * alpha)
        if a <= 0:
            continue
        cw = QColor(cor_onda); cw.setAlpha(a)
        p.setPen(QPen(cw, 1.2 + 2.2 * (1.0 - f)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if lados >= 3:
            giro = mt.ext + (45.0 if lados == 4 else 0.0)
            p.drawPolygon(_poligono(cx, cy, rr, lados, giro))
        else:
            p.drawEllipse(QPointF(cx, cy), rr, rr)

    # anel de fora (com rastro quando gira rápido)
    if mt.rastro > 0.5:
        for i, fa in ((2, 0.18), (1, 0.32)):
            _desenhar_peca(p, ext, cx, cy, mt.ext - mt.rastro * i, k * mt.esc_ext, alpha=fa * alpha)
    _desenhar_peca(p, ext, cx, cy, mt.ext, k * mt.esc_ext, alpha=alpha)

    # anel de dentro
    dy_int = extras.get("centro_int", (0.0, 0.0))[1]
    if mt.rastro > 0.5:
        _desenhar_peca(p, inn, cx, cy, mt.int + mt.rastro * 1.5, k * mt.esc_int,
                       alpha=0.28 * alpha, dy=dy_int)
    _desenhar_peca(p, inn, cx, cy, mt.int, k * mt.esc_int, alpha=alpha, dy=dy_int)

    # espectro: barras em volta do anel, do histórico real do áudio
    if extras.get("barras"):
        _barras(p, cv, cx, cy, R * k * r_int * 1.02, R * k * 0.95, cor_onda, alpha,
                int(extras["barras"]), mt.ext)

    # átomo: elétrons nas três órbitas
    if extras.get("orbitas"):
        _eletrons(p, mt, cx, cy, R * k, extras["orbitas"], cor_onda, alpha)

    # energia do meio: pulsa a cada sílaba; uma segunda cópia gira ao contrário
    fator = (0.80 + 0.55 * mt.pulso) / 1.35
    _desenhar_peca(p, en, cx, cy, mt.en, k * fator, sx=mt.sx_en, alpha=alpha)
    _desenhar_peca(p, en, cx, cy, mt.en2, k * fator * 0.92, sx=mt.sx_en, alpha=0.40 * alpha)
    p.restore()


def _barras(p, cv, cx, cy, r0, r1, cor, alpha, n, giro):
    hist = list(getattr(cv, "_h", []) or [])
    if not hist:
        return
    m = len(hist)
    larg = max(1.5, 2 * math.pi * r0 / n * 0.45)
    for i in range(n):
        # espelhado: metade do anel lê o histórico, a outra metade o espelho
        j = i if i < n // 2 else n - 1 - i
        v = hist[int(j * m / (n // 2)) % m]
        comp = (r1 - r0) * (0.12 + 0.88 * min(1.0, v * 1.6))
        a = math.radians(giro * 0.3 + 360.0 * i / n - 90.0)
        ca, sa = math.cos(a), math.sin(a)
        c = QColor(cor); c.setAlpha(int((90 + 165 * min(1.0, v * 1.5)) * alpha))
        p.setPen(QPen(c, larg, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx + ca * r0, cy + sa * r0),
                   QPointF(cx + ca * (r0 + comp), cy + sa * (r0 + comp)))


def _eletrons(p, mt, cx, cy, Rk, orbitas, cor, alpha):
    a_rel, b_rel, angs = orbitas
    a, b = Rk * a_rel, Rk * b_rel
    for i, (fase, giro) in enumerate(zip(mt.eletrons, angs)):
        g = math.radians(giro)
        for passo, fa in ((0.0, 1.0), (0.10, 0.45), (0.20, 0.22), (0.30, 0.10)):
            t = fase - passo
            x0, y0 = a * math.cos(t), b * math.sin(t)
            x = cx + x0 * math.cos(g) - y0 * math.sin(g)
            y = cy + x0 * math.sin(g) + y0 * math.cos(g)
            r = Rk * (0.035 if passo == 0.0 else 0.025)
            gr = QRadialGradient(x, y, r * 2.2)
            c0 = QColor("#ffffff" if passo == 0.0 else cor.name())
            c0.setAlpha(int(255 * fa * alpha))
            c1 = QColor(cor); c1.setAlpha(0)
            gr.setColorAt(0.0, c0); gr.setColorAt(1.0, c1)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(gr))
            p.drawEllipse(QPointF(x, y), r * 2.2, r * 2.2)


def _fabrica(nid: str):
    def desenhar(cv, p, W, H, cx, cy, R, main, acc, amp):
        _desenhar(nid, cv, p, W, H, cx, cy, R, main, acc, amp)
    desenhar.__name__ = f"nucleo_{nid}"
    return desenhar


# Mesmo formato de ULTRA_STYLES: chave -> (ícone, nome, descrição, função)
NUCLEO_STYLES: dict = {nid: (v[0], v[1], v[2], _fabrica(nid)) for nid, v in _NUCLEOS.items()}
# 6.1.7 — Visual 2026: anel de luz (minimalista) e futurista (gráficos em movimento)
try:
    from .hud_2026 import ESTILOS_2026
    NUCLEO_STYLES.update(ESTILOS_2026)
except Exception as _e:      # pragma: no cover — um visual nunca derruba o HUD
    print(f"[HUD] visuais 2026 indisponíveis: {_e}")
NUCLEO_INFO = {k: v[:3] for k, v in NUCLEO_STYLES.items()}
