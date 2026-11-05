"""NOMES DA TELA (17/10/2026) — o cliente troca os nomes que aparecem na janela.

Pedido do Diego: "um sistema de personalizacao de nomes, qualquer nome na
interface do JARVIS o cliente consiga alterar, tipo o nome la em cima, JARVIS,
ele pode alterar para qualquer um".

Fica em config/nomes_tela.json, so com o que o cliente mudou. Campo vazio =
o nome de fabrica. A tela le daqui ao montar e de novo quando o cliente salva
na engrenagem (aba NOMES), sem precisar reabrir o JARVIS.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ARQUIVO = BASE_DIR / "config" / "nomes_tela.json"

# (chave, rotulo na engrenagem, nome de fabrica, maximo de letras)
# nome de fabrica "" = segue o que o JARVIS ja mostra (o subtitulo muda com o
# idioma; o nome no chat segue a voz escolhida).
CAMPOS: list[tuple[str, str, str, int]] = [
    ("titulo", "Nome no alto da tela", "J.A.R.V.I.S", 18),
    ("subtitulo", "Frase embaixo do nome", "", 40),
    ("janela", "Nome da janela (barra do Windows)", "JARVIS", 40),
    ("nome_chat", "Nome dele nas mensagens do chat", "", 24),
    ("cartao_sistema", "Título do cartão SISTEMA", "SISTEMA", 22),
    ("cartao_cowork", "Título do cartão COWORK", "COWORK", 22),
    ("cartao_conversa", "Título do cartão CONVERSA", "CONVERSA", 22),
    ("botao_mute", "Botão MICROFONE", "MICROFONE", 14),
    ("botao_interrupt", "Botão INTERROMPER", "INTERROMPER", 14),
    ("botao_whatsapp", "Botão CONECTAR (WhatsApp)", "CONECTAR", 14),
    ("botao_remote", "Botão CONTROLE (remoto)", "CONTROLE", 14),
    ("botao_webcam", "Botão WEBCAM", "WEBCAM", 14),
    ("botao_cowork", "Botão COWORK", "COWORK", 14),
    ("botao_computer_use", "Botão COMPUTER USE", "COMPUTER USE", 14),
    ("botao_arquivo", "Botão ARQUIVO", "ARQUIVO", 14),
]
_MAXIMO = {c[0]: c[3] for c in CAMPOS}
# Botoes e titulos de cartao sao desenhados em MAIUSCULA (o visual do dock).
_EM_MAIUSCULA = {c[0] for c in CAMPOS if c[0].startswith(("botao_", "cartao_"))}

_trava = threading.Lock()
_cache: dict | None = None


def carregar() -> dict:
    """O que o cliente mudou ({chave: nome}). Le o arquivo uma vez so."""
    global _cache
    with _trava:
        if _cache is None:
            try:
                dados = json.loads(ARQUIVO.read_text(encoding="utf-8-sig"))
                _cache = {str(k): str(v) for k, v in dados.items()
                          if k in _MAXIMO and str(v or "").strip()} if isinstance(dados, dict) else {}
            except Exception:
                _cache = {}
        return dict(_cache)


def _limpo(chave: str, valor: str) -> str:
    v = " ".join(str(valor or "").split())[:_MAXIMO.get(chave, 40)]
    return v.upper() if chave in _EM_MAIUSCULA else v


def salvar(mudancas: dict) -> dict:
    """Grava as mudancas (valor vazio = volta ao nome de fabrica)."""
    global _cache
    atual = carregar()
    for chave, valor in (mudancas or {}).items():
        if chave not in _MAXIMO:
            continue
        v = _limpo(chave, valor)
        if v:
            atual[chave] = v
        else:
            atual.pop(chave, None)
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARQUIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ARQUIVO)
    with _trava:
        _cache = dict(atual)
    return dict(atual)


def voltar_ao_padrao() -> None:
    salvar({c[0]: "" for c in CAMPOS})


def nome(chave: str, padrao: str | None = None) -> str:
    """O nome a mostrar: o do cliente, senao `padrao`, senao o de fabrica."""
    v = carregar().get(chave, "")
    if v:
        return v
    if padrao is not None:
        return padrao
    for c in CAMPOS:
        if c[0] == chave:
            return c[2]
    return ""
