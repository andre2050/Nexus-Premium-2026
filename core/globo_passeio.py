# -*- coding: utf-8 -*-
"""O PASSEIO GUIADO (02/11/2026, pedido do Diego).

"Pedi para abrir na Avenida Paulista, em qualquer lugar do mundo, e ele vai andando
pelo Street View e me falando o que tem: 'o, aqui e' o MASP, aqui e' aquilo ali', ate
onde eu quiser que ele pare."

Como cada parada funciona, depois do que ele reprovou na primeira versao ("nao anda" e
"fala de um lugar mas esta em outro"):
  - so' para quando o lugar esta DO LADO, na rua em que ele esta andando (nao a 200 m);
  - vira a camera para o ponto exato do lugar, lendo o rumo da propria camera, explica,
    e volta a olhar para a rua;
  - lugar que nao se ve (radio, empresa, predio que ja foi demolido) nao e' parada;
  - comeca andando para o lado da rua onde tem mais coisa para ver.

Roda numa thread do JARVIS. As pernas estao em globo/andar.py; os lugares vem da
Wikipedia; a fala sai do modelo rapido e, sem resposta a tempo, do proprio artigo.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import deque

from core import globo as _globo

RAIO_BUSCA_M = 500
BUSCA_A_CADA_M = 200
LADO_MAX_M = 85          # mais longe que isto da rua, nao se ve de onde ele esta
AINDA_A_FRENTE_M = 16    # para quando o lugar esta praticamente na altura dele
JA_PASSOU_M = 45         # ficou para tras: nao volta para falar
ENTRE_PARADAS_M = 55
ESPERA_PASSO_S = 3.4     # sem sair do lugar nesse tempo, nao deu para andar
# Altura do clique no chao, no quadro: 0,5 e' o horizonte. 0,56 andou 44 e 77 m na Paulista e na Reboucas.
CLIQUE_NO_CHAO = (0.56, 0.60)
SALTOS_M = (35, 70, 120)     # onde procurar a rua, a frente, quando as fotos nao estao ligadas

_UA = "JARVIS-Globo/1.0 (assistente pessoal)"
_abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_NAO_E_PAGINA = re.compile(r"^(lista d|list of|anexo:|predefini|categoria:|portal:)", re.I)
# So' o que da para ver da rua. Sem isto, ele parava para falar de radio e de empresa.
_E_DE_VER = re.compile(
    r"\b(?:edif[ií]cio|pr[eé]dio|arranha|torre|museu|parque|pra[cç]a|largo|jardim|igreja|catedral|bas[ií]lica|"
    r"par[oó]quia|capela|mosteiro|convento|sinagoga|mesquita|templo|esta[cç][aã]o|metr[oô]|teatro|cinema|monumento|"
    r"est[aá]tua|memorial|obelisco|chafariz|fonte|shopping|centro comercial|conjunto|mercado|hospital|col[eé]gio|"
    r"escola|universidade|faculdade|biblioteca|pal[aá]cio|castelo|forte|ponte|viaduto|t[uú]nel|avenida|est[aá]dio|"
    r"arena|gin[aá]sio|hotel|casa|resid[eê]ncia|mans[aã]o|centro cultural|bairro|"
    r"building|tower|skyscraper|museum|park|square|garden|church|cathedral|basilica|chapel|monastery|temple|mosque|"
    r"synagogue|station|theat(?:er|re)|cinema|monument|statue|memorial|fountain|mall|market|hospital|school|"
    r"university|college|library|palace|castle|fort|bridge|viaduct|tunnel|stadium|arena|hotel|house|mansion|"
    r"cultural cent|plaza|gate|arch|tomb|cemetery|cemit[eé]rio|ruins|ru[ií]nas)\b", re.I)
_NAO_SE_VE = re.compile(
    r"\b(?:emissora|r[aá]dio|canal de|televis[aã]o|empresa|companhia|banco|jornal|revista|gravadora|partido|"
    r"radio station|company|newspaper|magazine)\b", re.I)
_JA_NAO_EXISTE = re.compile(r"\b(?:era|eram)\s+(?:um|uma|o|a|os|as)\b|\bfoi\s+(?:um|uma)\b|\bwas\s+(?:a|an|the)\b|\bdemolid|\bdemolished\b|\bextint", re.I)

_RE_SETA = re.compile(r"\b(northeast|northwest|southeast|southwest|north|south|east|west|nordeste|noroeste|sudeste|sudoeste|norte|sul|leste|oeste)\b")
_RUMOS = {"north": 0, "norte": 0, "northeast": 45, "nordeste": 45, "east": 90, "leste": 90, "southeast": 135, "sudeste": 135,
          "south": 180, "sul": 180, "southwest": 225, "sudoeste": 225, "west": 270, "oeste": 270, "northwest": 315, "noroeste": 315}


def _dist_m(a_lat, a_lon, b_lat, b_lon) -> float:
    r = math.pi / 180
    x = (b_lon - a_lon) * r * math.cos((a_lat + b_lat) / 2 * r)
    y = (b_lat - a_lat) * r
    return math.hypot(x, y) * 6371000


def _rumo(a_lat, a_lon, b_lat, b_lon) -> float:
    r = math.pi / 180
    y = math.sin((b_lon - a_lon) * r) * math.cos(b_lat * r)
    x = (math.cos(a_lat * r) * math.sin(b_lat * r)
         - math.sin(a_lat * r) * math.cos(b_lat * r) * math.cos((b_lon - a_lon) * r))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _ponto_a_frente(lat: float, lon: float, rumo: float, metros: float) -> tuple:
    r = math.radians(rumo)
    return (lat + metros * math.cos(r) / 111320.0,
            lon + metros * math.sin(r) / (111320.0 * max(0.01, math.cos(math.radians(lat)))))


def _dif(a: float, b: float) -> float:
    """Quanto virar de b para chegar em a: -180 a 180, positivo para a direita."""
    return (a - b + 540) % 360 - 180


def _pedir_wiki(lingua: str, params: dict) -> list:
    q = urllib.parse.urlencode({"action": "query", "format": "json", "redirects": 1, **params})
    req = urllib.request.Request(f"https://{lingua}.wikipedia.org/w/api.php?{q}", headers={"User-Agent": _UA})
    # A busca por lugar responde "too busy" de vez em quando (visto em 02/11). Tratado
    # como lista vazia, o passeio saia andando sem nada para contar e para o lado errado.
    for tentativa in range(4):
        with _abridor.open(req, timeout=6) as r:
            d = json.loads(r.read().decode("utf-8"))
        if "error" not in d:
            return list((d.get("query", {}).get("pages", {}) or {}).values())
        if tentativa < 3:
            time.sleep(0.6 + tentativa * 0.8)
    raise RuntimeError(str(d["error"].get("code")))


def _wiki_perto(lat, lon, lingua: str) -> list:
    paginas = _pedir_wiki(lingua, {
        "generator": "geosearch", "ggscoord": f"{lat:.5f}|{lon:.5f}", "ggsradius": RAIO_BUSCA_M, "ggslimit": 20,
        "prop": "extracts|coordinates|pageimages|info", "exintro": 1, "explaintext": 1, "exsentences": 3,
        "exlimit": 20, "colimit": 20, "piprop": "thumbnail", "pithumbsize": 480,
    })
    saida = []
    for p in paginas:
        co = (p.get("coordinates") or [{}])[0]
        titulo = p.get("title", "")
        texto = re.sub(r"\s*\([^)]{0,80}\)", "", p.get("extract") or "").strip()
        if "lat" not in co or not texto or _NAO_E_PAGINA.match(titulo):
            continue
        primeira = re.split(r"(?<=[.!?])\s+", texto)[0][:240]
        if (not _E_DE_VER.search(f"{titulo} {primeira}") or _JA_NAO_EXISTE.search(primeira)
                or _NAO_SE_VE.search(f"{titulo} {primeira[:120]}")):
            continue
        saida.append({"titulo": titulo, "lat": co["lat"], "lon": co["lon"], "texto": texto,
                      "foto": (p.get("thumbnail") or {}).get("source", ""),
                      "tamanho": int(p.get("length") or 0), "lingua": lingua})
    return saida


def _wiki_longe(lat, lon, lingua: str) -> list:
    """Sem texto, so' para saber para que lado da rua tem mais coisa."""
    paginas = _pedir_wiki(lingua, {
        "generator": "geosearch", "ggscoord": f"{lat:.5f}|{lon:.5f}", "ggsradius": 2500, "ggslimit": 50,
        "prop": "coordinates|info", "colimit": 50,
    })
    saida = []
    for p in paginas:
        co = (p.get("coordinates") or [{}])[0]
        if "lat" in co:
            saida.append((co["lat"], co["lon"], int(p.get("length") or 0)))
    return saida


