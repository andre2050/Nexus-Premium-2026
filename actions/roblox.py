"""roblox — programa no Roblox Studio por comando de voz (5.1).

    "Nexus, instala a ponte do Roblox"                  (uma vez)
    "Nexus, programa no Roblox um script que faz o personagem pular mais alto"
    "Nexus, cria no Roblox um script de moedas que somam pontos"
    "Nexus, põe esse código no ServerScriptService como Porta"   (código pronto)
    "deu certo no Roblox?"                                (resultado do último comando)
    "o Studio está aberto?"                               (diagnóstico)

Como funciona: a descrição do que você quer vira código Luau (Gemini) e entra
numa fila local; o plugin NexusBridge, dentro do Studio, pega esse comando em até
1 segundo e cria/atualiza o script na árvore do jogo. Nada sai para servidor
nenhum além da própria API do Gemini.
"""
from __future__ import annotations

import re

from core import roblox_bridge as ponte
from core import roblox_studio as studio

_SERVICOS = {
    "serverscriptservice": ("ServerScriptService", "Script"),
    "serverscript": ("ServerScriptService", "Script"),
    "servidor": ("ServerScriptService", "Script"),
    "starterplayerscripts": ("StarterPlayerScripts", "LocalScript"),
    "local": ("StarterPlayerScripts", "LocalScript"),
    "client": ("StarterPlayerScripts", "LocalScript"),
    "replicatedstorage": ("ReplicatedStorage", "ModuleScript"),
    "modulo": ("ReplicatedStorage", "ModuleScript"),
    "module": ("ReplicatedStorage", "ModuleScript"),
    "startergui": ("StarterGui", "LocalScript"),
    "gui": ("StarterGui", "LocalScript"),
    "workspace": ("Workspace", "Script"),
}

_PROMPT = """Você escreve scripts para o Roblox Studio em Luau moderno.

Pedido do usuário: {pedido}

Regras:
- Responda SOMENTE com o código Luau, sem explicação, sem markdown, sem cercas ```.
- Use APIs atuais do Roblox (task.wait, RunService, TweenService, RemoteEvents quando precisar).
- Comente em português, de forma curta, o que cada bloco faz.
- Trate erros com pcall onde houver chamada que pode falhar.
- Se precisar de um RemoteEvent, crie-o com Instance.new e explique no comentário onde ele nasce.
- O script será inserido em {servico} como {classe} chamado "{nome}".
"""


def _limpar_codigo(texto: str) -> str:
    """Tira cercas de markdown e texto solto que o modelo às vezes devolve."""
    if not texto:
        return ""
    t = texto.strip()
    bloco = re.search(r"```(?:lua|luau)?\s*(.+?)```", t, re.S)
    if bloco:
        t = bloco.group(1)
    else:
        linhas = [l for l in t.splitlines()
                  if not l.strip().startswith(("```", "Aqui", "Claro", "Certamente"))]
        t = "\n".join(linhas)
    return t.strip()


def _alvo(servico_ou_pai: str, tipo: str) -> tuple[str, str]:
    """Aceita 'servidor', 'ServerScriptService', 'ServerScriptService/Combate'…"""
    bruto = (servico_ou_pai or "").strip()
    chave = bruto.split("/")[0].strip().lower()
    pai, classe_padrao = _SERVICOS.get(chave, ("ServerScriptService", "Script"))
    if "/" in bruto:
        pai = pai + "/" + bruto.split("/", 1)[1]
    classe = (tipo or "").strip() or classe_padrao
    if classe.lower() in ("localscript", "local"):
        classe = "LocalScript"
    elif classe.lower() in ("modulescript", "module", "modulo"):
        classe = "ModuleScript"
    elif classe.lower() not in ("script", "localscript", "modulescript"):
        classe = classe_padrao
    return pai, classe


def _garantir_ponte() -> str:
    """Liga a ponte se preciso e garante que o plugin está instalado."""
    avisos = []
    est = ponte.estado()
    if not ponte.ativa():
        msg = ponte.iniciar(est.get("porta"))
        if "Ponte ativa" not in msg:
            return msg
    porta = ponte.porta_atual() or est.get("porta") or 8899
    ok, caminho = studio.instalar_plugin(porta, est["token"])
    if not ok:
        avisos.append(f"não instalei o plugin: {caminho}")
    return "; ".join(avisos)


