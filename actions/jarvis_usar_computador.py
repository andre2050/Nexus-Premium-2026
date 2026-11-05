# -*- coding: utf-8 -*-
"""Ferramenta `usar_computador` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Usa o PC olhando a tela (cliques, digitacao, formularios). O Gemini decide
cada passo no lugar do servidor do JARVIS. A tecla ESC para na hora.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None, speak=None):
    from actions.usar_computador import usar_computador
    # So com pedido recente do usuario: o modelo nao pode assumir o mouse sozinho
    # (por exemplo, num aviso proativo).
    if not P.ultima_fala(speak, 120):
        return ("Para eu mexer no computador, o usuario precisa pedir agora, com as palavras "
                "dele. Pergunte o que ele quer que eu faca.")
    return usar_computador(parameters=dict(parameters or {}), player=P.janela(player),
                           falar=P.falar_por(speak), perguntar=None,
                           deve_parar=P.esc_apertado, narrar=False,
                           falando=P.esta_falando(speak))


TOOL = {'name': 'usar_computador',
 'description': 'Usa o computador do dono sozinho, OLHANDO a tela como uma pessoa: clica '
                '(esquerdo, direito ou duplo), digita, usa atalho, rola a pagina, preenche '
                "formulario, faz login, navega num sistema e vai ate concluir. Serve para: 'clica "
                "na pasta X', 'seleciona aquele arquivo', 'aperta o botao Entrar', cadastro em "
                'site, configuracao dentro de um programa, WhatsApp Web ou e-mail pela tela, '
                'resolver uma janela que apareceu. TAMBEM MEXE EM ARQUIVO: abrir pasta e subpasta, '
                'entrar em pasta dentro de pasta, escolher varios arquivos de uma vez, arrastar '
                'arquivo ou pasta para DENTRO de outra pasta, renomear, copiar, colar e usar o '
                'menu do botao direito. Se o dono pediu para clicar em algo, NAO pergunte onde '
                'esta: chame esta ferramenta, ela enxerga a tela. Passe em `tarefa` o objetivo '
                'completo com todos os dados que o dono deu (site, nome, texto a digitar). NAO use '
                'para abrir programa (open_app), pesquisar (web_search), tocar video '
                '(youtube_video) nem para comando simples de PC (executar_tarefa).',
 'parameters': {'type': 'OBJECT',
                'properties': {'tarefa': {'type': 'STRING',
                                          'description': 'O que fazer na tela, completo, em '
                                                         'portugues, com os dados necessarios.'}},
                'required': ['tarefa']},
    "handler": _rodar,
}
