# actions/globo.py
# A ferramenta `globo` do cerebro. O caminho rapido (sem modelo) esta em core/globo_voz.py;
# aqui chega o que precisou de raciocinio: "me leva para o maior pais da Africa".

from __future__ import annotations

from core import globo as _globo
from core import globo_voz as _voz


def globo(parameters: dict | None = None, player=None) -> str:
    p = dict(parameters or {})
    acao = str(p.get("acao") or "ir").strip().lower()
    if acao == "abrir" and str(p.get("lugar") or "").strip():
        acao = "ir"     # "abre o globo na Paulista": abrir sem ir ate la' nao e' o pedido
    pedido: dict = {"acao": acao}

    if acao == "capital":
        pedido = {"acao": "ir", "tipo": "capital", "lugar": str(p.get("lugar") or "")}
    elif acao in ("ir", "street_view", "google_maps"):
        lugar = str(p.get("lugar") or "").strip()
        if lugar:
            pedido["lugar"] = lugar
        if p.get("tipo"):
            pedido["tipo"] = str(p["tipo"]).strip().lower()
    elif acao == "medir":
        pedido["origem"] = str(p.get("origem") or "")
        pedido["destino"] = str(p.get("destino") or "")
    elif acao == "modo":
        pedido["modo"] = str(p.get("modo") or "satelite").strip().lower()
    elif acao == "zoom":
        pedido["direcao"] = str(p.get("direcao") or "aproximar").strip().lower()
    elif acao == "mover":
        pedido["direcao"] = str(p.get("direcao") or "norte").strip().lower()

    geo = None
    maximizada = False
    if player is not None:
        try:
            geo, maximizada = player.geometria_para_globo()
        except Exception:
            pass
    r = _globo.pedir(pedido, geo=geo, maximizada=maximizada)
    try:
        from core.idioma import idioma  # noqa: PLC0415
        lingua = idioma()
    except Exception:
        lingua = "pt"
    fala = _voz.frase(pedido, r, lingua)
    if r.get("ok") is False and not fala:
        return f"Nao consegui no globo: {r.get('erro', '')}"
    return fala or "Feito no globo."
