# -*- coding: utf-8 -*-
"""Ferramenta `fechar_app` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Fecha um programa aberto pelo nome.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None):
    from actions.fechar_app import fechar_app
    return fechar_app(dict(parameters or {}), player=P.janela(player))


TOOL = {'name': 'fechar_app',
 'description': 'Fecha, encerra ou sai de um programa aberto (close/quit an app): use SEMPRE que o '
                'usuario disser fechar, encerrar, sair, matar ou tirar da tela qualquer programa, '
                'app ou janela, em portugues ou ingles, e NUNCA diga que fechou sem chamar esta '
                'ferramenta.',
 'parameters': {'type': 'OBJECT',
                'properties': {'app_name': {'type': 'STRING',
                                            'description': 'Name of the app to close, as the user '
                                                           "said it (e.g. 'bloco de notas', "
                                                           "'Chrome')"}},
                'required': ['app_name']},
    "handler": _rodar,
}
