# -*- coding: utf-8 -*-
"""Ferramenta `executar_tarefa` — veio do JARVIS e foi adaptada ao NEXUS (v6.1.0).

O Gemini escreve um comando de PowerShell para a tarefa e o PC executa,
com a revisao de seguranca de actions/tarefa_comando.py (comando perigoso e recusado).
Gerado em 04/11/2026; a declaracao abaixo e a mesma que o JARVIS usava.
"""
from __future__ import annotations

from actions import _ponte_local as P  # noqa: F401

def _rodar(parameters=None, player=None):
    from actions.tarefa_comando import executar
    tarefa = str((parameters or {}).get("tarefa") or "").strip()
    if not tarefa:
        return "Faltou dizer qual e a tarefa."
    janela = P.janela(player)
    cmd = P.comando_powershell(tarefa)
    if not cmd:
        return "Nao consegui escrever o comando para essa tarefa agora."
    janela.write_log(f"[comando] {cmd[:160]}")
    r = executar(cmd)
    if r.get("recusado"):
        return f"Recusei esse comando por seguranca: {r.get('motivo')}. Nao executei nada."
    if r.get("ok"):
        return r.get("saida") or "Feito."
    return f"O comando falhou: {r.get('motivo') or r.get('saida') or 'erro'}"


TOOL = {'name': 'executar_tarefa',
 'description': 'Executa QUALQUER tarefa no computador do usuario — ABRIR e FECHAR programas, '
                'criar, apagar, mover, copiar, renomear, listar e zipar arquivos e pastas, ver '
                'disco, memoria, rede e processos, mexer em configuracoes do Windows, enfim '
                'qualquer coisa que o Windows faca: escreva a tarefa com o VERBO QUE O USUARIO '
                'ACABOU DE USAR nesta mensagem (se ele disse FECHAR, a tarefa e FECHAR; se disse '
                'ABRIR, e ABRIR) e NUNCA repita a tarefa da mensagem anterior.',
 'parameters': {'type': 'OBJECT',
                'properties': {'tarefa': {'type': 'STRING',
                                          'description': 'A tarefa em portugues, com todo o '
                                                         'detalhe que o usuario deu (nomes, '
                                                         'caminhos, quantidades).'}},
                'required': ['tarefa']},
    "handler": _rodar,
}