_GENERICAS = {"estacao", "station", "metro", "de", "do", "da", "dos", "das", "the", "of", "e", "and"}


def _chave(titulo: str) -> str:
    """O mesmo lugar tem um artigo em cada lingua: "Estacao Trianon-Masp" e
    "Trianon-Masp (Sao Paulo Metro)" dao a mesma chave, e ele fala uma vez so'."""
    t = unicodedata.normalize("NFD", re.sub(r"\([^)]*\)", " ", str(titulo or "").lower()))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    palavras = sorted(p for p in re.findall(r"\w+", t) if p not in _GENERICAS)
    return " ".join(palavras) or t


def _nome_da_rua(texto: str) -> str:
    """'2300 Av. Paulista' -> 'Avenida Paulista': do jeito que o artigo da rua se chama."""
    t = re.sub(r"^\s*\d+[\w-]*\s+", "", str(texto or "")).strip()
    for curto, longo in (("Av.", "Avenida"), ("R.", "Rua"), ("Al.", "Alameda"), ("Pç.", "Praça"), ("Tv.", "Travessa"),
                         ("Rod.", "Rodovia"), ("Est.", "Estrada")):
        if t.startswith(curto + " "):
            return longo + t[len(curto):]
    return t


def _artigo_da_rua(nome: str, lingua: str):
    """O artigo com exatamente este nome. Quem so' tem nome parecido ("Estacao Paulista") nao serve."""
    if not nome:
        return None
    paginas = _pedir_wiki(lingua, {
        "titles": nome, "prop": "extracts|pageimages|info", "exintro": 1, "explaintext": 1, "exsentences": 3,
        "piprop": "thumbnail", "pithumbsize": 480,
    })
    for p in paginas:
        texto = re.sub(r"\s*\([^)]{0,80}\)", "", p.get("extract") or "").strip()
        if texto and "missing" not in p:
            return {"titulo": p.get("title", nome), "texto": texto, "foto": (p.get("thumbnail") or {}).get("source", ""),
                    "tamanho": int(p.get("length") or 0), "lingua": lingua}
    return None


