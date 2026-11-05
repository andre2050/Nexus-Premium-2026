"""MODELO de skill — copie para 'minha_skill.py' (sem o _ na frente) e edite.

Uma skill é só este arquivo: um dict TOOL no fim e uma função que faz o
trabalho. O app carrega tudo o que estiver em skills/ na abertura.

Regras curtas:
  • 'name' tem que ser único (não pode repetir o nome de uma ação do app);
  • 'description' é o que o modelo lê para decidir quando usar — escreva o
    gatilho ("use quando o usuário pedir X"), não a implementação;
  • 'parameters' segue o formato de função do Gemini: type OBJECT + properties;
  • o handler recebe parameters e deve devolver uma STRING (é o que volta para
    a conversa). Erros: devolva uma frase explicando, não levante exceção.
"""

from pathlib import Path


def contar_linhas(parameters, **_):
    caminho = (parameters or {}).get("caminho") or ""
    if not caminho:
        return "Diga o caminho do arquivo."
    try:
        n = len(Path(caminho).expanduser().read_text(encoding="utf-8", errors="replace").splitlines())
        return f"{n} linha(s) em {caminho}."
    except Exception as e:
        return f"Não consegui ler {caminho}: {e}"


TOOL = {
    "name": "contar_linhas",
    "description": "Conta as linhas de um arquivo de texto. Use quando o usuário perguntar o tamanho de um arquivo.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"caminho": {"type": "STRING", "description": "Caminho do arquivo"}},
        "required": ["caminho"],
    },
    "handler": contar_linhas,
}
