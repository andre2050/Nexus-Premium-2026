# -*- coding: utf-8 -*-
"""GLOBO (02/11/2026): a janela do globo, em processo separado do JARVIS.

POR QUE SEPARADO, e nao uma pagina dentro da janela principal:
  - o motor grafico do navegador embutido (Chromium) roda dentro do processo
    que o abre. Driver de video ruim derruba o processo inteiro: aqui cai so' o
    globo, o JARVIS continua falando;
  - fechou o globo, voltam os 300-500 MB que ele usa. O JARVIS nem carrega o
    Chromium enquanto ninguem pede o globo;
  - colocar uma pagina WebGL na janela principal obriga o Qt a recriar a janela
    inteira, a piscar, e muda como todos os paineis dela sao desenhados.

COMO ABRE: com o Chromium do Qt (PyQt6-WebEngine), a janela parece parte do
JARVIS. O pacote do cliente nao tem esse modulo desde a v1.0.35 (345 MB): sem ele
abre no Edge ou no Chrome em "modo aplicativo", que ja estao no PC e dao o mesmo
resultado na mesma pagina. Sem nenhum dos dois, no navegador padrao.

Chamado por core/globo.py:
    pythonw janela.py --pai <pid do JARVIS> --geo x,y,l,a [--maximizada] [--lugar "Japao"]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
JARVIS = RAIZ.parent
sys.path.insert(0, str(RAIZ))

import servidor as _srv  # noqa: E402

ARQ_ESTADO = JARVIS / "config" / ".globo.json"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def _gravar_estado(porta: int, token: str) -> None:
    try:
        ARQ_ESTADO.parent.mkdir(parents=True, exist_ok=True)
        tmp = ARQ_ESTADO.with_suffix(".tmp")
        tmp.write_text(json.dumps({"porta": porta, "token": token, "pid": os.getpid()}), encoding="utf-8")
        tmp.replace(ARQ_ESTADO)
    except OSError as exc:
        _srv.registrar(f"estado nao gravou: {exc}")


def _apagar_estado() -> None:
    try:
        dados = json.loads(ARQ_ESTADO.read_text(encoding="utf-8"))
        if dados.get("pid") == os.getpid():
            ARQ_ESTADO.unlink()
    except (OSError, ValueError):
        pass


def _pai_vivo(pid: int) -> bool:
    """O JARVIS fechou (ou caiu)? Entao o globo nao tem mais por que ficar."""
    if pid <= 0:
        return True
    try:
        import psutil  # noqa: PLC0415
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if sys.platform == "win32":
        import ctypes  # noqa: PLC0415
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        codigo = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(codigo))
        ctypes.windll.kernel32.CloseHandle(h)
        return codigo.value == 259
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _porta_livre() -> int:
    import socket  # noqa: PLC0415
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _pernas(globo, porta: int) -> None:
    try:
        from andar import Andarilho  # noqa: PLC0415
        globo.andarilho = Andarilho(porta)
    except Exception as exc:
        _srv.registrar(f"passeio sem pernas: {exc}")


def _idioma() -> str:
    try:
        sys.path.insert(0, str(JARVIS))
        from core.idioma import idioma  # noqa: PLC0415
        return idioma()
    except Exception:
        return "pt"


def _config_pagina(args, host: str) -> dict:
    cor = "#00d4ff"
    try:
        sys.path.insert(0, str(JARVIS))
        from core import tema  # noqa: PLC0415
        tema.carregar()
        cor = tema.cor("#00d4ff")
    except Exception:
        pass
    return {"idioma": _idioma(), "cor": cor, "host": host, "lugar": args.lugar or ""}


# ── com o Chromium do Qt ─────────────────────────────────────────────────────

def _abrir_com_qt(args) -> int:
    # Tudo isto precisa existir ANTES de criar o QApplication.
    if sys.platform.startswith("linux"):
        # Ubuntu 23.10+ fecha o namespace de que o sandbox do Chromium precisa, e a janela nem abre.
        # A pagina so' carrega o globo e Google/Esri/Wikipedia por HTTPS.
        try:
            if (os.geteuid() == 0
                    or Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns").read_text().strip() == "1"):
                os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
        except OSError:
            pass
    flags = [
        "--ignore-gpu-blocklist",           # placa velha na lista negra ainda roda WebGL
        "--enable-gpu-rasterization",
        "--enable-unsafe-swiftshader",      # sem placa nenhuma, WebGL por software (lento, mas abre)
        "--disable-features=Translate",
    ]
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " " + " ".join(flags)).strip()
    # As pernas do passeio (andar.py) falam com o Chromium por esta porta.
    porta_dep = args.depurar or _porta_livre()
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = f"127.0.0.1:{porta_dep}"

    from PyQt6.QtCore import QTimer, QUrl, Qt, pyqtSignal, QObject  # noqa: PLC0415
    from PyQt6.QtGui import QColor, QIcon, QKeySequence, QShortcut  # noqa: PLC0415
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings  # noqa: PLC0415
    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: PLC0415
    from PyQt6.QtWidgets import QApplication, QMainWindow  # noqa: PLC0415

    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JARVIS.CyberBot.Globo")
        except Exception:
            pass

    app = QApplication(sys.argv[:1])
    app.setApplicationName("JARVIS Globo")

    class Ponte(QObject):
        """O servidor roda em outra thread; a janela so' mexe na thread dela."""
        pedido = pyqtSignal(str, dict)

    class Pagina(QWebEnginePage):
        def javaScriptConsoleMessage(self, nivel, msg, linha, origem):
            if nivel == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                _srv.registrar(f"console: {msg[:400]} ({origem[-60:]}:{linha})")

        def createWindow(self, _tipo):
            # A pagina nunca abre outra janela do Qt. Quem precisa do navegador
            # de verdade pede pelo /api/host.
            return None

        def acceptNavigationRequest(self, url, tipo, principal):
            # Clique em link de dentro do Google Maps que levaria a pagina do
            # globo embora: vai para o navegador, o globo fica onde esta.
            if principal and tipo == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                if url.host() not in ("127.0.0.1", "localhost"):
                    webbrowser.open(url.toString())
                    return False
            return super().acceptNavigationRequest(url, tipo, principal)

    janela = QMainWindow()
    janela.setWindowTitle("JARVIS — Globo")
    icone = JARVIS / "assets" / "icons" / "jarvis.ico"
    if not icone.exists():
        achados = sorted((JARVIS / "assets").rglob("*.ico"))
        icone = achados[0] if achados else icone
    if icone.exists():
        janela.setWindowIcon(QIcon(str(icone)))
    janela.setStyleSheet("QMainWindow { background: #00060a; }")
    janela.setMinimumSize(960, 600)

    perfil_dir = JARVIS / "cache" / "globo_navegador"
    perfil = QWebEngineProfile("jarvis_globo", app)
    perfil.setPersistentStoragePath(str(perfil_dir / "dados"))
    perfil.setCachePath(str(perfil_dir / "cache"))
    perfil.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
    perfil.setHttpCacheMaximumSize(400 * 1024 * 1024)
    # Sem isto o Google trata como navegador desconhecido e mostra aviso.
    perfil.setHttpUserAgent(USER_AGENT)

    visao = QWebEngineView(janela)
    visao.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    pagina = Pagina(perfil, visao)
    pagina.setBackgroundColor(QColor("#00060a"))
    ajustes = pagina.settings()
    for atributo in (QWebEngineSettings.WebAttribute.WebGLEnabled,
                     QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled,
                     QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
                     QWebEngineSettings.WebAttribute.FullScreenSupportEnabled):
        ajustes.setAttribute(atributo, True)
    ajustes.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, False)
    visao.setPage(pagina)
    janela.setCentralWidget(visao)

    # ── o que a pagina pode pedir ────────────────────────────────────────
    ponte = Ponte()

    def alternar_tela_cheia():
        if janela.isFullScreen():
            janela.showNormal()
            if args.maximizada:
                janela.showMaximized()
        else:
            janela.showFullScreen()

    def tratar(acao: str, dados: dict):
        if acao == "fechar":
            janela.close()
        elif acao == "tela_cheia":
            alternar_tela_cheia()
        elif acao == "focar":
            trazer_para_frente()
        elif acao == "externo":
            webbrowser.open(str(dados.get("url") or ""))

    ponte.pedido.connect(tratar)

    def ao_host(acao: str, dados: dict) -> dict:
        ponte.pedido.emit(acao, dict(dados))
        return {"ok": True}

    def trazer_para_frente():
        if janela.isMinimized():
            janela.showNormal()
        janela.raise_()
        janela.activateWindow()
        if sys.platform == "win32":
            try:
                import ctypes  # noqa: PLC0415
                ctypes.windll.user32.SetForegroundWindow(int(janela.winId()))
            except Exception:
                pass

    # ── servidor ─────────────────────────────────────────────────────────
    globo = _srv.Globo(_config_pagina(args, "qt"), ao_host)
    _pernas(globo, porta_dep)
    srv = _srv.subir(globo, args.porta)
    porta = srv.server_address[1]
    _gravar_estado(porta, globo.token)
    url = f"http://127.0.0.1:{porta}/?t={globo.token}"
    _srv.registrar(f"abriu com Qt, porta {porta}")

    QShortcut(QKeySequence("F11"), janela, activated=alternar_tela_cheia)

    # ── pagina que morre (driver, memoria) volta sozinha uma vez ─────────
    quedas = {"n": 0}

    def morreu(status, codigo):
        _srv.registrar(f"pagina caiu: {status} codigo {codigo}")
        quedas["n"] += 1
        if quedas["n"] <= 2:
            globo.pagina_pronta.clear()
            QTimer.singleShot(800, lambda: visao.setUrl(QUrl(url)))
        else:
            janela.close()

    pagina.renderProcessTerminated.connect(morreu)

    # ── o JARVIS fechou? ─────────────────────────────────────────────────
    relogio = QTimer(janela)
    relogio.timeout.connect(lambda: (_pai_vivo(args.pai) or janela.close()))
    relogio.start(1500)

    # ── tamanho: o mesmo da janela do JARVIS, para parecer uma aba dela ──
    if args.geo:
        try:
            x, y, l, a = [int(v) for v in args.geo.split(",")]
            janela.setGeometry(x, y, max(960, l), max(600, a))
        except ValueError:
            janela.resize(1400, 860)
    else:
        janela.resize(1400, 860)
    if args.maximizada:
        janela.showMaximized()
    else:
        janela.show()
    if sys.platform == "win32":
        # Barra de titulo escura, igual a do JARVIS no Windows 11.
        try:
            import ctypes  # noqa: PLC0415
            valor = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(janela.winId()), 20, ctypes.byref(valor), 4)
        except Exception:
            pass
    trazer_para_frente()

    visao.setUrl(QUrl(url))
    codigo = app.exec()

    # Sem isto o Qt reclama de perfil destruido antes da pagina e demora a sair.
    visao.setPage(None)
    pagina.deleteLater()
    try:
        srv.shutdown()
    except Exception:
        pass
    _apagar_estado()
    return codigo


