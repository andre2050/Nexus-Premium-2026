# Skills do NEXUS

Solte aqui um arquivo `.py` e ele vira ferramenta nova na próxima abertura — sem
editar nenhum arquivo do núcleo. O formato é o mesmo das ações:

```python
def minha_ferramenta(parameters: dict, player=None) -> str:
    return "resultado"

TOOL = {
    "name": "minha_ferramenta",
    "description": "O que ela faz (o modelo lê isto para decidir quando usar).",
    "parameters": {
        "type": "OBJECT",
        "properties": {"texto": {"type": "STRING", "description": "..."}},
        "required": ["texto"],
    },
    "handler": minha_ferramenta,
}
```

Regras: nome único (não pode repetir uma ação existente), arquivo que começa com
`_` é ignorado (use para modelos, como o `_exemplo.py`), e erro ao carregar só
desliga aquela skill — o resto do NEXUS continua funcionando.
