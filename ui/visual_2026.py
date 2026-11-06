"""Visual 2026 — o acabamento moderno do NEXUS Premium 2026.

Tudo o que muda a "cara" da janela sem mexer no que ela faz:

  • transparência da janela (preferência visual_transparencia)
  • fundo em degradê suave com textura sutil (FundoGradiente)
  • barra de título escura e na cor do tema; cantos arredondados no Windows 11
  • brilho nos botões ao passar o mouse e sombra suave nos títulos dos painéis
  • transições suaves (painéis aparecem com fade; trocas do centro também)
  • rolagem suave e barra de rolagem fina e moderna em toda a janela
  • cursor do mouse com a cor do tema
  • avisos (notificações) modernos dentro da janela — notificar()
  • painéis laterais redimensionáveis e com lado trocável (organizar_paineis)

Cada efeito pode ser desligado em Configuração do usuário › VISUAL 2026, e
nenhum deles pode derrubar a janela: qualquer erro aqui é engolido e o NEXUS
segue com o visual de antes.
"""
from __future__ import annotations

import random
import weakref

from ._qt import *  # noqa: F401,F403
from ._base import C, _OS, _bg_color, accent2, mix, qcol
from PyQt6.QtGui import QCursor, QFontMetrics
from PyQt6.QtWidgets import (QAbstractScrollArea, QGraphicsDropShadowEffect,
                             QGraphicsOpacityEffect)

_JANELA = None            # weakref da MainWindow
_FILTRO = None            # o filtro de eventos global (brilho, fade, rolagem)
_PONTE = None             # ponte entre threads para notificar()
_AVISOS: list = []        # avisos na tela, de baixo para cima
_ULTIMA_COR = None        # para perceber troca de tema


# ── preferências ──────────────────────────────────────────────────────────────
def _pref(chave: str, padrao):
    try:
        from core import preferences as _P
        v = _P.get(chave)
        return padrao if v is None else v
    except Exception:
        return padrao


def salvar(**valores) -> None:
    try:
        from core import preferences as _P
        _P.save(valores)
    except Exception as e:
        print(f"[Visual] não salvou {list(valores)}: {e}")


def efeitos_ligados() -> bool:
    return bool(_pref("visual_efeitos", True))


def janela():
    return _JANELA() if _JANELA is not None else None