# ── sem o Chromium do Qt: Edge ou Chrome em modo aplicativo ──────────────────

def _achar_navegador() -> str | None:
    candidatos = []
    if sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
            if not base:
                continue
            candidatos += [
                Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(base) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            ]
    elif sys.platform == "darwin":
        candidatos += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                       Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")]
    for c in candidatos:
        if c.exists():
            return str(c)
    for nome in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"):
        achado = shutil.which(nome)
        if achado:
            return achado
    return None


def _abrir_com_navegador(args) -> int:
    fim = threading.Event()

    def ao_host(acao: str, dados: dict) -> dict:
        if acao == "fechar":
            fim.set()
        elif acao == "externo":
            webbrowser.open(str(dados.get("url") or ""))
        return {"ok": True}

    globo = _srv.Globo(_config_pagina(args, "navegador"), ao_host)
    porta_dep = args.depurar or _porta_livre()
    _pernas(globo, porta_dep)
    srv = _srv.subir(globo, args.porta)
    porta = srv.server_address[1]
    _gravar_estado(porta, globo.token)
    url = f"http://127.0.0.1:{porta}/?t={globo.token}"
    _srv.registrar(f"abriu sem Qt, porta {porta}")

    exe = _achar_navegador()
    proc = None
    if exe:
        cmd = [exe, f"--app={url}", f"--user-data-dir={JARVIS / 'cache' / 'globo_navegador_app'}",
               f"--remote-debugging-port={porta_dep}",
               "--no-first-run", "--no-default-browser-check", "--disable-sync",
               "--disable-features=Translate", "--ignore-gpu-blocklist"]
        if args.geo:
            try:
                x, y, l, a = [int(v) for v in args.geo.split(",")]
                cmd += [f"--window-position={x},{y}", f"--window-size={max(960, l)},{max(600, a)}"]
            except ValueError:
                pass
        if args.maximizada:
            cmd.append("--start-maximized")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            _srv.registrar(f"navegador nao abriu: {exc}")
    if proc is None:
        webbrowser.open(url)

    # A pagina fala com o servidor o tempo todo. Parou de falar depois de ter
    # falado = a janela foi fechada. O pid do navegador nao serve para isto: ele
    # pode ser so' o lancador, que entrega para outro processo e sai na hora.
    inicio = time.monotonic()
    while not fim.is_set():
        time.sleep(1.0)
        if not _pai_vivo(args.pai):
            break
        if globo.tem_pagina():
            continue
        if globo.ultima_pagina:
            if time.monotonic() - globo.ultima_pagina > 12:
                break
        elif time.monotonic() - inicio > 90:
            break
    if proc is not None and proc.poll() is None and not fim.is_set():
        try:
            proc.terminate()
        except OSError:
            pass
    if fim.is_set() and proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            pass
    try:
        srv.shutdown()
    except Exception:
        pass
    _apagar_estado()
    return 0


