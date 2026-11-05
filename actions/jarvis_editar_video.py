# -*- coding: utf-8 -*-
"""Ferramenta `editar_video` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Edita video no PC com ffmpeg; o Gemini so escreve a receita.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None, speak=None):
    from actions.editar_video import editar_video, garantir_ffmpeg_no_path
    try:
        garantir_ffmpeg_no_path()
    except Exception:
        pass
    p = dict(parameters or {})
    p.setdefault("_fala_do_dono", P.ultima_fala(speak, 60))
    return editar_video(parameters=p, player=P.janela(player), gerar=P.gerar,
                        falar=P.falar_por(speak), ouvido=None, ver=P.ver)


TOOL = {'name': 'editar_video',
 'description': 'EDITA VIDEO aqui no computador, sem mandar o video para lugar nenhum: formato do '
                'TikTok/Reels/Shorts (9:16), YouTube (16:9) ou quadrado; cortar TODOS os silencios '
                '(deixar so a parte falada); cortar ou tirar um trecho; espelhar/inverter, girar, '
                'acelerar ou camera lenta; legenda automatica; texto na tela; colocar imagem ou '
                'logo; musica de fundo; tirar ou aumentar o som; efeitos (preto e branco, vintage, '
                'zoom, tremer, cores vivas...); transicao; juntar videos; deixar leve para o '
                'WhatsApp. USE SEMPRE que o dono pedir qualquer mudanca num VIDEO (o que ele '
                'arrastou para a janela, selecionou na pasta ou citou pelo nome). Foto e '
                'editar_imagem, nao esta. Passe em `pedido` TUDO o que ele pediu, com as palavras '
                'dele. O trabalho roda em segundo plano, o NEXUS avisa falando quando fica pronto '
                'e o original nunca e alterado. Perguntou do andamento: acao=status. Mandou parar: '
                "acao=cancelar. PERGUNTA NAO E PEDIDO: 'voce edita video?' se responde, sem chamar "
                "a ferramenta. Depois do 'Pronto, o video ficou pronto', elogio ('ficou top', "
                "'ficou bom') e conversa: agradeca, nao edite de novo nem diga que ainda esta "
                'editando.',
 'parameters': {'type': 'OBJECT',
                'properties': {'pedido': {'type': 'STRING',
                                          'description': 'O que fazer no video, completo, com as '
                                                         'palavras do dono.'},
                               'video': {'type': 'STRING',
                                         'description': 'Caminho ou nome do video, so se ele '
                                                        'citou; vazio = o da janela do NEXUS ou o '
                                                        'selecionado na pasta.'},
                               'acao': {'type': 'STRING',
                                        'description': 'editar (padrao) | status | cancelar'}},
                'required': []},
    "handler": _rodar,
}
