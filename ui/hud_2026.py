"""Mostradores centrais do Visual 2026 (6.1.7).

  anel ...... minimalista: um anel de luz que respira e pulsa com a voz
  futurista . gráficos em movimento: arcos de dados girando, espectro radial,
              osciloscópio e escala graduada

Mesmo formato dos núcleos (ui/hud_nucleos.py): função(cv, p, W, H, cx, cy, R,
main, acc, amp). Não dependem de arte em assets/ — são desenhados à mão, então
funcionam em qualquer instalação e com qualquer cor de tema.
"""
from __future__ import annotations

import math
import time

from ._qt import *  # noqa: F401,F403
from ._base import C, accent2, qcol


def _rgba(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlpha(max(0, min(255, int(a))))
    return out


def _cor_estado(cv, main: QColor, acc: QColor) -> QColor:
    if getattr(cv, "muted", False):
        return qcol(C.MUTED_C)
    st = str(getattr(cv, "state", "")).upper()
    if getattr(cv, "speaking", False) or st in ("THINKING", "PROCESSING", "LISTENING"):
        return acc
    return main


def anel(cv, p: QPainter, W, H, cx, cy, R, main, acc, amp) -> None:
    t = time.monotonic()
    cor = _cor_estado(cv, main, acc)
    resp = 0.5 + 0.5 * math.sin(t * 1.6)               # respiração lenta
    r = R * (0.62 + 0.035 * resp + 0.16 * amp)

    # halo largo
    g = QRadialGradient(cx, cy, r * 1.55)
    g.setColorAt(0.0, _rgba(cor, 0))
    g.setColorAt(0.55, _rgba(cor, 40 + 50 * resp + 120 * amp))
    g.setColorAt(0.70, _rgba(cor, 18 + 40 * amp))
    g.setColorAt(1.0, _rgba(cor, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), r * 1.55, r * 1.55)

    # anel principal: degradê cônico girando
    p.save()
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    cg = QConicalGradient(cx, cy, (t * 40.0) % 360.0)
    c2 = qcol(accent2(cor.name()))
    cg.setColorAt(0.0, _rgba(cor, 255))
    cg.setColorAt(0.33, _rgba(c2, 230))
    cg.setColorAt(0.66, _rgba(QColor("#ffffff"), 210))
    cg.setColorAt(1.0, _rgba(cor, 255))
    for larg, a in ((R * 0.10, 40), (R * 0.05, 110), (R * 0.018, 255)):
        pen = QPen(QBrush(cg), larg)
        p.setOpacity(a / 255.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)
    p.setOpacity(1.0)

    # ondas que saem com a voz
    for k in range(3):
        f = ((t * 0.55) + k / 3.0) % 1.0
        rr = r * (1.0 + 0.45 * f)
        a = (1.0 - f) ** 2 * (40 + 200 * amp)
        p.setPen(QPen(_rgba(cor, a), 1.4))
        p.drawEllipse(QPointF(cx, cy), rr, rr)

    # arco fino externo, segmentado, girando devagar
    p.setPen(QPen(_rgba(cor, 120), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    re = R * 0.92
    rect = QRectF(cx - re, cy - re, 2 * re, 2 * re)
    giro = -t * 18.0
    for i in range(4):
        p.drawArc(rect, int((giro + i * 90) * 16), int(52 * 16))
    p.restore()


def futurista(cv, p: QPainter, W, H, cx, cy, R, main, acc, amp) -> None:
    t = time.monotonic()
    cor = _cor_estado(cv, main, acc)
    c2 = qcol(accent2(cor.name()))
    hist = list(getattr(cv, "_h", []) or [0.0] * 36)

    p.save()
    # fundo do disco
    g = QRadialGradient(cx, cy, R)
    g.setColorAt(0.0, _rgba(cor, 50 + 80 * amp))
    g.setColorAt(0.6, _rgba(cor, 14))
    g.setColorAt(1.0, _rgba(cor, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), R, R)

    # escala graduada (120 marcas, uma maior a cada 10)
    rt = R * 0.97
    for i in range(120):
        a = math.radians(i * 3 - t * 6)
        lng = R * (0.06 if i % 10 == 0 else 0.025)
        p.setPen(QPen(_rgba(cor, 150 if i % 10 == 0 else 60), 1.2))
        p.drawLine(QPointF(cx + math.cos(a) * rt, cy + math.sin(a) * rt),
                   QPointF(cx + math.cos(a) * (rt - lng), cy + math.sin(a) * (rt - lng)))

    # arcos de dados girando em velocidades diferentes
    for k, (esc, vel, segs, larg) in enumerate(((0.84, 22, 7, 3.0), (0.74, -35, 5, 5.0),
                                                 (0.64, 50, 11, 1.6))):
        rr = R * esc
        rect = QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr)
        giro = t * vel * (1.6 if str(getattr(cv, "state", "")).upper() == "THINKING" else 1.0)
        p.setPen(QPen(_rgba(c2 if k == 1 else cor, 150 + 90 * amp), larg,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        for s in range(segs):
            comp = 360.0 / segs * (0.35 + 0.3 * ((s * 37) % 7) / 7.0)
            p.drawArc(rect, int((giro + s * 360.0 / segs) * 16), int(comp * 16))

    # espectro radial do histórico real do áudio
    n = 64
    r0 = R * 0.40
    for i in range(n):
        j = i if i < n // 2 else n - 1 - i
        v = hist[int(j * len(hist) / (n // 2)) % len(hist)]
        comp = R * (0.02 + 0.20 * min(1.0, v * 1.7))
        a = math.radians(i * 360.0 / n - 90)
        p.setPen(QPen(_rgba(cor, 90 + 165 * min(1.0, v * 1.6)), 2.2,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                   QPointF(cx + math.cos(a) * (r0 + comp), cy + math.sin(a) * (r0 + comp)))

    # osciloscópio no meio (linha que corre)
    larg = R * 0.62
    path = QPainterPath()
    for i in range(61):
        x = -larg / 2 + larg * i / 60
        env = math.sin(math.pi * i / 60)
        y = math.sin(i * 0.45 + t * 7) * env * R * (0.03 + 0.16 * amp)
        y += math.sin(i * 0.17 - t * 3) * env * R * 0.02
        pt = QPointF(cx + x, cy + y)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(_rgba(cor, 70), 5))
    p.drawPath(path)
    p.setPen(QPen(_rgba(QColor("#ffffff"), 220), 1.4))
    p.drawPath(path)

    # varredura de radar
    ang = (t * 70) % 360
    cg = QConicalGradient(cx, cy, -ang)
    cg.setColorAt(0.0, _rgba(cor, 90))
    cg.setColorAt(0.08, _rgba(cor, 0))
    cg.setColorAt(1.0, _rgba(cor, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(cg))
    p.drawEllipse(QPointF(cx, cy), R * 0.86, R * 0.86)
    p.restore()


# chave -> (ícone, nome, descrição, função) — o mesmo formato de NUCLEO_STYLES
ESTILOS_2026 = {
    "anel":      ("◯", "Anel de luz", "Minimalista: um anel de luz que respira e pulsa com a voz", anel),
    "futurista": ("◎", "Futurista", "Gráficos em movimento: arcos de dados, espectro e osciloscópio", futurista),
}
