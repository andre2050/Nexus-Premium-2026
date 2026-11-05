# -*- coding: utf-8 -*-
"""Ferramenta `organizar_pasta` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Separa os arquivos de uma pasta em subpastas por tipo (e desfaz).
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None):
    from actions.organizar_pasta import organizar_pasta
    return organizar_pasta(parameters=dict(parameters or {}), player=P.janela(player))


TOOL = {'name': 'organizar_pasta',
 'description': 'Organiza uma pasta separando os arquivos em subpastas por tipo (Imagens, Videos, '
                'Documentos, Instaladores...) e DESFAZ quando o dono pedir para voltar como '
                'estava. acao=organizar (padrao) com pasta = downloads, documentos, area de '
                'trabalho ou um caminho; acao=desfazer volta a ultima organizacao. QUANDO O DONO '
                "APONTAR PARA A TELA — 'organiza essa pasta', 'essa que esta aberta', 'a pasta "
                "aqui' — mande pasta='aberta' ou deixe pasta VAZIA: a ferramenta descobre sozinha "
                'qual pasta esta aberta no Explorer e, se nao houver nenhuma, olha a tela. Nunca '
                'invente um caminho a partir do que ouviu.',
 'parameters': {'type': 'OBJECT',
                'properties': {'acao': {'type': 'STRING', 'description': 'organizar | desfazer'},
                               'pasta': {'type': 'STRING',
                                         'description': 'downloads (padrao), documentos, area de '
                                                        'trabalho, imagens, ou um caminho '
                                                        'completo'}},
                'required': []},
    "handler": _rodar,
}
