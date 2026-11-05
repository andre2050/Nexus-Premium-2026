"""Nexus Premium 2026 — a barra de AÇÕES em destaque (no lugar do acesso rápido).

Onze botões grandes, de vidro, com borda ciano que brilha:
    Microfone · Sempre ouvindo · Interromper · Conectar WhatsApp · Controle remoto
    Webcam · Cowork · Computer use · Globo Nexus · Segundo plano · Arquivo

Cada botão tem três estados de cor, que a janela atualiza com set_estado():
    "normal"  vidro com borda ciano suave
    "on"      ligado: preenchido de ciano, borda acesa e um pontinho no canto
    "alerta"  algo desligado que o usuário precisa ver (ex.: microfone mudo) — vermelho
"""
from __future__ import annotations

from PyQt6.QtGui import QFontMetrics

from ._qt import *  # noqa: F401,F403
from ._base import C, FONT_MAIN, qcol  # noqa: F401

_FONTE_ICONE = "Segoe UI Emoji"


class BotaoAcao(QPushButton):
    """Ladrilho: ícone grande em cima, nome embaixo; desenhado à mão (glow)."""

    def __init__(self, icone: str, nome: str, dica: str, parent=None, cor: str = ""):
        super().__init__(parent)
        self.icone, self.nome = icone, nome
        self.cor = cor                  # 6.1.3: cor própria (ex.: verde do WhatsApp)
        self.estado = "normal"
        self._hover = False
        self.setToolTip(dica)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(64, 62)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(68)

    def set_estado(self, estado: str) -> None:
        estado = estado if estado in ("normal", "on", "alerta") else "normal"
        if estado != self.estado:
            self.estado = estado
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        from .modern import ICONE_ACAO, pintar_chip_icone, pintar_vidro
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 2, -3, -5)
        alerta = self.estado == "alerta"
        cor = qcol(C.RED) if alerta else (QColor(self.cor) if self.cor else qcol(C.PRI))
        apertado = self.isDown()

        # 6.1.3: botão de vidro em relevo (sombra, reflexo, borda iluminada)
        pintar_vidro(p, r, 12, cor, aceso=1.0 if self.estado != "normal" else 0.0,
                     hover=self._hover, press=apertado, alerta=alerta)

        # ícone (pastilha vetorial; emoji só se não houver desenho para ele)
        dy = 1 if apertado else 0
        chave = ICONE_ACAO.get(self.icone, "")
        lado = 26.0
        chip = QRectF(r.center().x() - lado / 2, r.top() + 5 + dy, lado, lado)
        if chave:
            pintar_chip_icone(p, chip, chave, cor if not self._hover else QColor("#ffffff"),
                              aceso=self.estado != "normal" or self._hover)
        else:
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont(_FONTE_ICONE, 14))
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, self.icone)
        f = QFont(FONT_MAIN, 7, QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        nome = self.nome.upper()
        caixa = QRectF(r.left() + 3, r.top() + 33 + dy, r.width() - 6,
                       max(10.0, r.height() - 35))
        alinha = Qt.AlignmentFlag.AlignCenter
        if QFontMetrics(f).horizontalAdvance(nome) > caixa.width():
            # não cabe numa linha: letra menor e quebra em duas ("SEMPRE / OUVINDO")
            f = QFont(FONT_MAIN, 6, QFont.Weight.Bold)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.3)
            alinha = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap
            if QFontMetrics(f).horizontalAdvance(max(nome.split(), key=len)) > caixa.width():
                nome = QFontMetrics(f).elidedText(nome, Qt.TextElideMode.ElideRight, int(caixa.width()))
        p.setFont(f)
        txt = QColor(C.WHITE) if self.estado != "normal" else qcol(C.TEXT_MED)
        p.setPen(txt)
        p.drawText(caixa, alinha, nome)

        # LED de "ligado", com halo
        if self.estado != "normal":
            led = QPointF(r.right() - 9, r.top() + 9)
            halo = QRadialGradient(led, 7)
            c0 = QColor(cor); c0.setAlpha(150)
            c1 = QColor(cor); c1.setAlpha(0)
            halo.setColorAt(0.0, c0); halo.setColorAt(1.0, c1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo)); p.drawEllipse(led, 7, 7)
            p.setBrush(QBrush(cor)); p.drawEllipse(led, 3.0, 3.0)
            p.setBrush(QColor(255, 255, 255, 200)); p.drawEllipse(led + QPointF(-0.9, -0.9), 1.0, 1.0)
        p.end()


class BarraAcoes(QWidget):
    """A faixa com o título AÇÕES e os onze botões lado a lado."""

    def __init__(self, itens: list[dict], parent=None):
        super().__init__(parent)
        self.setObjectName("BarraAcoes")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 6.1.3: a faixa é um "console" com degradê, onde os botões ficam encaixados
        self.setStyleSheet(f"QWidget#BarraAcoes {{ border-top: 1px solid {C.BORDER_B};"
                           f" background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                           f" stop:0 {C.PANEL2}, stop:0.12 {C.DARK}, stop:1 {C.BG}); }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 6)
        lay.setSpacing(7)
        self.botoes: dict[str, BotaoAcao] = {}
        for it in itens:
            b = BotaoAcao(it["icone"], it["nome"], it.get("dica", it["nome"]), cor=it.get("cor", ""))
            # o clicked manda um bool (checked); as ações não recebem argumento
            b.clicked.connect(lambda _=False, f=it["acao"]: f())
            self.botoes[it["chave"]] = b
            lay.addWidget(b, 1)

    def set_estado(self, chave: str, estado: str) -> None:
        b = self.botoes.get(chave)
        if b is not None:
            b.set_estado(estado)
