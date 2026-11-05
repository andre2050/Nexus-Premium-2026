# -*- coding: utf-8 -*-
"""IMPORTAR SO' QUANDO FOR USAR (02/11/2026).

Medido na abertura: `google.genai` sozinho leva 1,5 s de 2,2 s de imports num PC
rapido, e tres a quatro vezes isso num PC fraco, com a tela ainda fechada. Com este
substituto o nome continua igual para quem usa (`types.Part`, `genai.Client`), e o
modulo de verdade so' carrega na primeira vez que alguem encosta nele.

`aquecer` carrega em segundo plano logo depois da janela aparecer: a abertura fica
rapida e a primeira fala nao paga a espera.
"""
from __future__ import annotations

import importlib
import threading


class Preguicoso:
    __slots__ = ("_nome", "_modulo")

    def __init__(self, nome: str):
        object.__setattr__(self, "_nome", nome)
        object.__setattr__(self, "_modulo", None)

    def _carregar(self):
        m = object.__getattribute__(self, "_modulo")
        if m is None:
            m = importlib.import_module(object.__getattribute__(self, "_nome"))
            object.__setattr__(self, "_modulo", m)
        return m

    def __getattr__(self, item):
        return getattr(self._carregar(), item)

    def __setattr__(self, item, valor):
        setattr(self._carregar(), item, valor)

    def __repr__(self):
        return f"<Preguicoso {object.__getattribute__(self, '_nome')}>"


def aquecer(*nomes: str) -> None:
    def carregar():
        for n in nomes:
            try:
                importlib.import_module(n)
            except Exception:
                pass    # quem for usar de verdade recebe o erro na hora certa

    threading.Thread(target=carregar, name="aquecer-imports", daemon=True).start()
