# -*- coding: utf-8 -*-
"""Ferramenta `marcar_na_tela` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

Tira um print e circula em vermelho o que o usuario procura.
O Gemini acha o item; o circulo e desenhado aqui (a captura fica intacta).
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

import io
import os
from datetime import datetime


def _rodar(parameters=None, player=None):
    from PIL import Image, ImageDraw
    alvo = str((parameters or {}).get("alvo") or (parameters or {}).get("target") or "").strip()
    if not alvo:
        return "Me diz o que voce quer que eu marque na tela: o nome do botao, do menu ou do campo."
    janela = P.janela(player)
    janela.write_log("SIS: tirando o print e procurando na tela...")
    jpeg, larg, alt = P.foto_da_tela_jpeg(85)
    pergunta = (f"Esta e a captura da tela do usuario ({larg}x{alt}). Encontre: {alvo}. "
                "Responda SO com JSON: {\"achou\": true|false, \"caixa\": [ymin, xmin, ymax, xmax], "
                "\"onde\": \"descricao curta do lugar\"} com a caixa em escala 0-1000.")
    import json
    bruto = P.ver(jpeg, pergunta, json_mime=True)
    try:
        dados = json.loads(bruto[bruto.find("{"): bruto.rfind("}") + 1])
    except Exception:
        dados = {}
    if not dados.get("achou") or len(dados.get("caixa") or []) != 4:
        return f"Olhei a tela, mas nao encontrei {alvo}."
    y0, x0, y1, x1 = [float(v) for v in dados["caixa"]]
    x0, x1 = x0 * larg / 1000, x1 * larg / 1000
    y0, y1 = y0 * alt / 1000, y1 * alt / 1000
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    d = ImageDraw.Draw(img)
    folga = max(14, int(0.25 * max(x1 - x0, y1 - y0)))
    esp = max(5, larg // 300)
    d.ellipse([x0 - folga, y0 - folga, x1 + folga, y1 + folga], outline=(230, 20, 20), width=esp)
    # seta vindo de baixo/esquerda ate a borda do circulo
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ax, ay = max(10, cx - 4 * folga), min(alt - 10, cy + 4 * folga)
    bx, by = cx - folga * 0.9, cy + folga * 0.9
    d.line([ax, ay, bx, by], fill=(230, 20, 20), width=esp)
    d.polygon([(bx, by), (bx - 3 * esp, by + 1 * esp), (bx - 1 * esp, by + 3 * esp)], fill=(230, 20, 20))
    pasta = P._PASTA_CRIACOES
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"marcacao_{datetime.now():%Y%m%d_%H%M%S}.png"
    img.save(destino)
    try:
        os.startfile(str(destino))
    except Exception:
        pass
    onde = str(dados.get("onde") or "").strip()
    return f"Pronto, marquei {alvo} em vermelho e abri a imagem." + (f" Fica {onde}." if onde else "")


TOOL = {'name': 'marcar_na_tela',
 'description': 'TIRA UM PRINT DA TELA E MARCA COM UM CIRCULO VERMELHO onde esta o item que o '
                'usuario procura, depois abre a imagem marcada para ele. Use quando ele estiver '
                "PROCURANDO algo na tela e nao achar: 'onde fica o botao X', 'nao estou achando o "
                "menu Y', 'me mostra onde esta Z', 'pode marcar pra mim'. ORDEM OBRIGATORIA: "
                'primeiro screen_process para OLHAR e DIZER onde esta; so chame esta aqui se ele '
                'disser que mesmo assim nao achou, ou se ele pedir a marcacao com todas as letras. '
                'Leva cerca de um minuto, entao avise que esta preparando.',
 'parameters': {'type': 'OBJECT',
                'properties': {'alvo': {'type': 'STRING',
                                        'description': 'O que circular, com as palavras do '
                                                       "usuario. Ex.: 'o botao Configuracao', 'o "
                                                       "menu Arquivo'"}},
                'required': ['alvo']},
    "handler": _rodar,
}
