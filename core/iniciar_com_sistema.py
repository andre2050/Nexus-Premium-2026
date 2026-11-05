# -*- coding: utf-8 -*-
"""INICIAR COM O WINDOWS — o liga/desliga da engrenagem (24/10/2026).

Pedido do Diego: o cliente marca a opcao e, dali em diante, toda vez que o PC
liga o JARVIS abre sozinho.

O jeito escolhido e o mesmo dos programas comuns: um valor na chave `Run` do
USUARIO (HKCU). Nao pede administrador — o instalador e `lowest` —, vale so para
quem marcou, e aparece em Gerenciador de Tarefas > Aplicativos de inicializacao
com o nome "JARVIS CyberBot", onde o cliente tambem consegue desligar.

O ESTADO E LIDO DO PROPRIO WINDOWS, nunca de um arquivo nosso: se o cliente
desligar pelo Gerenciador de Tarefas (que grava em `StartupApproved`, sem apagar
o `Run`), a engrenagem tem de mostrar DESLIGADA, e um .json ficaria mentindo.

No Linux a mesma opcao vira o `.desktop` de `~/.config/autostart`, que GNOME,
KDE, XFCE e Cinnamon leem ao entrar. No Mac a opcao nao aparece.

O desinstalador apaga o valor (`[Registry]` com `uninsdeletevalue` no .iss), e o
`desinstalar.sh` do Linux apaga o `.desktop`: ninguem fica com o Windows tentando
abrir um JARVIS que nao existe mais.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PASTA_APP = Path(__file__).resolve().parents[1]
NOME = "JARVIS CyberBot"

_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APROVADO = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"

_E_WINDOWS = sys.platform.startswith("win")
_E_LINUX = sys.platform.startswith("linux")

# Linux: o jarvis.sh fica um nivel acima da pasta app (ver instalar.sh).
_AUTOSTART = Path(os.path.expanduser("~/.config/autostart/jarvis-cyberbot.desktop"))


def disponivel() -> bool:
    """A opcao aparece na engrenagem? (Windows e Linux; no Mac, nao.)"""
    if _E_WINDOWS:
        return _comando_windows() is not None
    if _E_LINUX:
        return (PASTA_APP.parent / "jarvis.sh").is_file()
    return False


def _comando_windows() -> str | None:
    """O que o Windows roda ao ligar: o mesmo lancador do atalho da area de
    trabalho, que ja entra na pasta certa e chama o pythonw."""
    exe = PASTA_APP / "JARVIS-CyberBot.exe"
    return f'"{exe}"' if exe.is_file() else None


def esta_ligado() -> bool:
    try:
        if _E_WINDOWS:
            import winreg  # noqa: PLC0415
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN) as k:
                    winreg.QueryValueEx(k, NOME)
            except FileNotFoundError:
                return False
            # Desligado pelo Gerenciador de Tarefas: o primeiro byte e impar
            # (03 = desativado, 02 = ativado). Sem o valor = ativado.
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _APROVADO) as k:
                    dado, _ = winreg.QueryValueEx(k, NOME)
                if isinstance(dado, bytes) and dado and dado[0] % 2 == 1:
                    return False
            except FileNotFoundError:
                pass
            return True
        if _E_LINUX:
            return _AUTOSTART.is_file()
    except Exception:
        pass
    return False


def ligar(querer: bool) -> tuple[bool, str]:
    """Liga ou desliga. Devolve (deu_certo, motivo_se_falhou)."""
    try:
        if _E_WINDOWS:
            return _ligar_windows(querer)
        if _E_LINUX:
            return _ligar_linux(querer)
        return False, "so existe no Windows e no Linux"
    except Exception as exc:
        return False, str(exc)[:120]


def _ligar_windows(querer: bool) -> tuple[bool, str]:
    import winreg  # noqa: PLC0415
    if querer:
        comando = _comando_windows()
        if comando is None:
            return False, "nao achei o JARVIS-CyberBot.exe"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN) as k:
            winreg.SetValueEx(k, NOME, 0, winreg.REG_SZ, comando)
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, NOME)
        except FileNotFoundError:
            pass
    # Nos dois casos a marca do Gerenciador de Tarefas sai: ao ligar, porque um
    # "desativado" antigo calaria a opcao; ao desligar, para nao sobrar lixo.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _APROVADO, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NOME)
    except FileNotFoundError:
        pass
    if esta_ligado() != querer:
        return False, "o Windows nao gravou"
    return True, ""


def _ligar_linux(querer: bool) -> tuple[bool, str]:
    if not querer:
        _AUTOSTART.unlink(missing_ok=True)
        return True, ""
    sh = PASTA_APP.parent / "jarvis.sh"
    if not sh.is_file():
        return False, "nao achei o jarvis.sh"
    icone = PASTA_APP.parent / "jarvis.png"
    _AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    _AUTOSTART.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NOME}\n"
        f'Exec="{sh}"\n'
        f"Path={PASTA_APP}\n"
        f"Icon={icone}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
    return True, ""


def conferir_caminho() -> None:
    """Chamado ao abrir: se a opcao esta ligada mas aponta para outra pasta
    (o cliente reinstalou em outro lugar), aponta de novo para esta."""
    try:
        if _E_WINDOWS:
            import winreg  # noqa: PLC0415
            comando = _comando_windows()
            if comando is None:
                return
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN) as k:
                    atual, _ = winreg.QueryValueEx(k, NOME)
            except FileNotFoundError:
                return
            if str(atual).strip().lower() != comando.lower():
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN) as k:
                    winreg.SetValueEx(k, NOME, 0, winreg.REG_SZ, comando)
        elif _E_LINUX and _AUTOSTART.is_file():
            if str(PASTA_APP.parent / "jarvis.sh") not in _AUTOSTART.read_text(encoding="utf-8"):
                _ligar_linux(True)
    except Exception:
        pass