class Passeio:
    def __init__(self, falar, parar_fala, falando, diag=None, persona=None, idioma="pt", ao_escrever=None):
        self._falar = falar
        self._parar_fala = parar_fala
        self._falando = falando
        self._diag = diag or (lambda *a: None)
        self._persona = persona or (lambda: "")
        self._idioma = idioma
        self._escrever = ao_escrever or (lambda t: None)
        self._id = 0
        self._ativo = False
        self._vistos: set = set()
        self._onde_ja_falou: list = []
        self._conferiu_em = 0.0

    # ── comandos ─────────────────────────────────────────────────────────
    def rodando(self) -> bool:
        return self._ativo

    def iniciar(self, lugar: str = "", tipo: str = "", geo=None, maximizada=False) -> None:
        self._id += 1
        threading.Thread(target=self._rodar, args=(self._id, lugar, tipo, geo, maximizada),
                         daemon=True, name="globo-passeio").start()

    def parar(self, avisar: bool = False) -> None:
        if not self._ativo:
            return
        self._id += 1
        self._ativo = False
        try:
            self._parar_fala()
        except Exception:
            pass
        threading.Thread(target=self._parou, args=(avisar,), daemon=True).start()

    def _parou(self, avisar: bool) -> None:
        _globo.comando("passeio", {"ativo": False}, 2.0)
        if avisar:
            time.sleep(0.2)
            self._dizer("Stopped here." if self._idioma == "en" else "Parei aqui.")

    # ── helpers ──────────────────────────────────────────────────────────
    def _rua(self, acao: str, **dados) -> dict:
        return _globo._post("/api/rua", {"acao": acao, **dados}, 9.0)

    def _dizer(self, texto: str, minha: int | None = None) -> None:
        """Fala e so' volta quando acabou. Parado no meio, a voz corta na hora."""
        fim = threading.Event()

        def boca():
            try:
                self._falar(texto, ao_primeiro_som=lambda: self._escrever(texto))
            finally:
                fim.set()

        threading.Thread(target=boca, daemon=True, name="globo-passeio-fala").start()
        limite = time.monotonic() + 40 + len(texto) * 0.12
        while not fim.wait(0.15):
            if (minha is not None and minha != self._id) or time.monotonic() > limite:
                return
            if self._pediu_parar(minha):
                return
        # A fila de audio ainda pode estar tocando depois de `_falar` voltar.
        while self._falando() and time.monotonic() < limite:
            if (minha is not None and minha != self._id) or self._pediu_parar(minha):
                return
            time.sleep(0.15)

    def _pediu_parar(self, minha) -> bool:
        """O botao PARAR da tela vem por aqui."""
        if minha is None:
            return False
        agora = time.monotonic()
        if agora - self._conferiu_em < 0.5:
            return False
        self._conferiu_em = agora
        if self._rua("estado").get("parar"):
            self.parar()
            return True
        return False

    def _frase_guia(self, item: dict, lado: str, onde: str) -> str:
        """Fala de guia pelo modelo rapido. Sem resposta a tempo, sai do proprio artigo."""
        texto = item["texto"]
        frases = re.split(r"(?<=[.!?])\s+", texto)
        reserva = " ".join(frases[:2])[:320]
        en = self._idioma == "en"
        comeco = (f"{'Here' if not lado else lado.capitalize()} is {item['titulo']}. " if en
                  else f"Olha, {lado + ' ' if lado else 'aqui '}é {item['titulo']}. ")
        pronta = comeco + (reserva if item.get("lingua") == ("en" if en else "pt") else "")
        try:
            from core.cerebro_rapido import MODELOS, _cliente_gemini  # noqa: PLC0415
            cliente = _cliente_gemini()
            if cliente is None:
                return pronta
            jeito = self._persona()
            if en:
                pedido = (f"You are JARVIS, a tour guide walking through Street View with your boss. We are at: {onde}. "
                          f"{lado or 'Right here'} is: {item['titulo']}. Facts from Wikipedia: {texto[:700]}\n"
                          "In at most 2 short sentences (35 words at most), speak in English as someone pointing at it. "
                          "Only the speech, no quotes, no markdown, no numbers in digits.")
            else:
                pedido = (f"Você é o JARVIS, guia turístico andando pelo Street View com o dono. Estamos em: {onde}. "
                          f"{lado.capitalize() if lado else 'Aqui'} está: {item['titulo']}. Dados da Wikipédia: {texto[:700]}\n"
                          f"Em no máximo 2 frases curtas (até 35 palavras), em português do Brasil, fale como quem aponta "
                          f"(\"Olha, {lado or 'aqui'} é...\"), contando a curiosidade mais interessante. "
                          f"{('Seu jeito de falar: ' + jeito + '. ') if jeito else ''}"
                          "Só a fala, sem aspas, sem markdown, sem números com muitos dígitos.")
            caixa: dict = {}
            pronto = threading.Event()

            def perguntar(modelo):
                try:
                    r = cliente.models.generate_content(model=modelo, contents=pedido)
                    if (r.text or "").strip() and "t" not in caixa:
                        caixa["t"] = r.text.strip()
                        pronto.set()
                except Exception as exc:
                    caixa["e"] = str(exc)[:120]

            # A mesma corrida do ouvido: passou de 2,2 s, o segundo modelo entra junto.
            threading.Thread(target=perguntar, args=(MODELOS[0],), daemon=True, name="globo-passeio-guia").start()
            if not pronto.wait(2.2) and len(MODELOS) > 1:
                threading.Thread(target=perguntar, args=(MODELOS[1],), daemon=True, name="globo-passeio-guia2").start()
            pronto.wait(3.8)
            fala = re.sub(r"[*_#`\"]", "", caixa.get("t", "")).strip()
            if len(fala) > 12:
                return fala
            self._diag("passeio_guia_reserva", caixa.get("e", "sem resposta a tempo"))
        except Exception as exc:
            self._diag("passeio_guia_reserva", str(exc)[:120])
        return pronta

    # ── onde estao os lugares ────────────────────────────────────────────
    def _buscar_em_fundo(self, pos: dict, lista: list) -> None:
        def buscar():
            # As duas Wikipedias: a do idioma do dono primeiro, e a em ingles cobre o resto do
            # mundo (o modelo conta em portugues do mesmo jeito). Mesmo lugar nas duas conta uma vez.
            novos: list = []
            for lingua in (("en",) if self._idioma == "en" else ("pt", "en")):
                try:
                    for n in _wiki_perto(pos["lat"], pos["lon"], lingua):
                        if not any(_dist_m(n["lat"], n["lon"], x["lat"], x["lon"]) < 60 and x["lingua"] != lingua for x in novos):
                            novos.append(n)
                except Exception as exc:
                    self._diag("passeio_sem_lugares", f"{lingua}: {exc}"[:120])
            ja = lista + [{"lat": v[0], "lon": v[1], "titulo": ""} for v in self._onde_ja_falou]
            for n in novos:
                if _chave(n["titulo"]) in self._vistos or any(
                        n["titulo"] == x["titulo"] or _dist_m(n["lat"], n["lon"], x["lat"], x["lon"]) < 25 for x in ja):
                    continue
                lista.append(n)
            self._diag("passeio_lugares", f"{len(novos)} perto de {pos['lat']:.4f},{pos['lon']:.4f}")

        threading.Thread(target=buscar, daemon=True, name="globo-passeio-wiki").start()

    def _sentido_melhor(self, pos: dict, rumo: float) -> float:
        """A rua tem dois sentidos: comeca pelo que tem mais coisa conhecida pela frente.
        Saindo do numero 2300 da Paulista para o lado errado, o MASP nunca ia aparecer."""
        pontos = []
        for lingua in (("en",) if self._idioma == "en" else ("pt", "en")):
            try:
                pontos = _wiki_longe(pos["lat"], pos["lon"], lingua)
            except Exception as exc:
                self._diag("passeio_sentido", f"{lingua}: {exc}"[:100])
            if pontos:
                break
        frente = tras = 0.0
        for la, lo, tam in pontos:
            if _dist_m(pos["lat"], pos["lon"], la, lo) < 40:
                continue
            a = abs(_dif(_rumo(pos["lat"], pos["lon"], la, lo), rumo))
            peso = math.log10(max(tam, 100))
            if a < 40:
                frente += peso
            elif a > 140:
                tras += peso
        self._diag("passeio_sentido", f"frente {frente:.0f} x tras {tras:.0f}")
        return (rumo + 180) % 360 if tras > frente * 1.15 else rumo

    def _escolher_parada(self, lugares: list, pos: dict, rumo: float | None, ultima) -> dict | None:
        """O lugar que esta na altura dele agora, do lado da rua. O mais conhecido primeiro."""
        if rumo is None:
            return None
        if ultima and _dist_m(ultima[0], ultima[1], pos["lat"], pos["lon"]) < ENTRE_PARADAS_M:
            return None
        na_altura = []
        for x in lugares:
            if _chave(x["titulo"]) in self._vistos:
                continue
            d = _dist_m(pos["lat"], pos["lon"], x["lat"], x["lon"])
            a = math.radians(_dif(_rumo(pos["lat"], pos["lon"], x["lat"], x["lon"]), rumo))
            frente = d * math.cos(a)
            lado = d * math.sin(a)
            if frente < -JA_PASSOU_M:
                self._vistos.add(_chave(x["titulo"]))       # ficou para tras
                continue
            if frente <= AINDA_A_FRENTE_M and abs(lado) <= LADO_MAX_M:
                na_altura.append((x, lado))
        if not na_altura:
            return None
        item, lado = max(na_altura, key=lambda p: p[0].get("tamanho", 0))
        return {**item, "_lado": lado}

    # ── andar ────────────────────────────────────────────────────────────
    def _esperar_street_view(self, minha: int, segundos: float = 22.0):
        fim = time.monotonic() + segundos
        while time.monotonic() < fim and minha == self._id:
            r = self._rua("pos")
            if r.get("lat") is not None:
                return r
            time.sleep(0.5)
        return None

    def _setas(self) -> list:
        """[(rumo, nome da rua, rotulo)] das setas que o Street View mostra aqui."""
        saida = []
        for rotulo in self._rua("setas").get("setas", []):
            m = _RE_SETA.search(str(rotulo).lower())
            if not m:
                continue
            nome = str(rotulo).split(",", 1)[1].strip() if "," in str(rotulo) else ""
            saida.append((float(_RUMOS[m.group(1)]), nome, rotulo))
        return saida

    def _escolher_seta(self, rumo: float, rua: str):
        """A seta que continua na mesma rua, para o mesmo lado. Sem ela, so' a que segue
        reto (a avenida pode mudar de nome). Sem nenhuma das duas, so' clicando no chao."""
        setas = self._setas()
        mesma = [(abs(_dif(g, rumo)), n, r) for g, n, r in setas if rua and n == rua and abs(_dif(g, rumo)) <= 100]
        if mesma:
            return min(mesma)
        reto = [(abs(_dif(g, rumo)), n, r) for g, n, r in setas if abs(_dif(g, rumo)) <= (32 if rua else 70)]
        return min(reto) if reto else None

    def _dar_passo(self, minha: int, pos: dict, rotulo: str):
        """Clica na seta e espera chegar. Devolve a posicao nova, ou None se nao saiu do lugar."""
        self._rua("seta", rotulo=rotulo)
        return self._esperar_sair(minha, pos, ESPERA_PASSO_S)

    def _atravessar(self, minha: int, pos: dict, rumo: float):
        """CRUZAMENTO SEM SETA (02/11/2026). A Paulista continua depois da Bela Cintra, mas ali
        o Street View so' oferece virar ou voltar: as fotos de cada quarteirao nem sempre estao
        ligadas, e ele dizia "a rua acaba aqui" no meio da avenida. Uma pessoa olha para a
        frente e clica no chao mais adiante, e e' o que ele faz. Devolve a posicao nova, ou
        None se nao deu para seguir em frente: ai' sim a rua acabou."""
        self._rua("olhar", graus=rumo)
        time.sleep(0.25)
        for fracao in CLIQUE_NO_CHAO:
            if minha != self._id:
                return None
            self._rua("chao", fracao=fracao)
            novo = self._esperar_sair(minha, pos, 2.5)
            if novo:
                d = _dist_m(pos["lat"], pos["lon"], novo["lat"], novo["lon"])
                para_frente = d >= 3 and abs(_dif(_rumo(pos["lat"], pos["lon"], novo["lat"], novo["lon"]), rumo)) <= 60
                self._diag("passeio_cruzou", f"{d:.0f} m -> {novo.get('rua')}" if para_frente else f"foi para o lado: {novo.get('rua')}")
                return novo if para_frente else None
        return None

    def _saltar(self, minha: int, pos: dict, rumo: float):
        """FOTOS SEM LIGACAO (02/11/2026). Na Champs-Elysees a foto mais perto era um caminho gravado por um
        usuario, que termina no meio da avenida sem ligacao com as fotos do carro do Google: nem seta nem clique
        no chao. Ultimo recurso: reabre o Street View mais a frente, ja olhando para onde ia. Devolve a posicao
        nova, ou None se nao tem rua para frente, e ai' volta para onde estava."""
        for metros in SALTOS_M:
            if minha != self._id:
                return None
            la, lo = _ponto_a_frente(pos["lat"], pos["lon"], rumo, metros)
            if not _globo.comando("rua_saltar", {"lat": la, "lon": lo, "rumo": rumo}, 8.0).get("ok"):
                return None
            novo = self._esperar_sair(minha, pos, 7.0)
            if not novo:
                continue
            d = _dist_m(pos["lat"], pos["lon"], novo["lat"], novo["lon"])
            if d >= 8 and abs(_dif(_rumo(pos["lat"], pos["lon"], novo["lat"], novo["lon"]), rumo)) <= 60:
                self._diag("passeio_saltou", f"{d:.0f} m -> {novo.get('rua')}")
                self._rua("olhar", graus=rumo)
                return novo
        if minha == self._id:
            _globo.comando("rua_saltar", {"lat": pos["lat"], "lon": pos["lon"], "rumo": rumo}, 8.0)
            self._esperar_sair(minha, {"pano": None, "lat": pos["lat"], "lon": pos["lon"]}, 6.0)
        return None

    def _esperar_sair(self, minha: int, pos: dict, segundos: float):
        """Espera a imagem mudar. Devolve a posicao nova, ou None se nao saiu do lugar."""
        fim = time.monotonic() + segundos
        while time.monotonic() < fim and minha == self._id:
            time.sleep(0.2)
            p = self._rua("pos")
            if p.get("lat") is None:
                continue
            if p.get("pano") != pos.get("pano") or _dist_m(pos["lat"], pos["lon"], p["lat"], p["lon"]) > 1.5:
                time.sleep(0.45)    # a imagem nova assenta antes do proximo passo
                return p
        return None

    def _rodar(self, minha: int, lugar: str, tipo: str, geo, maximizada) -> None:
        en = self._idioma == "en"
        self._ativo = True
        try:
            pedido = {"acao": "street_view"}
            if lugar:
                pedido["lugar"] = lugar
            if tipo:
                pedido["tipo"] = tipo
            ja_na_rua = bool(self._rua("pos").get("lat") is not None) and not lugar
            if not ja_na_rua:
                r = _globo.pedir(pedido, geo=geo, maximizada=maximizada)
                if r.get("ok") is False:
                    if "encontrad" in str(r.get("erro") or ""):
                        self._dizer("I couldn't find that place." if en else "Não encontrei esse lugar.")
                    else:
                        self._diag("passeio_erro", str(r.get("erro") or "")[:160])
                        self._dizer("The globe took too long to respond. Please try again." if en
                                    else "O globo demorou para responder. Tenta de novo, por favor.")
                    return
            pos = self._esperar_street_view(minha)
            if minha != self._id:
                return
            if not pos:
                self._dizer("There is no Street View here to walk on." if en else "Não tem Street View aqui para eu andar.")
                return
            _globo.comando("passeio", {"ativo": True}, 3.0)
            self._rua("estado")             # limpa um PARAR velho
            self._diag("passeio_inicio", f"{pos.get('rua')} {pos['lat']:.5f},{pos['lon']:.5f} rumo {pos.get('h')}")

            lugares: list = []
            self._buscar_em_fundo(pos, lugares)
            rumo_rua = float(pos.get("h") or 0)
            rumo_rua = self._sentido_melhor(pos, rumo_rua)
            self._rua("olhar", graus=rumo_rua)

            onde = ", ".join(x for x in (pos.get("rua"), pos.get("lugar")) if x)
            # A abertura e' a propria rua, quando ela tem artigo: "Estamos na Avenida Paulista...".
            artigo_rua = None
            try:
                artigo_rua = _artigo_da_rua(_nome_da_rua(pos.get("rua")), "en" if en else "pt")
            except Exception as exc:
                self._diag("passeio_sem_lugares", f"rua: {exc}"[:120])
            if artigo_rua:
                self._vistos.add(_chave(artigo_rua["titulo"]))
                _globo.comando("guia", {"titulo": artigo_rua["titulo"], "foto": artigo_rua["foto"], "lado": ""}, 2.0)
                self._dizer(self._frase_guia(artigo_rua, "", onde), minha)
                _globo.comando("guia", {}, 2.0)
            else:
                self._dizer("Let's walk. Just say stop whenever you want." if en
                            else "Vamos lá, vou andando e te explicando. É só falar para quando quiser.", minha)
            if minha != self._id:
                return

            rastro: deque = deque(maxlen=7)
            rastro.append(pos)
            rumo_andando = None
            buscou_em = pos
            buscou_t = time.monotonic()
            ultima_parada = None
            travas = 0
            voltou = False
            rua_atual = ""
            falando_desde = time.monotonic()

            while minha == self._id:
                if self._pediu_parar(minha):
                    return
                # Respondendo outra coisa para o dono: espera a voz acabar para seguir.
                # Com teto: essa marca ja ficou presa em True no passado.
                if self._falando() and time.monotonic() - falando_desde < 45:
                    time.sleep(0.25)
                    continue
                falando_desde = time.monotonic()

                # A Wikipedia as vezes recusa ("too busy"): sem nenhum lugar na lista, tenta de novo
                # logo, em vez de andar 200 m calado.
                agora = time.monotonic()
                if (_dist_m(buscou_em["lat"], buscou_em["lon"], pos["lat"], pos["lon"]) > BUSCA_A_CADA_M
                        or (not lugares and agora - buscou_t > 12)):
                    buscou_em = pos
                    buscou_t = agora
                    self._buscar_em_fundo(pos, lugares)

                # ── parada ───────────────────────────────────────────────
                item = self._escolher_parada(lugares, pos, rumo_andando, ultima_parada)
                if item:
                    self._vistos.add(_chave(item["titulo"]))
                    self._onde_ja_falou.append((item["lat"], item["lon"]))
                    ultima_parada = (pos["lat"], pos["lon"])
                    lado_m = item["_lado"]
                    if abs(lado_m) < 8:
                        lado = "right here" if en else "bem aqui"
                    elif lado_m > 0:
                        lado = "on your right" if en else "à sua direita"
                    else:
                        lado = "on your left" if en else "à sua esquerda"
                    onde = ", ".join(x for x in (pos.get("rua"), pos.get("lugar")) if x) or onde
                    alvo = _rumo(pos["lat"], pos["lon"], item["lat"], item["lon"])
                    self._diag("passeio_parada", f"{item['titulo']} ({lado}) a {_dist_m(pos['lat'], pos['lon'], item['lat'], item['lon']):.0f} m, rumo {alvo:.0f}")
                    _globo.comando("guia", {"titulo": item["titulo"], "foto": item["foto"], "lado": lado}, 2.0)
                    # Vira ja', enquanto o texto fica pronto: quem explica, aponta.
                    self._rua("olhar", graus=alvo)
                    fala = self._frase_guia(item, lado, onde)
                    if minha != self._id:
                        return
                    self._dizer(fala, minha)
                    if minha != self._id:
                        return
                    _globo.comando("guia", {}, 2.0)
                    self._rua("olhar", graus=rumo_rua)
                    continue

                # ── passo ────────────────────────────────────────────────
                seta = self._escolher_seta(rumo_rua, rua_atual)
                novo = None
                if seta:
                    if not rua_atual or seta[1] != rua_atual:
                        rua_atual = seta[1]
                    # Olha para onde vai. Quem anda e' a seta, mas o passeio e' para ver a rua.
                    h = pos.get("h")
                    if h is not None and abs(_dif(rumo_rua, float(h))) > 12:
                        self._rua("olhar", graus=rumo_rua)
                    novo = self._dar_passo(minha, pos, seta[2])
                if minha != self._id:
                    return
                if novo is None and (not seta or travas >= 2):
                    novo = self._atravessar(minha, pos, rumo_rua) or self._saltar(minha, pos, rumo_rua)
                    if minha != self._id:
                        return
                if novo is None:
                    travas += 1
                    if self._pediu_parar(minha):
                        return
                    agora_aqui = self._rua("pos")       # o clique pode ter levado para o lado
                    if agora_aqui.get("lat") is not None:
                        pos = agora_aqui
                    if seta and travas < 3:         # imagem demorou: tenta de novo
                        time.sleep(0.5)
                        continue
                    if voltou:
                        self._dizer("The street ends here. I stopped." if en else "A rua acaba aqui. Parei.", minha)
                        return
                    voltou = True
                    travas = 0
                    rumo_rua = (rumo_rua + 180) % 360
                    self._dizer("End of the street, heading back." if en else "A rua acaba aqui, vou voltando.", minha)
                    self._rua("olhar", graus=rumo_rua)
                    continue
                travas = 0
                pos = novo
                rastro.append(pos)
                # O rumo da rua vem do caminho ja feito, nao de um passo so': cada imagem pode
                # estar numa faixa diferente, e um passo isolado apontaria torto.
                base = rastro[0]
                if _dist_m(base["lat"], base["lon"], pos["lat"], pos["lon"]) >= 18:
                    rumo_andando = _rumo(base["lat"], base["lon"], pos["lat"], pos["lon"])
                    if abs(_dif(rumo_andando, rumo_rua)) < 60:
                        rumo_rua = rumo_andando
        except Exception as exc:
            self._diag("passeio_erro", f"{type(exc).__name__}: {exc}"[:160])
        finally:
            if minha == self._id:
                self._ativo = False
                try:
                    _globo.comando("passeio", {"ativo": False}, 2.0)
                except Exception:
                    pass
