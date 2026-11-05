"""Nexus Premium 2026 — os núcleos do hub (ui/hud_nucleos.py) e a barra de ações."""
import pytest

NUCLEOS = ["reator", "hexagono", "prisma", "cubo", "iris", "engrenagem",
           "atomo", "mandala", "espectro", "vortice"]


def test_nucleos_registrados_e_com_arte():
    from memory.config_manager import HUD_STYLES, get_hud_style
    from ui.hud import HUD_STYLE_INFO
    from ui import hud_nucleos as N
    assert list(N.NUCLEO_STYLES) == NUCLEOS
    assert set(NUCLEOS) <= set(HUD_STYLES) and set(NUCLEOS) <= set(HUD_STYLE_INFO)
    assert N.tem_arte(), "faltou assets/nucleo/*.png"
    for nid in NUCLEOS:
        for peca in N._PECAS:
            assert N._arquivo(nid, peca).exists()
    assert get_hud_style() in HUD_STYLES


@pytest.mark.parametrize("estilo", NUCLEOS)
def test_cada_nucleo_desenha_em_todos_os_estados_e_tamanhos(estilo):
    from PyQt6.QtWidgets import QApplication
    from ui.hud import HudCanvas
    _app = QApplication.instance() or QApplication([])
    h = HudCanvas("", "NEXUS")
    h._tmr.stop()
    h.hud_style = estilo
    for (w, alt) in ((480, 420), (300, 300), (700, 360)):
        h.resize(w, alt)
        for estado, fala, mudo in (("SPEAKING", True, False), ("LISTENING", False, False),
                                   ("THINKING", False, False), ("SLEEPING", False, True)):
            h.state, h.speaking, h.muted = estado, fala, mudo
            for amp in (0.0, 0.5, 1.0):
                h._amp = amp
                h._hist.append(amp)
                img = h.grab().toImage()
                assert not img.isNull() and img.width() == w
            assert h.hud_style == estilo, f"{estilo} caiu para o orbe (erro de desenho)"


def test_sem_arte_o_nucleo_cai_no_orbe(monkeypatch, tmp_path):
    from PyQt6.QtWidgets import QApplication
    from ui import hud, hud_nucleos
    _app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(hud_nucleos, "_PASTA", tmp_path)       # pasta vazia: sem arte
    h = hud.HudCanvas("", "NEXUS")
    h._tmr.stop()
    h.resize(400, 400)
    h.hud_style = "prisma"
    assert not h.grab().toImage().isNull()
    assert h.hud_style == "orb"


def test_barra_de_acoes_tem_os_onze_botoes():
    from PyQt6.QtWidgets import QApplication
    from ui.acoes_premium import BarraAcoes
    _app = QApplication.instance() or QApplication([])
    chaves = ["mic", "sempre", "interromper", "whatsapp", "remoto", "webcam",
              "cowork", "pc", "globo", "fundo", "arquivo"]
    clicados = []
    itens = [{"chave": c, "icone": "•", "nome": c, "acao": (lambda c=c: clicados.append(c))}
             for c in chaves]
    b = BarraAcoes(itens)
    assert list(b.botoes) == chaves
    b.set_estado("mic", "alerta")
    b.set_estado("webcam", "on")
    b.set_estado("nao_existe", "on")            # chave desconhecida: ignora
    assert b.botoes["mic"].estado == "alerta" and b.botoes["webcam"].estado == "on"
    b.botoes["globo"].click()
    assert clicados == ["globo"]
    b.resize(1100, 74)
    assert not b.grab().toImage().isNull()


def test_nome_premium():
    from ui._base import APP_NAME, APP_VERSION
    assert APP_NAME == "NEXUS Premium 2026"
    assert APP_VERSION.startswith("NEXUS Premium 2026 ")
