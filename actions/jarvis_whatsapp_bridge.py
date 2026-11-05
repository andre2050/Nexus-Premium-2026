# -*- coding: utf-8 -*-
"""Ferramenta `whatsapp_bridge` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

WhatsApp completo pela ponte local (Baileys, Node em runtime/node).
Na primeira vez, abre a pagina com o QR Code para parear o celular.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

import atexit

_REGISTRADO = False


def _fechar_ponte():
    try:
        from actions.whatsapp_bridge import encerrar_ponte_com_calma, is_bridge_alive
        if is_bridge_alive():
            encerrar_ponte_com_calma(1.5)
    except Exception:
        pass


def _rodar(parameters=None, player=None):
    global _REGISTRADO
    from actions.whatsapp_bridge import whatsapp_action
    if not _REGISTRADO:
        atexit.register(_fechar_ponte)     # fechar o NEXUS fecha a ponte junto
        _REGISTRADO = True
    return whatsapp_action(parameters=dict(parameters or {}), player=P.janela(player))


TOOL = {'name': 'whatsapp_bridge',
 'description': 'Dedicated WhatsApp module using the local Baileys bridge. Use whenever the user '
                'says WhatsApp, Whats, Zap, QR Code do WhatsApp, conectar/desconectar WhatsApp, '
                'enviar mensagem/áudio/arquivo/pasta pelo WhatsApp, ler mensagens, listar grupos, '
                'transcrever áudio, agendar mensagem WhatsApp, alertas de mensagens ou agente '
                'WhatsApp. Do not use send_message for WhatsApp. When the user asks for multiple '
                'separate text messages to the same contact, make exactly ONE tool call with '
                'action=send_multiple_texts and put every text in messages; never make several '
                'send_text calls.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING',
                                          'description': 'connect | status | disconnect | '
                                                         'clean_session | send_text | '
                                                         'send_multiple_texts | send_audio | '
                                                         'send_file | recent_messages | '
                                                         'last_message | transcribe_audio | '
                                                         'find_contact | list_groups | '
                                                         'watch_messages | stop_watch | '
                                                         'watch_status | leave_group | '
                                                         'delete_last_sent | delete_sent_messages '
                                                         '| save_contact | schedule_message | '
                                                         'confirm_schedule | list_schedules | '
                                                         'cancel_schedule | agent_load_knowledge | '
                                                         'agent_enable | agent_disable | '
                                                         'agent_status'},
                               'to': {'type': 'STRING',
                                      'description': 'Contact, phone, chat or group name'},
                               'contact': {'type': 'STRING',
                                           'description': 'Contact or group name'},
                               'target': {'type': 'STRING',
                                          'description': 'Target contact/group/name'},
                               'message': {'type': 'STRING',
                                           'description': 'Exact message text or instruction'},
                               'messages': {'type': 'ARRAY',
                                            'items': {'type': 'STRING'},
                                            'description': 'All separate text messages for one '
                                                           'send_multiple_texts call, in sending '
                                                           'order'},
                               'file_path': {'type': 'STRING',
                                             'description': 'Local file/folder path or name to '
                                                            'send/load'},
                               'caption': {'type': 'STRING', 'description': 'Caption for media'},
                               'mode': {'type': 'STRING',
                                        'description': 'any | private | groups | contact | group'},
                               'date': {'type': 'STRING',
                                        'description': 'Schedule date, e.g. hoje or DD/MM/YYYY'},
                               'time': {'type': 'STRING',
                                        'description': 'Schedule time, e.g. 22:30'},
                               'schedule_at': {'type': 'STRING',
                                               'description': 'Full schedule date/time if '
                                                              'available'},
                               'confirm': {'type': 'BOOLEAN',
                                           'description': 'True only after user explicitly '
                                                          'confirms group leave/schedule'},
                               'limit': {'type': 'INTEGER',
                                         'description': 'Message count limit; for deletion, the '
                                                        'exact number of latest outgoing messages '
                                                        'to delete'},
                               'count': {'type': 'INTEGER',
                                         'description': 'Exact quantity of latest messages sent by '
                                                        'the user to delete, from 1 to 50'},
                               'direction': {'type': 'STRING',
                                             'description': 'incoming | outgoing | all'},
                               'phone': {'type': 'STRING', 'description': 'Phone number for alias'},
                               'name': {'type': 'STRING', 'description': 'Alias/contact name'},
                               'raw_text': {'type': 'STRING',
                                            'description': 'Original user text for scheduling '
                                                           'parser'}},
                'required': ['action']},
    "handler": _rodar,
}
