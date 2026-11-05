# -*- coding: utf-8 -*-
"""Ferramenta `digitar_na_tela` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Digita ao vivo, letra por letra, na janela aberta. ESC para.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None):
    from actions.digitar_na_tela import digitar_na_tela
    return digitar_na_tela(parameters=dict(parameters or {}), player=P.janela(player),
                           gerar=P.gerar_para_digitar, deve_parar=P.esc_apertado)


TOOL = {'name': 'digitar_na_tela',
 'description': 'DIGITA ao vivo, letra por letra, na janela que esta aberta (Bloco de Notas, Word, '
                'editor) para o dono VER o texto ou o codigo nascendo: use quando ele disser '
                "'digita', 'escreve ai', 'vai codando no bloco de notas', 'escreve nesse arquivo'. "
                'Passe em `pedido` o que escrever (ex.: codigo Python de uma calculadora completa) '
                "e em `janela` onde (bloco de notas). NAO e para criar arquivo: 'cria um codigo' e "
                "code_helper, 'cria um arquivo' e file_controller.",
 'parameters': {'type': 'OBJECT',
                'properties': {'pedido': {'type': 'STRING',
                                          'description': 'O que escrever, completo (linguagem, o '
                                                         'que o programa faz).'},
                               'janela': {'type': 'STRING',
                                          'description': 'bloco de notas | word | vscode | (vazio '
                                                         '= onde o cursor estiver)'},
                               'linguagem': {'type': 'STRING',
                                             'description': 'python, javascript... quando for '
                                                            'codigo'},
                               'conteudo': {'type': 'STRING',
                                            'description': 'Texto pronto para digitar, se voce '
                                                           'mesmo ja escreveu.'}},
                'required': []},
    "handler": _rodar,
}
