# -*- coding: utf-8 -*-
"""Ferramenta `desfazer` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Desfaz a ultima organizacao de pasta ou exclusao (restaura da Lixeira).
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None):
    from actions.desfazer import desfazer_tool
    return desfazer_tool(parameters=dict(parameters or {}), player=P.janela(player))


TOOL = {'name': 'desfazer',
 'description': 'Desfaz a ULTIMA acao do NEXUS que tem volta: uma organizacao de pasta (os '
                'arquivos voltam ao lugar) ou uma exclusao (o item e restaurado da Lixeira para '
                'onde estava). Chame quando o dono disser desfaz, volta como estava, restaura o '
                'que voce excluiu, poe de volta.',
 'parameters': {'type': 'OBJECT', 'properties': {}, 'required': []},
    "handler": _rodar,
}
