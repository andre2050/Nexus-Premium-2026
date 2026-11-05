# -*- coding: utf-8 -*-
"""Ferramenta `hora_agora` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Hora e data lidas do relogio do PC, ja escritas como se fala.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None, speak=None):
    from actions.relogio_falado import agora_falado
    dados = agora_falado(P.ultima_fala(speak, 30))
    frase = str(dados.get("falar_assim") or "").strip()
    if not frase:
        return str(dados)
    return f"Diga ao usuario exatamente isto e nada alem: {frase}"


TOOL = {'name': 'hora_agora',
 'description': 'Diz a hora OU a data AGORA, lidas do relogio do computador, so o que foi '
                'perguntado: use SEMPRE que perguntarem que horas sao, que dia e hoje, o dia da '
                'semana, o mes ou o ano, porque voce NAO sabe a data de cabeca e a que vier da sua '
                "memoria estara errada. Repita 'falar_assim' e nada mais.",
 'parameters': {'type': 'OBJECT', 'properties': {}},
    "handler": _rodar,
}
