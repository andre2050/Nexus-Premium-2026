# -*- coding: utf-8 -*-
"""Ferramenta `codex_remote` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Cria sites e imagens com o Gemini do usuario (antes ia para o servidor do JARVIS).
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None, speak=None):
    from actions.codex_remote import remote_codex_job
    return remote_codex_job(parameters=dict(parameters or {}), player=P.janela(player), speak=speak)


TOOL = {'name': 'codex_remote',
 'description': 'Creation tool for customer-facing websites and image files. Use this for any '
                'request to create or update a website/project or to create an image. REGRA '
                'CRITICA — PERGUNTA NAO E PEDIDO. So chame esta ferramenta quando o usuario MANDAR '
                'criar algo concreto. NUNCA chame quando ele estiver apenas perguntando se voce '
                "consegue, o que voce sabe fazer, ou como funciona. NAO chame: 'voce consegue "
                "criar imagens?', 'voce faz site?', 'o que voce sabe fazer?', 'da para criar uma "
                "imagem com voce?', 'voce cria logo?'. Nesses casos APENAS RESPONDA em uma frase "
                "que sim, voce cria, e pergunte o que ele quer. CHAME: 'cria uma imagem de um "
                "gato', 'faz um site para a minha loja', 'me gera uma logo azul', 'pode criar do "
                "seu jeito'. Na duvida entre perguntar e mandar, RESPONDA em vez de chamar: "
                'perguntar de volta custa uma frase, e criar por engano custa um minuto de espera. '
                "It returns a real verified file to the user's Desktop. Never claim success unless "
                'the tool returns a verified file path. ANTES de chamar esta ferramenta, e SEMPRE '
                'no mesmo turno em que a chama, diga ao usuario UMA frase curta em portugues '
                "avisando que voce ja comecou e que leva cerca de um minuto (exemplo: 'Pode "
                "deixar, chefe, ja comecei — me da um minutinho'). Nunca fique calado ao iniciar "
                'este trabalho: o silencio faz o usuario achar que o programa travou. Isto NAO '
                'contradiz a regra de nao prometer sem agir, porque a chamada acontece '
                'imediatamente depois da frase.',
 'parameters': {'type': 'OBJECT',
                'properties': {'kind': {'type': 'STRING', 'description': 'site or image'},
                               'description': {'type': 'STRING',
                                               'description': 'Detailed requested site or image'},
                               'project_name': {'type': 'STRING',
                                                'description': 'Optional project or file name'}},
                'required': ['kind', 'description']},
    "handler": _rodar,
}
