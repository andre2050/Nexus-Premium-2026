# -*- coding: utf-8 -*-
"""Ferramenta `vision_control` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Mouse pelos gestos da mao, com a webcam.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None):
    from actions.vision_control import vision_control
    return vision_control(parameters=dict(parameters or {}), response=None,
                          player=P.janela(player), session_memory=None)


TOOL = {'name': 'vision_control',
 'description': 'Controls the mouse using the webcam and hand gestures. Use when the user says: '
                'ativar vision control, ligar vision control, ativar controle por visao, controle '
                'por gestos, control vision, desativar vision control, desligar controle por '
                'visao, parar controle por gestos. Open hand moves the cursor with mirrored '
                'horizontal movement; pinch clicks; closed hand holds/drag. Always call this tool '
                'for these commands; never only answer that it was activated. This tool shows the '
                'webcam inside the small Vision Cam panel under SYS MONITOR, with hand skeleton '
                'overlay.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING',
                                          'description': 'start | stop | status | restart'},
                               'camera_index': {'type': 'INTEGER',
                                                'description': 'Webcam index. Default: 0'}},
                'required': ['action']},
    "handler": _rodar,
}
