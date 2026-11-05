# -*- coding: utf-8 -*-
"""Ferramenta `buscar_leads` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Lista de empresas reais pela busca do Google (Gemini com busca), salva em .txt.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None, speak=None):
    from actions.codex_remote import remote_codex_job
    p = dict(parameters or {})
    args = {"kind": "leads", "description": p.get("description") or "",
            "project_name": "NexusLeads", "destinos": p.get("destinos") or "",
            "abrir": p.get("abrir")}
    return remote_codex_job(parameters=args, player=P.janela(player), speak=speak)


TOOL = {'name': 'buscar_leads',
 'description': 'Busca leads comerciais reais no Google Maps e entrega uma lista em bloco de notas '
                '(.txt). Use sempre que pedirem lista de empresas, clientes em potencial, contatos '
                'comerciais, prospeccao ou leads de um segmento em uma cidade ou regiao. OS '
                'FILTROS SAO TOTALMENTE LIVRES: com WhatsApp, sem WhatsApp, com site, sem site, '
                'com telefone, sem telefone, nota minima, quantidade minima de avaliacoes, bairro, '
                'ou qualquer combinacao que o usuario pedir. Repasse em description o pedido do '
                'usuario inteiro, com quantidade, cidade e TODOS os filtros citados. Se o usuario '
                'disser onde salvar (area de trabalho, documentos, uma pasta especifica, varias '
                'pastas), coloque cada lugar em destinos. Se ele pedir para abrir o arquivo, use '
                'abrir=true. Nunca invente empresas ou contatos: informe apenas o que a ferramenta '
                'retornar.',
 'parameters': {'type': 'OBJECT',
                'properties': {'description': {'type': 'STRING',
                                               'description': 'Pedido completo do usuario: '
                                                              'segmento, cidade ou regiao, '
                                                              'quantidade e todos os filtros '
                                                              'mencionados'},
                               'destinos': {'type': 'STRING',
                                            'description': 'Onde salvar, separado por virgula. Ex: '
                                                           "'area de trabalho', 'documentos, pasta "
                                                           "Clientes'. Vazio = area de trabalho"},
                               'abrir': {'type': 'BOOLEAN',
                                         'description': 'true se o usuario pediu para abrir ou ver '
                                                        'o arquivo depois de pronto'}},
                'required': ['description']},
    "handler": _rodar,
}
