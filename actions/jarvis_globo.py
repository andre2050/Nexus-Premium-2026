# -*- coding: utf-8 -*-
"""Ferramenta `globo` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Globo 3D (satelite, Street View, distancias) e o passeio guiado narrado.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

_PASSEIO = None


def _rodar(parameters=None, player=None, speak=None):
    global _PASSEIO
    p = dict(parameters or {})
    janela = P.janela(player)
    acao = str(p.get("acao") or "").strip().lower()
    if acao in ("ir", "street_view") or (acao == "abrir" and p.get("lugar")):
        try:
            from core import globo_voz as _gv
            if _gv.quer_passeio(_gv.normalizar(P.ultima_fala(speak, 30))):
                acao = "passeio"
        except Exception:
            pass
    if acao == "passeio":
        from core.globo_passeio import Passeio
        live = P.assistente(speak)
        if _PASSEIO is None:
            _PASSEIO = Passeio(
                falar=P.falar_por(speak),
                parar_fala=getattr(live, "interrupt", None) or (lambda: None),
                falando=P.esta_falando(speak),
                idioma="pt",
                ao_escrever=lambda t: janela.write_log(f"NEXUS: {t}"),
            )
        _PASSEIO.iniciar(str(p.get("lugar") or ""), str(p.get("tipo") or ""), None, False)
        return "Certo, comecei o passeio. Diga 'para' quando quiser encerrar."
    from actions.globo import globo
    return globo(parameters=p, player=janela)


TOOL = {'name': 'globo',
 'description': 'Opens and controls the NEXUS 3D Earth globe window: satellite view of every '
                'country, city, neighborhood and street, Street View, Google Maps and distance '
                'between places. Use when the user says: abre o globo, mostra o Japao no globo, '
                'vai na capital de tal pais, vai no bairro tal, entra no street view, qual a '
                'distancia de A ate B no mapa, me leva para tal lugar. When the place needs '
                'thinking (o maior pais da Africa), work out the real name and pass it in lugar. '
                'acao=passeio is the guided walk: NEXUS walks along the street in Street View and '
                'explains the landmarks by himself until the user says stop. WHENEVER the user '
                'asks to walk, andar, passear, percorrer, to show or explain pontos, lugares or '
                'pontos turisticos of a place (vai mostrando alguns pontos), use acao=passeio with '
                'lugar, NEVER acao=ir or acao=abrir. acao=abrir only opens the window: whenever a '
                'place is named, use acao=ir (or acao=passeio, as above). Always call this tool '
                'for these requests; never only answer that it was done.',
 'parameters': {'type': 'OBJECT',
                'properties': {'acao': {'type': 'STRING',
                                        'description': 'abrir | ir | capital | street_view | '
                                                       'google_maps | passeio | medir | modo | '
                                                       'zoom | mover | terra | voltar | fechar | '
                                                       'estado'},
                               'lugar': {'type': 'STRING',
                                         'description': 'Country, city, neighborhood, street or '
                                                        'landmark. For acao=capital, the country '
                                                        'or state.'},
                               'tipo': {'type': 'STRING',
                                        'description': 'Optional hint: pais | cidade | bairro | '
                                                       'rua | estado'},
                               'origem': {'type': 'STRING',
                                          'description': 'acao=medir: starting place'},
                               'destino': {'type': 'STRING',
                                           'description': 'acao=medir: destination place'},
                               'modo': {'type': 'STRING',
                                        'description': 'acao=modo: satelite | mapa | holograma'},
                               'direcao': {'type': 'STRING',
                                           'description': 'acao=zoom: aproximar | afastar. '
                                                          'acao=mover: norte | sul | leste | '
                                                          'oeste'}},
                'required': ['acao']},
    "handler": _rodar,
}
