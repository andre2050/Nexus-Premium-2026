"""Servidores MCP — ferramentas externas padronizadas.

Três modos numa ação só: 'status' (o que está configurado), 'listar' (que
ferramentas um servidor oferece) e 'chamar' (executar uma ferramenta do
servidor com argumentos). Os servidores ficam em config/mcp_servers.json; nada
é iniciado sem estar listado ali.
"""

import json

from core import mcp_client


def mcp(parameters, **_):
    params = parameters or {}
    acao = str(params.get("acao") or "status").strip().lower()
    servidor = str(params.get("servidor") or "").strip()

    if acao in ("status", "estado", "servidores"):
        return mcp_client.status()

    if not servidor:
        return "Diga qual servidor MCP usar. " + mcp_client.status()

    if acao in ("listar", "ferramentas", "list"):
        return mcp_client.list_tools(servidor)

    if acao in ("chamar", "executar", "call"):
        ferramenta = str(params.get("ferramenta") or "").strip()
        args = params.get("argumentos")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                return "O campo 'argumentos' precisa ser um JSON válido."
        if not isinstance(args, dict):
            args = {}
        return mcp_client.call_tool(servidor, ferramenta, args)

    return "Ação desconhecida. Use status, listar ou chamar."


TOOL = {
    "name": "mcp",
    "description": (
        "Usa servidores MCP (Model Context Protocol) configurados pelo usuário: "
        "é assim que o assistente alcança ferramentas externas padronizadas — "
        "repositórios de código, bancos de dados, sistemas da empresa, APIs. "
        "Ações: 'status' (padrão) mostra os servidores configurados; 'listar' "
        "mostra as ferramentas de um servidor; 'chamar' executa uma ferramenta "
        "com 'argumentos' em JSON. Sempre 'listar' antes de 'chamar' se ainda não "
        "souber o nome exato da ferramenta e os parâmetros dela."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "acao": {"type": "STRING",
                     "description": "status (padrão), listar ou chamar"},
            "servidor": {"type": "STRING",
                         "description": "Nome do servidor MCP em config/mcp_servers.json"},
            "ferramenta": {"type": "STRING",
                           "description": "Nome da ferramenta do servidor (para 'chamar')"},
            "argumentos": {"type": "STRING",
                           "description": "Objeto JSON com os argumentos da ferramenta"},
        },
        "required": [],
    },
    "handler": mcp,
}
