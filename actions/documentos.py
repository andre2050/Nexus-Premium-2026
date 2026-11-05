"""documentos — RAG local: indexa e busca nos SEUS arquivos (4.7).

    "indexa meus documentos"                     "procura o contrato do aluguel"
    "quando é a consulta médica?"                "o que diz o PDF do plano de saúde?"
    "quantos arquivos tem no índice?"

Lê PDF, DOCX, TXT, MD, CSV, JSON e LOG de uma pasta (Documents, Desktop,
Downloads por padrão, ou a pasta que você disser), divide em trechos e guarda um
índice BM25 em memory/rag_index.json — busca por palavra, offline, sem custo.
Incremental: só relê arquivo novo ou modificado. A resposta sempre traz o trecho
e o caminho do arquivo de origem, para você conferir.
"""
from __future__ import annotations



def documentos(parameters: dict, player=None) -> str:
    from core import rag as R

    acao = str(parameters.get("action") or "buscar").strip().lower()
    consulta = str(parameters.get("query") or "").strip()
    pastas = str(parameters.get("folders") or "").strip() or None
    try:
        limite = max(1, min(12, int(parameters.get("limit") or 5)))
    except (TypeError, ValueError):
        limite = 5

    try:
        if acao in ("indexar", "index", "atualizar", "indexar_documentos"):
            return R.index_folders(pastas=pastas)

        if acao in ("status", "situacao", "info"):
            return R.status()

        if acao in ("limpar", "apagar", "resetar"):
            return R.forget_all()

        if not consulta:
            return "Diga o que procurar, por exemplo: procura o contrato do aluguel."
        return R.search(consulta, k=limite)
    except Exception as e:          # nunca deixar a voz cair por causa do índice
        return f"Não consegui usar o índice de documentos: {e}"


TOOL = {
    "name": "documentos",
    "description": (
        "RAG LOCAL — busca e organiza os arquivos do próprio usuário (PDF, DOCX, TXT, MD, CSV, JSON, LOG). "
        "Use SEMPRE que a pergunta for sobre o conteúdo de um documento, uma nota, um contrato, um exame, "
        "uma planilha ou 'onde está' algum papel. Acione antes de dizer que não sabe: a resposta pode estar "
        "num arquivo local. action=indexar varre as pastas (Documents, Desktop, Downloads por padrão) e "
        "atualiza só o que mudou; action=buscar devolve os trechos mais relevantes com o arquivo de origem; "
        "action=status mostra o que está indexado; action=limpar apaga o índice. "
        "Depois de buscar, responda citando o arquivo (e a data do trecho) — nunca invente conteúdo."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "indexar | buscar | status | limpar"},
            "query": {"type": "STRING", "description": "Para buscar: o que procurar (palavras-chave ou a pergunta)"},
            "folders": {"type": "STRING", "description": "Para indexar: pastas separadas por vírgula (vazio = Documents, Desktop, Downloads)"},
            "limit": {"type": "INTEGER", "description": "Para buscar: quantos trechos devolver (padrão 5, máx 12)"},
        },
        "required": ["action"],
    },
    "handler": documentos,
}