def _ja_tem_globo() -> bool:
    """Um globo so'. Dois apontariam o mesmo arquivo de estado, e a voz iria para o
    errado. O segundo pedido so' traz o primeiro para a frente."""
    try:
        e = json.loads(ARQ_ESTADO.read_text(encoding="utf-8"))
        import psutil  # noqa: PLC0415
        if not psutil.pid_exists(int(e["pid"])) or int(e["pid"]) == os.getpid():
            return False
        import urllib.request  # noqa: PLC0415
        abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(
            f"http://127.0.0.1:{e['porta']}/api/host", data=b'{"acao":"focar"}',
            headers={"Content-Type": "application/json", "X-Token": e["token"]}, method="POST")
        with abridor.open(req, timeout=2.0):
            return True
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pai", type=int, default=0)
    ap.add_argument("--geo", default="")
    ap.add_argument("--maximizada", action="store_true")
    ap.add_argument("--lugar", default="")
    ap.add_argument("--porta", type=int, default=0)
    ap.add_argument("--depurar", type=int, default=0, help="porta de depuracao do Chromium (so' teste)")
    ap.add_argument("--forcar-navegador", action="store_true", help="testa o caminho sem o Qt")
    ap.add_argument("--teste", action="store_true", help="janela avulsa, sem tocar no estado do globo aberto")
    args = ap.parse_args()

    # --teste: janela avulsa para testar sem atrapalhar o globo de quem esta usando.
    if args.teste:
        global ARQ_ESTADO
        ARQ_ESTADO = JARVIS / "cache" / ".globo_teste.json"
    elif _ja_tem_globo():
        return 0

    if not args.forcar_navegador:
        try:
            import PyQt6.QtWebEngineWidgets  # noqa: F401, PLC0415
            tem_qt = True
        except Exception as exc:
            _srv.registrar(f"sem PyQt6-WebEngine: {exc}")
            tem_qt = False
    else:
        tem_qt = False
    try:
        return _abrir_com_qt(args) if tem_qt else _abrir_com_navegador(args)
    except Exception as exc:
        _srv.registrar(f"janela caiu: {type(exc).__name__}: {exc}")
        _apagar_estado()
        raise


if __name__ == "__main__":
    sys.exit(main())
