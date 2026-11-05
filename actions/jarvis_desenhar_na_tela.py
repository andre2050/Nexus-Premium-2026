# -*- coding: utf-8 -*-
"""Ferramenta `desenhar_na_tela` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Desenha de verdade no Paint (ou Photoshop/GIMP/Krita). ESC para.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None, speak=None):
    from actions.desenhar_na_tela import desenhar_na_tela
    return desenhar_na_tela(parameters=dict(parameters or {}), player=P.janela(player),
                            gerar=P.gerar, falar=P.falar_por(speak),
                            deve_parar=P.esc_apertado, olhar=P.ver)


TOOL = {'name': 'desenhar_na_tela',
 'description': 'DESENHA de verdade num editor de imagem (Paint, e tambem Photoshop/GIMP/Krita) '
                "quando o dono disser 'desenha', 'faz um desenho', 'desenha uma casa no Paint', "
                "'rabisca um gato', 'ilustra'. O NEXUS abre o Paint sozinho, deixa a folha do "
                'tamanho da janela e desenha peca por peca com as ferramentas de verdade '
                '(retangulo, oval, triangulo, estrela, lapis), com cor de contorno, cor de dentro '
                'e espessura. NAO precisa de computer use. Se o dono tiver mandado uma FOTO e '
                "falar nela ('desenha essa foto', 'usa essa imagem como referencia'), passe "
                '`referencia` (ou deixe vazio que ele pega a imagem do quadro de arquivo): a foto '
                "vira desenho. Se ele pedir para desenhar EM CIMA da foto ('poe um chapeu nessa "
                "foto'), a foto e aberta no Paint e o desenho vai por cima. NAO use para gerar "
                'arquivo de imagem por IA (isso e editar_imagem) nem para clicar na tela (isso e '
                'usar_computador).',
 'parameters': {'type': 'OBJECT',
                'properties': {'pedido': {'type': 'STRING',
                                          'description': "O que desenhar, com detalhe: 'uma casa "
                                                         "com sol, arvore e uma nuvem'."},
                               'programa': {'type': 'STRING',
                                            'description': 'paint (padrao) | photoshop | gimp | '
                                                           'krita | paint.net'},
                               'referencia': {'type': 'STRING',
                                              'description': 'Caminho de uma foto para servir de '
                                                             'referencia. Vazio = a imagem que o '
                                                             'dono arrastou para a janela.'},
                               'estilo': {'type': 'STRING',
                                          'description': 'Com referencia: colorido (padrao) ou '
                                                         'contorno (so o traco preto, tipo '
                                                         'esboco).'}},
                'required': []},
    "handler": _rodar,
}
