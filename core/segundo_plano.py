# -*- coding: utf-8 -*-
"""SEGUNDO PLANO — o JARVIS fica so no icone perto do relogio (01/11/2026, v1.0.37).

Pedido do Diego: um botao e uma tecla que tiram o JARVIS da tela e deixam so o
iconezinho dele na bandeja do Windows (a setinha ao lado do relogio). Enquanto
estiver assim ele NAO ouve, NAO responde e NAO executa nada — fica parado,
esperando o dono abrir a janela de novo. Vale igual no Linux.

A MARCA MORA AQUI, e nao no main nem na janela, porque quem precisa obedecer
esta espalhado pelo programa: o microfone e a voz (main.py), o controle remoto
do celular (dashboard/) e a propria janela (ui.py). E um `threading.Event` de
proposito: vale entre linhas sem trava nenhuma, e o motor que o `runner` do
main reconstroi depois de uma queda ja nasce sabendo que esta em segundo plano.

O PEDIDO PARA APARECER: com o JARVIS escondido, o dono pode clicar no atalho
de novo. O segundo JARVIS nao abre (um de cada vez) e, em vez de mandar
"procurar a janela na barra de tarefas" — onde ela NAO esta —, deixa o arquivo
`config/.pedido_abrir`. O JARVIS aberto confere esse arquivo a cada 0,7 s,
apaga e volta para a tela. Ver `pedir_para_aparecer` e `ui.py`.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

# A tecla que manda para o segundo plano. Livre no JARVIS: F2 (chave de IA),
# F4 (mudo), F11 (tela cheia) e ESC (interromper) ja tem dono.
TECLA = "F9"

EVENTO = threading.Event()

PEDIDO_ABRIR = Path(__file__).resolve().parents[1] / "config" / ".pedido_abrir"


def ligado() -> bool:
    return EVENTO.is_set()


def ligar() -> None:
    EVENTO.set()


def desligar() -> None:
    EVENTO.clear()


def _em_ingles() -> bool:
    try:
        from core.idioma import em_ingles  # noqa: PLC0415
        return bool(em_ingles())
    except Exception:
        return False


def aviso_remoto() -> str:
    """A resposta do Controle Remoto (celular) enquanto o JARVIS esta escondido."""
    if _em_ingles():
        return ("JARVIS is in the background on the computer: it is not listening "
                "and not doing anything. Open its window on the PC to use it again.")
    return ("O JARVIS esta em segundo plano no computador: nao esta ouvindo nem "
            "fazendo nada. Abra a janela dele no PC para voltar a usar.")


def pedir_para_aparecer(prazo: float = 2.5) -> bool:
    """O segundo JARVIS pede ao aberto para voltar para a tela.

    True = o aberto atendeu (apagou o pedido) e o segundo pode sair calado.
    False = ninguem atendeu no prazo (JARVIS antigo, sem esta versao, ou preso):
    o pedido e apagado e quem chamou mostra o aviso de sempre.
    """
    try:
        PEDIDO_ABRIR.parent.mkdir(parents=True, exist_ok=True)
        # WINDOWS: so quem o dono acabou de clicar pode trazer janela para a
        # frente. Este processo cede essa vez ao JARVIS aberto, senao ele so
        # piscaria na barra de tarefas.
        if os.name == "nt":
            try:
                import ctypes  # noqa: PLC0415
                ctypes.windll.user32.AllowSetForegroundWindow(-1)   # ASFW_ANY
            except Exception:
                pass
        PEDIDO_ABRIR.write_text(str(time.time()), encoding="utf-8")
    except Exception:
        return False
    limite = time.monotonic() + float(prazo)
    while time.monotonic() < limite:
        time.sleep(0.1)
        if not PEDIDO_ABRIR.exists():
            return True
    try:
        PEDIDO_ABRIR.unlink()
    except Exception:
        pass
    return False


def tem_pedido_para_aparecer() -> bool:
    """O JARVIS aberto: alguem clicou no atalho? Se sim, apaga o pedido."""
    try:
        if not PEDIDO_ABRIR.exists():
            return False
        PEDIDO_ABRIR.unlink()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        # Sem conseguir apagar, o segundo JARVIS acharia que ninguem atendeu.
        return False


__all__ = ["TECLA", "EVENTO", "ligado", "ligar", "desligar", "aviso_remoto",
           "pedir_para_aparecer", "tem_pedido_para_aparecer", "PEDIDO_ABRIR"]

if __name__ == "__main__":       # pragma: no cover - conferencia rapida
    print("segundo plano:", ligado(), "| tecla:", TECLA, "| pedido:", PEDIDO_ABRIR,
          "| python:", sys.version.split()[0])