def roblox(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    pedido = str(parameters.get("pedido") or "").strip()
    nome = str(parameters.get("nome") or "").strip()
    servico = str(parameters.get("servico") or "").strip()
    tipo = str(parameters.get("tipo") or "").strip()
    codigo = parameters.get("codigo") or ""

    if acao in ("status", "situacao"):
        est = studio.status()
        linha = [
            f"Studio: {'instalado' if est['instalado'] else 'NÃO encontrado'}.",
            f"Plugin: {'instalado' if est['plugin'] else 'não instalado'} ({est['pasta_plugins']}).",
            f"Ponte: {'ativa na porta ' + str(ponte.porta_atual()) if ponte.ativa() else 'parada'}.",
            f"Comandos na fila: {len(ponte.pendentes())}.",
        ]
        return " ".join(linha)

    if acao in ("instalar", "instalar_ponte", "configurar"):
        aviso = _garantir_ponte()
        if aviso.startswith("Não consegui abrir a porta") or "não instalei" in aviso:
            return aviso
        est = studio.status()
        if not est["instalado"]:
            return ("Ponte ligada e plugin gravado, mas não achei o Roblox Studio instalado. "
                    "Instale em roblox.com/create que o plugin já entra na próxima abertura.")
        return ("Pronto. Plugin instalado em " + est["plugin"] +
                ". Abra o Studio, ligue 'Allow HTTP Requests' em Game Settings → Security, "
                "e use a barra NEXUS (View → Toolbars → NEXUS).")

    if acao in ("abrir", "abrir_studio"):
        ok, msg = studio.abrir(parameters.get("lugar"))
        return msg if not ok else msg + ". Se o plugin ainda não aparece, feche e abra o Studio."

    if acao in ("pendentes", "fila"):
        itens = ponte.pendentes()
        if not itens:
            return "Nenhum comando esperando o Studio."
        return f"{len(itens)} comando(s) na fila: " + ", ".join(
            f"#{c['id']} {c['tipo']}" for c in itens[:8])

    if acao in ("resultado", "resultados", "deu_certo"):
        res = ponte.resultados()
        if not res:
            return ("Nenhum resultado ainda. Se o Studio está aberto, confira se o plugin "
                    "está ligado (barra NEXUS) e se 'Allow HTTP Requests' está ativo.")
        ult = res[-1]
        return (f"Último comando #{ult['id']}: {'aplicado' if ult['ok'] else 'falhou'} — "
                f"{ult['mensagem'] or 'sem detalhe'}")

    if acao in ("programar", "criar", "gerar", "codar"):
        if not pedido:
            return "Diga o que o script deve fazer, por exemplo: um script que faz o personagem pular mais alto."
        aviso = _garantir_ponte()
        if aviso.startswith("Não consegui abrir a porta") or "não instalei" in aviso:
            return aviso

        pai, classe = _alvo(servico, tipo)
        nome_final = nome or "NexusScript"
        try:
            from core import gemini
            resposta = gemini.call(
                _PROMPT.format(pedido=pedido, servico=pai, classe=classe, nome=nome_final),
                tier=gemini.SMART, timeout_ms=60_000,
            )
            texto = getattr(resposta, "text", "") if resposta is not None else ""
        except Exception as e:
            return f"Não consegui gerar o código agora: {e}"
        if not texto:
            return ("Não recebi código do modelo (chave do Gemini configurada? quota?). "
                    "Posso receber o código pronto: diga 'põe esse código no ServerScriptService'.")
        luau = _limpar_codigo(texto)
        if not luau:
            return "O modelo devolveu algo vazio. Tente descrever o pedido de outro jeito."

        cmd_id = ponte.enfileirar("script", {"nome": nome_final, "pai": pai,
                                             "classe": classe, "codigo": luau})
        return (f"Escrevi o {classe} '{nome_final}' ({len(luau.splitlines())} linhas) e coloquei na fila "
                f"como #{cmd_id}. O Studio aplica em até 1 segundo se o plugin estiver ligado. "
                f"Depois pergunte 'deu certo no Roblox?'.")

    if acao in ("script", "colar", "enviar"):
        """Manda um código que já existe (parâmetro codigo)."""
        if not str(codigo).strip():
            return "Me passe o código Luau no campo 'codigo'."
        aviso = _garantir_ponte()
        if aviso.startswith("Não consegui abrir a porta") or "não instalei" in aviso:
            return aviso
        pai, classe = _alvo(servico, tipo)
        nome_final = nome or "NexusScript"
        cmd_id = ponte.enfileirar("script", {"nome": nome_final, "pai": pai,
                                             "classe": classe, "codigo": str(codigo)})
        return f"Enviei '{nome_final}' para {pai} (comando #{cmd_id})."

    if acao in ("peca", "part"):
        ponte.iniciar()
        cmd_id = ponte.enfileirar("part", {"nome": nome or "NexusPart",
                                           "pai": parameters.get("servico") or "Workspace"})
        return f"Criei o comando para uma peça no Workspace (#{cmd_id})."

    return ("Ações: instalar_ponte, programar, script, abrir, resultado, pendentes, status. "
            "Exemplo: 'programa no Roblox um script que dá 50 moedas ao tocar na peça'.")


TOOL = {
    "name": "roblox",
    "description": (
        "ROBLOX STUDIO — programa dentro do Studio aberto no PC do usuário. Use quando ele pedir para "
        "'programar no Roblox', 'criar um script no Roblox', 'fazer um sistema de moedas/porta/checkpoint', "
        "ou perguntar 'deu certo no Roblox'. action=instalar_ponte (uma vez: liga a ponte local e instala o "
        "plugin no Studio); action=programar com 'pedido' em linguagem natural (o código Luau é escrito pela "
        "IA e aplicado pelo plugin); action=script para enviar código pronto; action=resultado para saber se "
        "o último comando foi aplicado; action=status para diagnosticar. Serviços: ServerScriptService "
        "(padrão, Script), StarterPlayerScripts (LocalScript), ReplicatedStorage (ModuleScript), StarterGui, "
        "Workspace. Se o pedido envolver telas, use StarterGui com LocalScript."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "instalar_ponte | programar | script | resultado | pendentes | status | abrir | peca"},
            "pedido": {"type": "STRING", "description": "O que o script deve fazer, em linguagem natural"},
            "nome": {"type": "STRING", "description": "Nome do script no Studio"},
            "servico": {"type": "STRING", "description": "ServerScriptService (padrão) | StarterPlayerScripts | ReplicatedStorage | StarterGui | Workspace, ou um caminho como ServerScriptService/Combate"},
            "tipo": {"type": "STRING", "description": "Script | LocalScript | ModuleScript (padrão vem do serviço)"},
            "codigo": {"type": "STRING", "description": "Para action=script: o código Luau pronto"},
            "lugar": {"type": "STRING", "description": "Para action=abrir: caminho de um .rbxl (opcional)"},
        },
        "required": ["action"],
    },
    "handler": roblox,
}
