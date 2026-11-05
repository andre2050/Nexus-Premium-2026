"""Janela do WhatsApp (6.1.3): o QR Code aparece DENTRO do NEXUS.

Antes o botão só tentava abrir o navegador com `start chrome` depois que a
ponte subia — e se o Node.js faltava (ou o Chrome), nada aparecia. Agora:

* a janela abre na hora e mostra o que está acontecendo;
* sem Node.js, oferece instalar (winget) ou baixar no site;
* com a ponte no ar, mostra o QR (wa_qr.png) e atualiza sozinha;
* quando o celular conecta, avisa e pode ser fechada.

O trabalho pesado (subir a ponte, instalar o Node) roda em threads; os
resultados voltam por sinais, então nenhuma thread mexe em widget.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN  # noqa: F401


class WhatsAppQrDialog(QDialog):
    _status_sig = pyqtSignal(dict)
    _info_sig = pyqtSignal(str, bool)       # mensagem, é erro?
    _node_sig = pyqtSignal(bool)            # True = Node presente

    QR_LADO = 264

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conectar o WhatsApp")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumWidth(380)
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {C.PANEL2}, stop:1 {C.BG});
            }}
            QLabel {{ background: transparent; }}
            QPushButton {{
                color: {C.WHITE}; font-weight: 600; padding: 8px 14px;
                border: 1px solid {C.BORDER_B}; border-radius: 10px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,26), stop:0.5 rgba(255,255,255,8),
                    stop:1 rgba(0,0,0,40));
            }}
            QPushButton:hover {{ border-color: {C.PRI}; }}
            QPushButton:pressed {{ background: rgba(0,0,0,70); }}
            QPushButton#verde {{
                border: 1px solid #1faa59; color: #ffffff;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3ddc84, stop:0.5 #25d366, stop:1 #128c4a);
            }}
            QPushButton#verde:hover {{ border-color: #bfffd9; }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        titulo = QLabel("WhatsApp  ·  Conectar aparelho")
        tf = QFont(FONT_MAIN, 12, QFont.Weight.Bold)
        titulo.setFont(tf)
        titulo.setStyleSheet("color: #25d366;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(titulo)

        passos = QLabel("No celular: WhatsApp › Configurações › Aparelhos conectados › "
                        "Conectar um aparelho, e aponte a câmera para o código.")
        passos.setWordWrap(True)
        passos.setAlignment(Qt.AlignmentFlag.AlignCenter)
        passos.setFont(QFont(FONT_MAIN, 8))
        passos.setStyleSheet(f"color: {C.TEXT_MED};")
        lay.addWidget(passos)

        self._qr = QLabel()
        self._qr.setFixedSize(self.QR_LADO + 24, self.QR_LADO + 24)
        self._qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr.setStyleSheet(f"background: #ffffff; border-radius: 14px;"
                               f" border: 2px solid {C.BORDER_B}; color: #555;")
        self._qr.setFont(QFont(FONT_MAIN, 9))
        self._qr.setWordWrap(True)
        self._qr.setText("Preparando…")
        lay.addWidget(self._qr, 0, Qt.AlignmentFlag.AlignHCenter)

        self._msg = QLabel("Verificando o WhatsApp…")
        self._msg.setWordWrap(True)
        self._msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg.setFont(QFont(FONT_MAIN, 8))
        self._msg.setStyleSheet(f"color: {C.TEXT};")
        self._msg.setMinimumHeight(36)
        lay.addWidget(self._msg)

        linha = QHBoxLayout()
        linha.setSpacing(8)
        self._btn_node = QPushButton("Instalar Node.js")
        self._btn_node.setObjectName("verde")
        self._btn_node.clicked.connect(self._instalar_node)
        self._btn_site = QPushButton("Baixar no site")
        self._btn_site.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://nodejs.org/pt/download")))
        self._btn_tentar = QPushButton("Tentar de novo")
        self._btn_tentar.clicked.connect(self._iniciar)
        self._btn_nav = QPushButton("Abrir no navegador")
        self._btn_nav.clicked.connect(self._abrir_navegador)
        self._btn_fechar = QPushButton("Fechar")
        self._btn_fechar.clicked.connect(self.close)
        for b in (self._btn_node, self._btn_site, self._btn_tentar, self._btn_nav, self._btn_fechar):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            linha.addWidget(b)
        lay.addLayout(linha)
        for b in (self._btn_node, self._btn_site, self._btn_tentar, self._btn_nav):
            b.hide()

        self._status_sig.connect(self._aplicar_status)
        self._info_sig.connect(self._mostrar_info)
        self._node_sig.connect(self._sem_ou_com_node)

        self._qr_mtime = 0.0
        self._ocupado = False          # uma subida/instalação de cada vez
        self._consultando = False
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self._consultar)

        QTimer.singleShot(0, self._iniciar)

    # ── fluxo ────────────────────────────────────────────────────────────────
    def _wa(self):
        from actions import whatsapp_bridge
        return whatsapp_bridge

    def _iniciar(self) -> None:
        if self._ocupado:
            return
        self._ocupado = True
        self._btn_tentar.hide()
        self._mostrar_info("Verificando o WhatsApp…", False)

        def _vai():
            try:
                wa = self._wa()
                if not wa.node_disponivel():
                    self._node_sig.emit(False)
                    return
                self._node_sig.emit(True)
                st = wa.get_status()
                if st.get("connected"):
                    self._status_sig.emit(st)
                    return
                if not wa.is_bridge_alive():
                    self._info_sig.emit("Ligando o servidor do WhatsApp… (na primeira vez ele "
                                        "baixa os componentes e pode levar alguns minutos)", False)
                    r = wa.start_bridge(force_restart=False)
                    low = r.lower()
                    if any(x in low for x in ("falha", "erro", "não encontrado", "nao encontrado",
                                              "demorou", "não consegui", "nao consegui")):
                        self._info_sig.emit(r, True)
                        return
            except Exception as e:  # nunca deixar a janela muda
                self._info_sig.emit(f"Não consegui ligar o WhatsApp: {str(e)[:160]}", True)
            finally:
                self._ocupado = False
        threading.Thread(target=_vai, daemon=True, name="wa-qr-iniciar").start()
        self._timer.start()

    def _consultar(self) -> None:
        if self._consultando:
            return
        self._consultando = True

        def _vai():
            try:
                self._status_sig.emit(self._wa().get_status() or {})
            except Exception:
                pass
            finally:
                self._consultando = False
        threading.Thread(target=_vai, daemon=True, name="wa-qr-status").start()

    def _instalar_node(self) -> None:
        if self._ocupado:
            return
        self._ocupado = True
        self._btn_node.setEnabled(False)
        self._mostrar_info("Instalando o Node.js… isso leva de 1 a 3 minutos. "
                           "Se o Windows pedir permissão, clique em Sim.", False)

        def _vai():
            try:
                ok, msg = self._wa().instalar_node()
            except Exception as e:
                ok, msg = False, str(e)
            self._ocupado = False
            if ok:
                self._info_sig.emit(msg, False)
                QTimer.singleShot(0, self._iniciar)
            else:
                self._info_sig.emit(msg, True)
                self._node_sig.emit(False)
        threading.Thread(target=_vai, daemon=True, name="wa-instalar-node").start()

    def _abrir_navegador(self) -> None:
        try:
            self._wa()._open_whatsapp_qr_page()
        except Exception:
            pass

    # ── tela ─────────────────────────────────────────────────────────────────
    def _mostrar_info(self, texto: str, erro: bool) -> None:
        self._msg.setText(texto)
        self._msg.setStyleSheet(f"color: {C.RED if erro else C.TEXT};")
        if erro:
            self._btn_tentar.show()
            self._btn_nav.show()

    def _sem_ou_com_node(self, presente: bool) -> None:
        self._btn_node.setVisible(not presente)
        self._btn_site.setVisible(not presente)
        self._btn_node.setEnabled(True)
        if not presente:
            self._timer.stop()
            self._qr.setText("⚠\n\nFalta o Node.js")
            self._mostrar_info("O WhatsApp do NEXUS precisa do Node.js, que não está neste "
                               "computador. Clique em \"Instalar Node.js\" (automático) ou "
                               "baixe a versão LTS no site.", False)

    def _aplicar_status(self, st: dict) -> None:
        if st.get("connected"):
            self._timer.stop()
            self._qr.setPixmap(QPixmap())
            self._qr.setText("✔\n\nConectado")
            self._qr.setStyleSheet("background: #e8fff1; border-radius: 14px;"
                                   " border: 2px solid #25d366; color: #128c4a;")
            self._qr.setFont(QFont(FONT_MAIN, 16, QFont.Weight.Bold))
            self._mostrar_info("WhatsApp conectado! Já pode pedir: \"manda mensagem para…\".", False)
            self._btn_tentar.hide()
            self._btn_nav.hide()
            return
        qr = self._wa().BRIDGE_DIR / "wa_qr.png"
        if st.get("has_qr") and qr.is_file():
            try:
                mt = qr.stat().st_mtime
            except OSError:
                mt = 0.0
            if mt != self._qr_mtime:
                px = QPixmap(str(qr))
                if not px.isNull():
                    self._qr_mtime = mt
                    self._qr.setPixmap(px.scaled(
                        self.QR_LADO, self.QR_LADO, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))
                    self._mostrar_info("Escaneie o código com o celular. Ele se renova sozinho "
                                       "a cada poucos segundos.", False)
            return
        if st.get("ponte_offline"):
            if not self._ocupado:
                self._mostrar_info("O servidor do WhatsApp está desligado. Clique em "
                                   "\"Tentar de novo\".", True)
            return
        msg = str(st.get("error") or st.get("message") or "").strip()
        if msg and not self._ocupado:
            self._mostrar_info(msg, bool(st.get("error")))
        elif msg:
            self._msg.setText(msg)

    def closeEvent(self, e):
        self._timer.stop()
        super().closeEvent(e)
