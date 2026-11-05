# -*- coding: utf-8 -*-
"""Ferramenta `editar_imagem` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Edita a foto arrastada para a janela com o modelo de imagem do Gemini.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None, speak=None):
    from actions.codex_remote import remote_codex_job
    p = dict(parameters or {})
    args = {"kind": "image_edit", "description": p.get("description") or "",
            "imagem": p.get("imagem") or p.get("image") or "",
            "project_name": p.get("project_name") or "NexusImagem"}
    return remote_codex_job(parameters=args, player=P.janela(player), speak=speak)


TOOL = {'name': 'editar_imagem',
 'description': 'USE SEMPRE que o usuario pedir para alterar, editar, mudar, trocar, refazer, '
                'tirar, colocar, melhorar ou arrumar algo em uma FOTO OU IMAGEM que ele arrastou '
                'para a janela, escolheu no quadro de arquivo ou cujo caminho informou. Exemplos: '
                "'troque a roupa por azul', 'deixe o fundo branco', 'tire o carro do fundo', "
                "'refaca essa imagem'. Voce TEM esta capacidade: nunca responda que nao consegue "
                'editar imagens e nunca ofereca apenas descrever a foto quando o pedido e de '
                'mudanca. MAS PERGUNTA NAO E PEDIDO: se ele so quer saber SE voce edita imagens ou '
                "COMO funciona ('voce consegue editar foto?', 'da para trocar a roupa numa "
                "imagem?'), APENAS RESPONDA que sim e pergunte qual foto e o que mudar. So chame a "
                'ferramenta quando houver um pedido concreto de mudanca. REGRA CRITICA: chame a '
                "ferramenta NA MESMA RESPOSTA em que aceitar o pedido. E PROIBIDO dizer 'vou "
                "fazer', 'ja estou fazendo', 'esta processando' ou 'ja vai ficar pronta' sem ter "
                'chamado a ferramenta neste mesmo turno — sem a chamada, NADA acontece e o cliente '
                "espera por uma imagem que nunca comecou. Se o usuario responder algo como 'do seu "
                "jeito', 'como voce quiser' ou 'voce decide', isso e autorizacao: chame a "
                'ferramenta imediatamente com uma descricao criativa sua, sem fazer mais '
                'perguntas. Leva de um a tres minutos e a imagem editada e salva e aberta no '
                'computador. Se nenhuma imagem estiver carregada, peca ao usuario para arrastar a '
                'foto para a janela do NEXUS. Nao afirme que ficou pronta antes de a ferramenta '
                'responder.',
 'parameters': {'type': 'OBJECT',
                'properties': {'description': {'type': 'STRING',
                                               'description': 'O que mudar na imagem, com o maximo '
                                                              'de detalhe que o usuario deu'},
                               'imagem': {'type': 'STRING',
                                          'description': 'Caminho da imagem, apenas se o usuario '
                                                         'informou um caminho; senao deixe vazio'},
                               'project_name': {'type': 'STRING',
                                                'description': 'Nome curto para o arquivo, '
                                                               'opcional'}},
                'required': ['description']},
    "handler": _rodar,
}
