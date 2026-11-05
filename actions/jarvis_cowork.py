# -*- coding: utf-8 -*-
"""Ferramenta `cowork` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

O programador: cria e modifica apps, jogos e sites numa pasta de projeto,
testa no PC e corrige. Antes rodava no servidor do JARVIS; agora usa o Gemini.
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

import re
import threading


def _abrir_pasta(cw, nome: str, frase: str) -> str:
    from actions.codex_remote import _resolver_pasta
    nome = re.sub(r"\b(?:do|da|no|na|pro|pra|para o|para a)?\s*co[\s-]?w[ou]rk\w*\b.*$", "", nome).strip(" ,.!?")
    pasta = _resolver_pasta(f"pasta {nome}") if nome else None
    if pasta is None:
        return "Nao entendi qual pasta. Diga o nome da pasta do projeto."
    criar = bool(re.search(r"\b(?:cria|criar|crie|nova|novo)\b", frase.lower()))
    if not pasta.exists() and not criar:
        alt = cw.pasta_de_projetos() / pasta.name
        if alt.is_dir():
            pasta = alt
        else:
            return (f"Nao achei a pasta {pasta.name}. Se quiser uma nova, diga "
                    f"'cria a pasta {pasta.name} no cowork'.")
    if not pasta.exists():
        pasta = cw.pasta_de_projetos() / pasta.name
    return cw.abrir_pasta(pasta, criar=criar)


def _rodar(parameters=None, player=None, speak=None):
    from actions.cowork import COWORK as cw
    p = dict(parameters or {})
    acao = str(p.get("acao") or "pedido").strip().lower()
    pasta = str(p.get("pasta") or "").strip()
    janela = P.janela(player)
    falar = P.falar_por(speak)
    if pasta and acao in ("pasta", "pedido"):
        r = _abrir_pasta(cw, pasta, P.ultima_fala(speak, 60) or pasta)
        if acao == "pasta" or not cw.pasta:
            return r
    if acao == "rodar":
        return cw.rodar()
    if acao == "desfazer":
        return cw.desfazer()
    if acao == "parar":
        return cw.parar()
    if acao == "pasta":
        return "Diga o nome da pasta do projeto (na Area de Trabalho ou em Documentos)."
    pedido = str(p.get("pedido") or "").strip() or P.ultima_fala(speak, 60)
    if cw.ocupado():
        return "Ainda estou trabalhando no pedido anterior do Cowork. Assim que terminar eu aviso."
    alvo = f"no projeto {cw.pasta.name}" if cw.pasta else "num projeto novo"

    def _trabalho():
        try:
            r = cw.executar_pedido(pedido, P.PONTE)
        except Exception as exc:
            r = f"O Cowork falhou: {str(exc)[:120]}"
        janela.write_log(f"NEXUS: {r}")
        falar(str(r))
    threading.Thread(target=_trabalho, daemon=True, name="cowork").start()
    return (f"Comecei a trabalhar nisso {alvo}. Leva alguns minutos: eu programo, testo e "
            "aviso quando terminar.")


TOOL = {'name': 'cowork',
 'description': 'NEXUS COWORK: o programador do NEXUS. Trabalha numa PASTA DE PROJETO do usuario: '
                'cria e modifica aplicativos, jogos, sistemas, sites e programas de verdade, testa '
                'no PC, olha a tela e corrige sozinho. Use quando o usuario pedir para '
                'programar/criar/modificar um app, jogo, sistema ou programa no projeto, falar '
                "'cowork', ou reclamar de algo do projeto (cor errada, bug, erro). acao='pedido' "
                "com o pedido COMPLETO nas palavras do usuario; acao='pasta' para abrir/escolher a "
                "pasta do projeto (pasta=nome ou caminho, opcional); 'rodar' abre o projeto; "
                "'desfazer' volta a ultima mudanca; 'parar' cancela o trabalho. O trabalho roda em "
                'segundo plano e o NEXUS avisa sozinho quando termina: so repita ao usuario a '
                'frase que a ferramenta devolver. Nao use para perguntas sobre o que voce sabe '
                'fazer: responda.',
 'parameters': {'type': 'OBJECT',
                'properties': {'acao': {'type': 'STRING',
                                        'description': 'pedido | pasta | rodar | desfazer | parar'},
                               'pedido': {'type': 'STRING',
                                          'description': 'O que o usuario quer no projeto, '
                                                         'completo'},
                               'pasta': {'type': 'STRING',
                                         'description': 'Pasta do projeto (opcional)'}},
                'required': ['acao']},
    "handler": _rodar,
}