# ══════════════════════════════════════════════════════════════════════════
#  FUNDO
# ══════════════════════════════════════════════════════════════════════════
class FundoGradiente(QWidget):
    """Widget central: degradê diagonal + dois brilhos + textura bem sutil.
    O desenho fica num pixmap em cache e só é refeito se o tamanho ou o tema mudar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: QPixmap | None = None
        self._chave = None

    def paintEvent(self, _e):
        W, H = self.width(), self.height()
        base = _bg_color(C.BG)
        chave = (W, H, base, C.PANEL2, C.PRI)
        if self._cache is None or self._chave != chave:
            self._cache, self._chave = self._desenhar(W, H, base), chave
            _tema_pode_ter_mudado()
        p = QPainter(self)
        if p.isActive():
            p.drawPixmap(0, 0, self._cache)
            p.end()

    @staticmethod
    def _desenhar(W: int, H: int, base: str) -> QPixmap:
        pm = QPixmap(max(1, W), max(1, H))
        pm.fill(QColor(base))
        g = QPainter(pm)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        lg = QLinearGradient(0, 0, W, H)
        lg.setColorAt(0.0, QColor(mix(base, C.PANEL2, 0.65)))
        lg.setColorAt(0.55, QColor(base))
        lg.setColorAt(1.0, QColor(mix(base, "#000000", 0.45)))
        g.fillRect(0, 0, W, H, QBrush(lg))
        for (x, y, r, cor, a) in ((0.12, 0.0, 0.75, C.PRI, 30),
                                  (0.95, 1.0, 0.65, accent2(), 26)):
            rg = QRadialGradient(W * x, H * y, max(W, H) * r)
            c0 = qcol(cor, a)
            c1 = qcol(cor, 0)
            rg.setColorAt(0.0, c0)
            rg.setColorAt(1.0, c1)
            g.fillRect(0, 0, W, H, QBrush(rg))
        # textura: linhas diagonais finíssimas + grão
        g.setPen(QPen(qcol(C.PRI, 6), 1))
        for x in range(-H, W, 7):
            g.drawLine(x, 0, x + H, H)
        rnd = random.Random(2026)
        g.setPen(Qt.PenStyle.NoPen)
        for _ in range(int(W * H / 700)):
            g.setBrush(QColor(255, 255, 255, rnd.randint(4, 12)))
            g.drawRect(QRectF(rnd.uniform(0, W), rnd.uniform(0, H), 1, 1))
        g.end()
        return pm


# ══════════════════════════════════════════════════════════════════════════
#  JANELA: transparência, barra de título, cursor, folha de estilo global
# ══════════════════════════════════════════════════════════════════════════
def _colorref(hx: str) -> int:
    c = QColor(hx)
    return (c.blue() << 16) | (c.green() << 8) | c.red()


def barra_titulo(win) -> None:
    """Barra de título escura e com a cor do tema (DWM). Win 10: modo escuro.
    Win 11: também a cor da barra, a cor da borda e os cantos arredondados."""
    if _OS != "Windows":
        return
    try:
        import ctypes
        hwnd = ctypes.c_void_p(int(win.winId()))
        dwm = ctypes.windll.dwmapi

        def _set(attr: int, val: int) -> int:
            v = ctypes.c_int(val)
            return dwm.DwmSetWindowAttribute(hwnd, ctypes.c_uint(attr),
                                             ctypes.byref(v), ctypes.sizeof(v))

        if _set(20, 1) != 0:             # DWMWA_USE_IMMERSIVE_DARK_MODE
            _set(19, 1)                  # (builds antigos do Windows 10)
        _set(33, 2)                      # cantos arredondados (Windows 11)
        _set(35, _colorref(mix(_bg_color(C.BG), C.PANEL2, 0.6)))   # cor da barra
        _set(36, _colorref(C.TEXT))      # cor do texto do título
        _set(34, _colorref(C.PRI_DIM))   # cor da borda
    except Exception as e:
        print(f"[Visual] barra de título: {e}")


def _cursor_tema() -> QCursor:
    s = 32
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    seta = QPainterPath()
    for i, (x, y) in enumerate(((2, 2), (2, 23), (7.5, 18), (11.5, 27), (15.5, 25.3),
                                (11.6, 16.8), (19, 16.8))):
        seta.moveTo(x, y) if i == 0 else seta.lineTo(x, y)
    seta.closeSubpath()
    p.translate(1, 1.4)
    p.fillPath(seta, QColor(0, 0, 0, 90))          # sombra
    p.translate(-1, -1.4)
    gr = QLinearGradient(2, 2, 16, 26)
    gr.setColorAt(0.0, QColor("#ffffff"))
    gr.setColorAt(0.35, qcol(C.PRI))
    gr.setColorAt(1.0, qcol(accent2()))
    p.fillPath(seta, QBrush(gr))
    p.setPen(QPen(QColor(mix(C.BG, "#000000", 0.3)), 1.3))
    p.drawPath(seta)
    p.end()
    return QCursor(pm, 2, 2)


def _folha_global() -> str:
    pri = QColor(C.PRI)
    rgba = f"rgba({pri.red()}, {pri.green()}, {pri.blue()}"
    from ._base import FONT_MAIN
    # A Bahnschrift desenha o acento das maiúsculas (Ê, Í, Ã) acima da altura
    # que o QLabel reserva; 2 px no topo evitam que ele seja cortado.
    extra = "QLabel { padding-top: 2px; }" if FONT_MAIN == "Bahnschrift" else ""
    return extra + f"""
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 1px; }}
        QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 1px 4px; }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {rgba}, 0.30); border-radius: 3px; min-height: 28px; min-width: 28px; }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background: {rgba}, 0.75); }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
        QToolTip {{ background: {C.PANEL2}; color: {C.TEXT}; border: 1px solid {C.BORDER_B};
            border-radius: 6px; padding: 5px 9px; }}
    """


def _aplicar_folha_global() -> None:
    app = QApplication.instance()
    if app is None:
        return
    atual = app.styleSheet() or ""
    marca = "/*nx-visual-2026*/"
    if marca in atual:
        atual = atual.split(marca)[0]
    app.setStyleSheet(atual + marca + _folha_global())


def _tema_pode_ter_mudado() -> None:
    """Chamado quando o fundo é refeito: se a cor do tema mudou, refaz o que
    não segue sozinho (folha global, cursor, barra de título)."""
    global _ULTIMA_COR
    if _ULTIMA_COR == C.PRI:
        return
    _ULTIMA_COR = C.PRI
    w = janela()
    if w is None:
        return
    QTimer.singleShot(0, lambda: reaplicar(w, so_cores=True))


# ══════════════════════════════════════════════════════════════════════════
#  EFEITOS: brilho, sombra nos títulos, fade, rolagem suave
# ══════════════════════════════════════════════════════════════════════════
def sombra_titulo(w: QWidget, forca: int = 150) -> None:
    if w is None or w.graphicsEffect() is not None:
        return
    ef = QGraphicsDropShadowEffect(w)
    ef.setObjectName("nx_sombra")
    ef.setBlurRadius(14)
    ef.setOffset(0, 1)
    ef.setColor(qcol(C.PRI, forca))
    w.setGraphicsEffect(ef)


def sombrear_titulos(raiz: QWidget) -> None:
    for lb in raiz.findChildren(QLabel):
        try:
            t = lb.text()
            f = lb.font()
            peso = f.weight()
            peso = int(getattr(peso, "value", peso))
            if (t and len(t) <= 40 and t.upper() == t and any(ch.isalpha() for ch in t)
                    and f.letterSpacing() >= 1.5 and peso >= 600):
                sombra_titulo(lb)
        except Exception:
            pass


def _tirar_efeitos(raiz: QWidget, nomes=("nx_sombra", "nx_brilho")) -> None:
    for w in raiz.findChildren(QWidget):
        ef = w.graphicsEffect()
        if ef is not None and ef.objectName() in nomes:
            w.setGraphicsEffect(None)


def aparecer(w: QWidget, ms: int = 220) -> None:
    """Fade-in curto. Só usa o efeito enquanto anima (opacidade fixa pesa)."""
    if w is None or not efeitos_ligados() or w.graphicsEffect() is not None:
        return
    try:
        ef = QGraphicsOpacityEffect(w)
        ef.setObjectName("nx_fade")
        ef.setOpacity(0.0)
        w.setGraphicsEffect(ef)
        an = QPropertyAnimation(ef, b"opacity", w)
        an.setDuration(ms)
        an.setStartValue(0.0)
        an.setEndValue(1.0)
        an.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _fim():
            try:
                if w.graphicsEffect() is ef:
                    w.setGraphicsEffect(None)
            except RuntimeError:
                pass
        an.finished.connect(_fim)
        an.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    except Exception:
        pass


class _Filtro(QObject):
    """Um único filtro para a aplicação: brilho dos botões, fade dos painéis
    flutuantes e rolagem suave. Rápido de propósito: olha o tipo primeiro."""

    _TIPOS = (QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.Show, QEvent.Type.Wheel)

    def eventFilter(self, obj, ev):
        try:
            t = ev.type()
            if t not in self._TIPOS or not isinstance(obj, QWidget):
                return False
            if not efeitos_ligados():
                return False
            if t == QEvent.Type.Wheel:
                return self._rolar(obj, ev)
            if t == QEvent.Type.Show:
                self._fade(obj)
                return False
            if isinstance(obj, QPushButton):
                self._brilho(obj, t == QEvent.Type.Enter)
        except Exception:
            pass
        return False

    @staticmethod
    def _brilho(b: QPushButton, entrou: bool) -> None:
        ef = b.graphicsEffect()
        if entrou:
            # botões desenhados à mão já brilham sozinhos no estilo neon
            if type(b).paintEvent is not QPushButton.paintEvent:
                try:
                    from .modern import botao_neon
                    if botao_neon():
                        return
                except Exception:
                    pass
            if ef is None and b.isEnabled():
                e = QGraphicsDropShadowEffect(b)
                e.setObjectName("nx_brilho")
                e.setBlurRadius(24)
                e.setOffset(0, 0)
                e.setColor(qcol(C.PRI, 185))
                b.setGraphicsEffect(e)
        elif ef is not None and ef.objectName() == "nx_brilho":
            b.setGraphicsEffect(None)

    @staticmethod
    def _fade(w: QWidget) -> None:
        win = janela()
        if win is None or w.isWindow():
            return
        cw = win.centralWidget()
        if w.parentWidget() is not cw or cw.layout() is None:
            return
        if cw.layout().indexOf(w) >= 0 or isinstance(w, Aviso):
            return
        aparecer(w)

    @staticmethod
    def _rolar(obj: QWidget, ev) -> bool:
        area = obj.parentWidget()
        if not isinstance(area, QAbstractScrollArea) or obj is not area.viewport():
            return False
        if ev.modifiers() != Qt.KeyboardModifier.NoModifier:
            return False
        if not ev.pixelDelta().isNull():           # touchpad: já é suave
            return False
        dy = ev.angleDelta().y()
        sb = area.verticalScrollBar()
        if dy == 0 or sb is None or sb.maximum() <= 0:
            return False
        an = getattr(sb, "_nx_an", None)
        base = an.endValue() if (an is not None and
                                 an.state() == QPropertyAnimation.State.Running) else sb.value()
        passo = max(48, sb.singleStep() * 3)
        alvo = max(sb.minimum(), min(sb.maximum(), int(base - dy / 120.0 * passo)))
        if an is None:
            an = QPropertyAnimation(sb, b"value", sb)
            an.setDuration(200)
            an.setEasingCurve(QEasingCurve.Type.OutCubic)
            sb._nx_an = an
        an.stop()
        an.setStartValue(sb.value())
        an.setEndValue(alvo)
        an.start()
        return True


# ══════════════════════════════════════════════════════════════════════════
#  AVISOS (notificações modernas dentro da janela)
# ══════════════════════════════════════════════════════════════════════════
_CORES_AVISO = {"info": None, "ok": "GREEN", "alerta": "ACC", "erro": "RED"}


class Aviso(QWidget):
    _W = 310

    def __init__(self, parent, titulo: str, texto: str, tipo: str, ms: int):
        super().__init__(parent)
        self._titulo, self._texto = titulo, texto
        chave = _CORES_AVISO.get(tipo)
        self._cor = qcol(getattr(C, chave) if chave else C.PRI)
        from ._base import FONT_MAIN
        self._ft = QFont(FONT_MAIN, 9, QFont.Weight.Bold)
        self._fx = QFont(FONT_MAIN, 8)
        fm = QFontMetrics(self._fx)
        alt_txt = fm.boundingRect(QRect(0, 0, self._W - 52, 400),
                                  int(Qt.TextFlag.TextWordWrap), texto).height() if texto else 0
        self.setFixedSize(self._W, 30 + alt_txt + (14 if texto else 4))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(28); sh.setOffset(0, 6); sh.setColor(QColor(0, 0, 0, 170))
        self.setGraphicsEffect(sh)
        self._t_fim = QTimer(self)
        self._t_fim.setSingleShot(True)
        self._t_fim.timeout.connect(self.fechar)
        self._t_fim.start(max(1500, ms))

    def paintEvent(self, _e):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0.0, qcol(C.PANEL2, 245))
        g.setColorAt(1.0, qcol(C.PANEL, 245))
        p.setPen(QPen(qcol(self._cor.name(), 150), 1))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 12, 12)
        # faixa de cor à esquerda
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._cor)
        p.drawRoundedRect(QRectF(r.left() + 7, r.top() + 10, 3.5, r.height() - 20), 2, 2)
        # ponto aceso
        halo = QRadialGradient(QPointF(r.left() + 26, r.top() + 17), 9)
        c0 = QColor(self._cor); c0.setAlpha(170)
        c1 = QColor(self._cor); c1.setAlpha(0)
        halo.setColorAt(0, c0); halo.setColorAt(1, c1)
        p.setBrush(QBrush(halo)); p.drawEllipse(QPointF(r.left() + 26, r.top() + 17), 9, 9)
        p.setBrush(self._cor); p.drawEllipse(QPointF(r.left() + 26, r.top() + 17), 3.2, 3.2)
        p.setPen(qcol(C.WHITE))
        p.setFont(self._ft)
        p.drawText(QRectF(r.left() + 38, r.top() + 6, r.width() - 48, 22),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._titulo)
        if self._texto:
            p.setPen(qcol(C.TEXT_MED))
            p.setFont(self._fx)
            p.drawText(QRectF(r.left() + 38, r.top() + 28, r.width() - 50, r.height() - 32),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap),
                       self._texto)
        p.end()

    def mousePressEvent(self, _e):
        self.fechar()

    def fechar(self):
        if getattr(self, "_saindo", False):
            return
        self._saindo = True
        an = QPropertyAnimation(self, b"pos", self)
        an.setDuration(220)
        an.setStartValue(self.pos())
        an.setEndValue(QPoint(self.parentWidget().width() + 10, self.y()))
        an.setEasingCurve(QEasingCurve.Type.InCubic)
        an.finished.connect(self._sumir)
        an.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _sumir(self):
        try:
            _AVISOS.remove(self)
        except ValueError:
            pass
        self.hide()
        self.deleteLater()
        _empilhar()


def _empilhar(animar_novo=None) -> None:
    win = janela()
    if win is None:
        return
    cw = win.centralWidget()
    # canto SUPERIOR direito da área central: não cobre a conversa, o sistema
    # nem o texto de estado do mostrador
    try:
        cs = win._center_split
        canto = cs.mapTo(cw, QPoint(cs.width(), 0))
        x_dir, y = canto.x() - 16, canto.y() + 14
    except Exception:
        x_dir, y = cw.width() - 18, 72
    for av in reversed(_AVISOS):
        x = x_dir - av.width()
        if av is animar_novo:
            av.move(cw.width() + 10, y)
            an = QPropertyAnimation(av, b"pos", av)
            an.setDuration(320)
            an.setStartValue(av.pos())
            an.setEndValue(QPoint(x, y))
            an.setEasingCurve(QEasingCurve.Type.OutBack)
            an.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        elif not getattr(av, "_saindo", False):
            av.move(x, y)
        y += av.height() + 10


def _mostrar_aviso(titulo: str, texto: str, tipo: str) -> None:
    win = janela()
    if win is None:
        return
    while len(_AVISOS) >= 4:
        _AVISOS[0].fechar()
        _AVISOS.pop(0)
    av = Aviso(win.centralWidget(), titulo, texto, tipo, 4500 + 40 * len(texto))
    _AVISOS.append(av)
    av.show()
    av.raise_()
    _empilhar(animar_novo=av)


class _Ponte(QObject):
    sinal = pyqtSignal(str, str, str)


def notificar(titulo: str, texto: str = "", tipo: str = "info") -> None:
    """Mostra um aviso moderno no canto da janela. Pode ser chamado de qualquer
    thread. tipo: info | ok | alerta | erro."""
    if _PONTE is None:
        return
    try:
        _PONTE.sinal.emit(str(titulo)[:80], str(texto)[:300], str(tipo))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
#  PAINÉIS: lado e largura
# ══════════════════════════════════════════════════════════════════════════
def organizar_paineis(win) -> None:
    """Põe os painéis no lado escolhido e com a largura salva."""
    sp = getattr(win, "_body_split", None)
    if sp is None:
        return
    invertido = str(_pref("visual_paineis", "padrao")) == "invertido"
    ordem = ([win._right_panel, win._center_split, win._left_panel] if invertido
             else [win._left_panel, win._center_split, win._right_panel])
    for i, w in enumerate(ordem):
        if sp.indexOf(w) != i:
            sp.insertWidget(i, w)
    sp.setStretchFactor(sp.indexOf(win._center_split), 1)
    sp.setStretchFactor(sp.indexOf(win._left_panel), 0)
    sp.setStretchFactor(sp.indexOf(win._right_panel), 0)
    larg = _pref("visual_larguras", []) or []
    from ._base import _LEFT_W, _RIGHT_W
    try:
        l_sis, l_conv = int(larg[0]), int(larg[1])
    except Exception:
        l_sis, l_conv = _LEFT_W, _RIGHT_W
    total = max(sp.width(), 900)
    tam = {id(win._left_panel): l_sis, id(win._right_panel): l_conv}
    meio = max(300, total - l_sis - l_conv)
    sp.setSizes([tam.get(id(w), meio) for w in ordem])


def _guardar_larguras(win) -> None:
    try:
        salvar(visual_larguras=[win._left_panel.width(), win._right_panel.width()])
    except Exception:
        pass


def preparar_divisor(win, sp: QSplitter) -> None:
    sp.setChildrenCollapsible(False)
    sp.setHandleWidth(5)
    sp.setStyleSheet(f"""
        QSplitter::handle {{ background: transparent; }}
        QSplitter::handle:hover {{ background: {C.PRI_DIM}; }}
    """)
    win._left_panel.setMinimumWidth(180)
    win._left_panel.setMaximumWidth(380)
    win._right_panel.setMinimumWidth(280)
    win._right_panel.setMaximumWidth(620)
    t = QTimer(win)
    t.setSingleShot(True)
    t.setInterval(600)
    t.timeout.connect(lambda: _guardar_larguras(win))
    sp.splitterMoved.connect(lambda *_: t.start())
    win._nx_larg_timer = t


# ══════════════════════════════════════════════════════════════════════════
#  APLICAR
# ══════════════════════════════════════════════════════════════════════════
def aplicar(win) -> None:
    """Chamado uma vez no fim do __init__ da MainWindow."""
    global _JANELA, _FILTRO, _PONTE, _ULTIMA_COR
    _JANELA = weakref.ref(win)
    _ULTIMA_COR = C.PRI
    app = QApplication.instance()
    if _FILTRO is None and app is not None:
        _FILTRO = _Filtro(app)
        app.installEventFilter(_FILTRO)
    if _PONTE is None:
        _PONTE = _Ponte(app)
        _PONTE.sinal.connect(_mostrar_aviso)
    try:
        win._hud_cam_stack.currentChanged.connect(
            lambda _i: aparecer(win._hud_cam_stack.currentWidget(), 260))
    except Exception:
        pass
    reaplicar(win)


def reaplicar(win=None, so_cores: bool = False) -> None:
    """Aplica (de novo) tudo conforme as preferências. Seguro chamar sempre."""
    win = win or janela()
    if win is None:
        return
    try:
        _aplicar_folha_global()
        barra_titulo(win)
        if bool(_pref("visual_cursor", True)):
            win.setCursor(_cursor_tema())
        else:
            win.unsetCursor()
        if so_cores:
            return
        try:
            op = float(_pref("visual_transparencia", 96))
        except (TypeError, ValueError):
            op = 96.0
        win.setWindowOpacity(max(0.70, min(1.0, op / 100.0)))
        if efeitos_ligados():
            sombrear_titulos(win)
            sombra_titulo(getattr(win, "_title_lbl", None), 200)
        else:
            _tirar_efeitos(win)
        try:
            from . import modern
            modern.definir_estilo_icone(str(_pref("visual_icones", "finas")))
            modern.definir_estilo_botao(str(_pref("visual_botoes", "neon")))
        except Exception:
            pass
        organizar_paineis(win)
        for w in win.findChildren(QWidget):
            w.update()
    except Exception as e:
        print(f"[Visual] reaplicar falhou: {e}")
