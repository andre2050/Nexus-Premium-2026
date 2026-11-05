# -*- coding: utf-8 -*-
"""PC FRACO (02/11/2026): quem decide o que este computador aguenta.

Medido nos clientes: no i5 650 do Wil o whisper levava 26 a 59 s por fala, com o
JARVIS em 70% do PC; pelo ouvido da nuvem caiu para 4 a 7 s, com 2% parado. No i7-5500U
do CSNOTE, 14 a 110 s contra 1,4 a 3,9 s. Quatro nucleos ou menos ja sofrem.

Uma placa NVIDIA resolve o ouvido por si so: essa conta fica no `_preparar_cuda` do
main.py, nao aqui. Forcar um lado: config/pc_fraco.json {"fraco": true} ou false.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ARQ = Path(__file__).resolve().parents[1] / "config" / "pc_fraco.json"
_cache: bool | None = None
_motivo = ""


def _tem_avx2() -> bool:
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415
            return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))  # PF_AVX2_INSTRUCTIONS_AVAILABLE
        except Exception:
            return True
    try:
        return " avx2 " in Path("/proc/cpuinfo").read_text(errors="ignore")
    except Exception:
        return True


def e_fraco() -> bool:
    global _cache, _motivo
    if _cache is not None:
        return _cache
    try:
        forcado = json.loads(_ARQ.read_text(encoding="utf-8")).get("fraco")
        if isinstance(forcado, bool):
            _cache, _motivo = forcado, "escolhido em config/pc_fraco.json"
            return _cache
    except (OSError, ValueError):
        pass
    try:
        import psutil  # noqa: PLC0415
        nucleos = psutil.cpu_count(logical=False) or psutil.cpu_count() or 4
        ram_gb = psutil.virtual_memory().total / 2**30
    except Exception:
        nucleos, ram_gb = 4, 8
    motivos = []
    if nucleos <= 4:
        motivos.append(f"{nucleos} nucleos")
    if ram_gb < 9:
        motivos.append(f"{ram_gb:.0f} GB de memoria")
    if not _tem_avx2():
        motivos.append("processador sem AVX2")
    _cache = bool(motivos)
    _motivo = ", ".join(motivos)
    return _cache


def motivo() -> str:
    e_fraco()
    return _motivo
