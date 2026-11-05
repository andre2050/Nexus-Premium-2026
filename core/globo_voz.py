# -*- coding: utf-8 -*-
"""O GLOBO POR VOZ (02/11/2026): entende a frase sem passar pelo cerebro.

Pedido do Diego: "ir falando em tempo real com o Jarvis e dar comando, tipo Jarvis vai
na capital tal, pais tal, bairro tal, cidade tal, e ele ir fazendo em tempo real".

Por que aqui e nao no modelo: pelo cerebro cada frase custa de 1 a 5 s de rede, e o
globo so' comeca a andar depois disso. Aqui a frase vira comando em menos de 1 ms: o
tempo que sobra e' o da transcricao. O que nao for claramente um comando do globo
devolve None e segue para o cerebro, que tambem tem a ferramenta `globo` (e resolve o
que precisa de raciocinio: "me leva para o maior pais da Africa").

`interpretar` recebe a frase JA NORMALIZADA: minuscula, sem acento, sem pontuacao e
sem o "Jarvis" (ver `_rede_do_globo` no main.py).
"""
from __future__ import annotations

import re

# O whisper escreve Street View de muitos jeitos. O proprio Diego digitou "Stream View".
_ST = (r"(?:street|streat|stret|strit|stream|strim|estreet|estrit|estrite|istrit|extrit|estriti)"
       r"\s*(?:view|viu|vew|vieu|vil|vio)")
_RE_ST = re.compile(rf"\b{_ST}\b|\bstreetview\b|\bvisao (?:de|da) rua\b|\bmodo rua\b")
_RE_ST_SOLTO = re.compile(
    r"^(?:(?:me )?(?:entra|entre|entrar|desce|desca|descer|anda|andar|ande|poe|coloca|abre|abra|mostra|mostre|quero ver|ver)\s+"
    r"(?:(?:na|a|pela)\s+)?rua|andar na rua|ver a rua)$")

_RE_MAPS = re.compile(r"\b(?:google\s*maps|googlemaps|no maps|o maps)\b")

# "Global" e' como o whisper ouve "globo" muitas vezes (visto no uso real, 02/11).
_ERROS_DO_GLOBO = r"golbulo|globulo|gobulo|golbo|goblo|globu|globinho"     # ditos "globo", ouvidos errado
_PALAVRA_GLOBO = rf"(?:globo terrestre|globo|global|{_ERROS_DO_GLOBO}|planeta terra|terra 3d|earth view|mapa mundi|mapa do mundo|globe)"
_RE_ABRIR = re.compile(
    rf"^(?:(?:por favor|quero|eu quero|pode)\s+)*(?:me\s+)?"
    rf"(?:abre|abra|abrir|liga|ligue|ligar|ativa|ative|ativar|mostra|mostre|mostrar|ver|inicia|inicie|open|show)\s+"
    rf"(?:o\s+|a\s+|the\s+|me\s+)*{_PALAVRA_GLOBO}\b(.*)$")
_RE_FECHAR = re.compile(
    rf"^(?:fecha|feche|fechar|encerra|encerre|desliga|desligue|sai do|sair do|close)\s+(?:o\s+|the\s+)?{_PALAVRA_GLOBO}\b")
_RE_NO_GLOBO = re.compile(rf"\s+(?:no|na|on the)\s+(?:{_PALAVRA_GLOBO}|mapa)\s*$")

_VERBOS_FORTES = (r"vai|va|ir|voa|voe|voar|leva|leve|levar|viaja|viaje|viajar|segue|siga|seguir|bora|partiu|"
                  r"navega|navegue|desce|desca|passa|passe|chega|chegue|entra|entre|entrar|go|fly|take")
_VERBOS_MOSTRAR = (r"mostra|mostre|mostrar|procura|procure|procurar|busca|busque|buscar|acha|ache|achar|encontra|"
                   r"encontre|encontrar|localiza|localize|localizar|abre|abra|abrir|ve|veja|ver|olha|olhe|olhar|"
                   r"find|show|locate")
_PREFIXO = r"^(?:(?:agora|entao|ai|e|por favor|pode|tipo|quero|eu quero|queria|gostaria de|bora|vamos|vamo)\s+)*"
_RE_FORTE = re.compile(rf"{_PREFIXO}(?:me\s+)?(?:{_VERBOS_FORTES})\s+(?:me\s+|us\s+)?(.+)$")
_RE_MOSTRAR = re.compile(rf"{_PREFIXO}(?:me\s+)?(?:{_VERBOS_MOSTRAR})\s+(?:me\s+)?(.+)$")
_PREP = (r"(?:para|pra|pro|pros|pras|ate|ao|aos|a|as|o|os|no|na|nos|nas|em|num|numa|de|do|da|dos|das|"
         r"to|the|in|at|of|ver|conhecer|visitar|la|ali)")
_RE_TEM_PREP = re.compile(r"^(?:para|pra|pro|pros|pras|ate|ao|aos|a|as|no|na|nos|nas|em|num|numa|to)\s+")

_FIM_INUTIL = re.compile(r"\s+(?:por favor|pra mim|para mim|agora|ai|ali|la|ja|rapido|no mapa|no globo|na terra|please|now)\s*$")

# Quando estas palavras aparecem, nao e' lugar no mapa: fica com o cerebro e as outras redes.
_NAO_E_LUGAR = re.compile(
    r"\b(?:computador|google|youtube|site|pagina|pasta|arquivo|whatsapp|chrome|navegador|programa|aplicativo|app|jogo|"
    r"musica|video|filme|cozinha|banheiro|quarto|trabalho|escola|embora|dormir|casa|frente|tras|internet|tela|janela|"
    r"bloco de notas|calculadora|paint|configuracoes|email|isso|isto|aquilo|tudo|nada|aqui|voce|dele|dela|bem|mal)\b")

_DIRECOES = {
    "norte": "norte", "cima": "norte", "sul": "sul", "baixo": "sul",
    "leste": "leste", "direita": "leste", "oeste": "oeste", "esquerda": "oeste",
    "north": "norte", "up": "norte", "south": "sul", "down": "sul",
    "east": "leste", "right": "leste", "west": "oeste", "left": "oeste",
}
_RE_MOVER = re.compile(
    r"^(?:(?:vai|va|anda|ande|move|mova|mexe|mexa|olha|olhe|gira|gire|vira|vire|desloca|desloque|go|move)\s+)?"
    r"(?:(?:mais|um pouco|pouco)\s+)*(?:(?:para|pra|pro|to)\s+)?(?:(?:a|o|the)\s+)?"
    r"(norte|sul|leste|oeste|direita|esquerda|cima|baixo|north|south|east|west|left|right|up|down)$")

_RE_MAIS_PERTO = re.compile(
    r"^(?:(?:mais|um pouco)\s+)?(?:aproxima|aproxime|aproximar|chega mais perto|chegue mais perto|mais perto|perto|"
    r"zoom|zoom in|mais zoom|da zoom|amplia|ampliar|desce mais|desce|desca|closer)(?:\s+(?:mais|ai|um pouco|o mapa|a camera))*$")
_RE_MAIS_LONGE = re.compile(
    r"^(?:(?:mais|um pouco)\s+)?(?:afasta|afaste|afastar|mais longe|longe|menos zoom|zoom out|tira o zoom|sobe mais|sobe|suba|"
    r"further)(?:\s+(?:mais|ai|um pouco|o mapa|a camera))*$")

_RE_TERRA = re.compile(
    r"\b(?:terra inteira|planeta inteiro|mundo inteiro|globo inteiro|visao geral|vai pro espaco|vai para o espaco|"
    r"volta pro espaco|volta para o espaco|whole earth|whole world)\b")
_RE_VOLTAR = re.compile(
    r"^(?:volta|voltar|volte|retorna|retornar|sai|sair|saia|go back|back|exit)"
    r"(?:\s+(?:do|da|para|pro|pra|ao|o|a|from|to|the)){0,3}"
    rf"(?:\s+(?:{_ST}|streetview|rua|globo|mapa|google maps|maps|tras))?$")

_RE_MODO = re.compile(r"\b(?:modo\s+)?(satelite|holograma|mapa de ruas|hologram|satellite)\b")
_RE_MODO_MAPA = re.compile(r"^modo (?:mapa|map)$")
_RE_NOITE_LIGA = re.compile(r"^(?:liga|ligue|ativa|ative|mostra|mostre)\s+(?:a\s+|o\s+)?(?:noite|dia e noite|luz do dia)\b")
_RE_NOITE_DESLIGA = re.compile(r"^(?:desliga|desligue|tira|tire|desativa|desative)\s+(?:a\s+|o\s+)?(?:noite|dia e noite)\b")
_RE_GIRAR = re.compile(r"^(?:gira|gire|girar|roda|rode|rodar|spin)(?:\s+(?:a|o|the))?(?:\s+(?:terra|globo|planeta|earth|globe))?$")
_RE_PARAR_GIRO = re.compile(r"^(?:para|pare|parar|stop)\s+(?:de\s+)?(?:girar|rodar|spinning)\b")
_RE_INCLINAR = re.compile(r"^(?:inclina|incline|inclinar|deita|deite|tilt)\b")
_RE_ONDE = re.compile(r"^(?:onde (?:eu )?(?:estou|estamos|to|e aqui|e isso)|que (?:lugar|cidade|pais) e (?:esse|esta|essa|aqui)|where am i)\b")

_RE_MEDIR = re.compile(
    r"\b(?:distancia|quantos km|quantos quilometros|quanto da|mede|medir|meça|calcula|distance|how far)\b.*?"
    r"\b(?:de|do|da|from)\s+(.+?)\s+(?:ate|para|pra|pro|ao|a|to)\s+(.+)$")
_RE_MEDIR_ENTRE = re.compile(r"\b(?:distancia|distance)\b.*?\b(?:entre|between)\s+(.+?)\s+(?:e|and)\s+(.+)$")

_RE_CAPITAL = re.compile(r"^(?:a\s+|the\s+)?capital(?:\s+(?:do|da|de|dos|das|of))?(?:\s+(.+))?$")
_RE_PERGUNTA_CAPITAL = re.compile(r"^(?:qual|quais|what)\s+(?:e\s+|is\s+)?(?:a\s+|the\s+)?capital\s+(?:do|da|de|dos|das|of)\s+(.+)$")
_RE_ONDE_FICA = re.compile(r"^(?:onde fica|onde e|cade|where is)\s+(.+)$")
_RE_BAIRRO = re.compile(r"^(?:o\s+)?(?:bairro|neighborhood|neighbourhood|distrito)(?:\s+(?:do|da|de))?\s+(.+)$")
_RE_RUA = re.compile(r"^((?:rua|avenida|av|travessa|alameda|praca|estrada|rodovia|ladeira|street|avenue)\s+.+)$")
_RE_CIDADE = re.compile(r"^(?:a\s+)?(?:cidade|municipio|city|town)(?:\s+(?:do|da|de|of))?\s+(.+)$")
_RE_PAIS = re.compile(r"^(?:o\s+)?(?:pais|nacao|country)(?:\s+(?:do|da|de|of))?\s+(.+)$")
_RE_ESTADO = re.compile(r"^(?:o\s+)?(?:estado|provincia|regiao|state)(?:\s+(?:do|da|de|of))?\s+(.+)$")
_RE_EM = re.compile(r"\s+(?:em|no|na|de|do|da|in)\s+(?=\S)")


# O PASSEIO GUIADO: anda pelo Street View explicando o que aparece. Ver core/globo_passeio.py.
RE_PARAR_PASSEIO = re.compile(
    r"^(?:(?:ok|pode|ja|por favor|agora|nao)\s+)*(?:para|pare|parar|parou|chega|stop|espera|espere|aguarda|segura|"
    r"ja deu|deu|acabou|cancela|cancelar)\b")
_RE_PASSEIO = re.compile(
    r"\b(?:passeio|passeando|passear|passeia|passeie|tour|visita guiada|guia turistic\w+|"
    r"vai andando|sai andando|andando (?:por|pel\w+|na|no|em)|anda (?:por|pel\w+)|ande (?:por|pel\w+)|"
    r"vai caminhando|caminhando|caminha pel\w+|caminhe pel\w+|percorre|percorra|percorrer|percorrendo|"
    r"pontos? turistic\w+|vai (?:me )?(?:falando|explicando|mostrando|contando|apresentando)|"
    r"(?:mostra|mostre|mostrar|mostrando|explica|explique|explicar|explicando|fala|fale|falando|conta|conte|contando|"
    r"conhecer)(?: me)? (?:os |as |alguns |algumas |uns |umas )?(?:pontos?|lugares|locais|atrac\w+|coisas interessantes)\b|"
    r"(?:da|dar|de|dando) (?:uma|um) (?:volta|voltinha|role|rolezinho) (?:por|pel\w+|na|no|em) (?!globo\b|mapa\b)|"
    r"anda comigo|ande comigo|"
    r"me (?:fala|explica|conta|mostra|mostre) o que tem|o que tem (?:de interessante|aqui|por aqui|nessa|nesse)|"
    r"take a walk|walk (?:around|along|down|through)|guided tour|keep walking)\b")
# Disse para andar, ou falou no globo: nao ha duvida de que o que vem depois e' um lugar.
_RE_PASSEIO_FORTE = re.compile(
    rf"\b(?:passe\w+|tour|visita guiada|guia turistic\w+|anda|ande|andar|andando|caminh\w+|percorr\w+|turistic\w+|"
    rf"volta|voltinha|role|rolezinho|{_PALAVRA_GLOBO}|{_ST}|streetview|mapa|walk|walking)\b")
# Quem esta contando a propria vida nao esta dando ordem: "vou passear em Recife amanha".
_RE_PRIMEIRA_PESSOA = re.compile(r"^(?:eu\s+)?(?:vou|fui|to|tou|estou|estava|tava|ia|gosto|adoro|tenho)\b")
_VERBOS_ROTA = (r"entra|entre|entrar|vai|va|ir|abre|abra|abrir|leva|leve|levar|mostra|mostre|anda|ande|andar|andando|"
                r"caminha|caminhe|caminhar|caminhando|passeia|passeie|passear|passeando|passeio|percorre|percorra|"
                r"percorrer|percorrendo|comeca|comece|explica|explique|explicando|fala|fale|falando|conta|conte|"
                r"contando|tour|guiada|streetview|interessante|turisticos?|pontos?|lugares|locais|go|walk|take|"
                rf"globo|global|{_ERROS_DO_GLOBO}|mapa|volta|voltinha|role|rolezinho|comigo")
_FIM_DO_LUGAR = (r"(?=\s+(?:e|pelo globo|pela terra|no globo|no streetview|pelo streetview|na streetview|no mapa|me|andando|"
                 r"caminhando|passeando|explicando|falando|contando|mostrando|aqui|ja|agora|com|and|vai)\b|$)")
_RE_ROTA_LUGAR = re.compile(
    rf"\b(?:{_VERBOS_ROTA})\s+(?:(?:em|no|na|nos|nas|para|pra|pro|ate|ao|a|por|pela|pelo|pelas|pelos|de|do|da|"
    r"sobre|to|in|at|along|down|through)\s+)+(.+?)" + _FIM_DO_LUGAR)
# Quem diz o que e' o lugar nao precisa de verbo nem de preposicao: "a avenida paulista, vai mostrando".
_RE_LUGAR_COM_TIPO = re.compile(
    r"\b((?:avenida|av|rua|alameda|travessa|praca|estrada|rodovia|bairro|cidade d[eoa]|capital d[eoa]|estado d[eoa])\s+.+?)"
    + _FIM_DO_LUGAR)
_NAO_E_DESTINO = re.compile(
    rf"^(?:(?:o|a|os|as)\s+)?(?:globo|global|{_ERROS_DO_GLOBO}|streetview|mapa|maps|google maps|terra|ele|ela|eles|elas|isso|isto|esse|essa|"
    r"este|esta|aqui|la|ali|rua|lugar|lugares|local|locais|coisas?|pontos? turisticos?|mim|ti|voce|the street|it)$")
_FALA_A_TOA = re.compile(r"\b(?:ai|ne|tipo|cara|mano|irmao|chefe|chefia|parceiro|bicho|velho|etc|e etc)\b")
_POLIDEZ = re.compile(
    r"^(?:(?:nao|ok|okay|certo|beleza|blz|sim|entao|agora|bora|vamos|vamo|olha|escuta|oi|ei|o|hey|please)\s+)*"
    r"(?:(?:eu\s+)?(?:quero|queria|gostaria de|preciso|i want)\s+(?:que\s+)?(?:voce\s+|vc\s+|tu\s+|you\s+)?(?:to\s+)?)?"
    r"(?:(?:pode|por favor)\s+)?")


_RE_VERBO_DE_ANDAR = re.compile(r"^(?:anda|ande|andar|andando|caminha|caminhe|caminhar|caminhando|passeia|passeie|passear|"
                                r"passeando|passeio|percorre|percorra|percorrer|percorrendo|walk)\b")


def _parece_globo(s: str) -> bool:
    """O whisper escreve "globo" de muitos jeitos. Palavra solta quase igual nao e' destino."""
    s = s.strip()
    if " " in s or not 3 < len(s) < 10:
        return False
    import difflib  # noqa: PLC0415
    return difflib.SequenceMatcher(None, s, "globo").ratio() >= 0.72


def _enxugar(t: str) -> str:
    """Tira o que a fala do dia a dia poe no meio ("entra ai", "eu quero que voce...")."""
    # Erros de transcricao vistos no uso real: "mostar" por "mostrar".
    t = re.sub(r"\bmostar\b", "mostrar", t)
    t = re.sub(r"\bmostano\b", "mostrando", t)
    t = re.sub(r"\bpuntos?\b", "pontos", t)
    t = re.sub(r"\b(?:por favor|por gentileza|pra mim|para mim|atraves d[oa])\b", " ", t)
    t = _FALA_A_TOA.sub(" ", t)
    t = " ".join(t.split())
    t = re.sub(r"\b(vai(?: me)?) passando (?=por\b|pel\w+\b)", r"\1 passeando ", t)
    return _POLIDEZ.sub("", t, count=1).strip() or t


def _destino_do_passeio(t: str) -> dict | None:
    """O lugar pode estar em qualquer ponto da frase de quem pede o passeio."""
    limpa = _RE_ST.sub("streetview", t)
    candidatos = []
    for m in _RE_ROTA_LUGAR.finditer(limpa):
        bruto = m.group(1).strip()
        if _NAO_E_DESTINO.match(bruto) or _parece_globo(bruto):
            continue
        a = _alvo(bruto)
        if a and a.get("lugar") and not _NAO_E_DESTINO.match(a["lugar"]):
            # Quem diz o que e' ("avenida", "cidade de") e quem vem depois de andar
            # ("passeando pela...") valem mais do que a 1a coisa depois de "entra".
            nota = (3 if a.get("tipo") else 0) + (2 if _RE_VERBO_DE_ANDAR.match(m.group(0)) else 0)
            candidatos.append((nota, len(candidatos), a))
    if candidatos:
        return max(candidatos, key=lambda c: c[:2])[2]
    m = _RE_LUGAR_COM_TIPO.search(limpa)
    a = _alvo(m.group(1)) if m else None
    return a if a and a.get("lugar") else None


_RE_CONTINUAR = re.compile(r"^(?:(?:ok|pode|agora)\s+)*(?:continua|continue|continuar|segue|siga|anda|ande|andar|caminha|caminhe|vai andando|keep going|walk)(?:\s+(?:ai|mais|agora|por favor))*$")
_RE_LUGAR_E_RUA = re.compile(
    r"^(?:(?:a|o)\s+)?(?:cidade(?:\s+(?:de|do|da))?\s+)?(.+?)\s+(?:na|no|em)\s+((?:rua|avenida|av|travessa|alameda|praca|estrada|rodovia)\s+.+)$")


def _limpar_lugar(s: str) -> str:
    s = s.strip()
    anterior = None
    while s != anterior:
        anterior = s
        s = _FIM_INUTIL.sub("", s).strip()
        s = _RE_NO_GLOBO.sub("", s).strip()
    # Tira as preposicoes da frente, nunca a ultima palavra (o lugar pode ser "Na" mesmo).
    partes = s.split()
    while len(partes) > 1 and re.fullmatch(_PREP, partes[0]):
        partes.pop(0)
    return " ".join(partes)


# "champs elysees em paris", "cristo redentor no rio de janeiro": o que vem depois diz ONDE e'. Com a virgula, o globo
# recusa quem nao fica la' (ver `resolver` em busca.js).
_RE_LUGAR_EM_LUGAR = re.compile(r"^(.+)\s+(?:em|in|no|na)\s+(\S+(?:\s+\S+){0,4})$")


def _alvo(lugar_bruto: str) -> dict | None:
    """'capital do japao' -> {'lugar': 'japao', 'tipo': 'capital'}; 'bairro x em y' -> ..."""
    s = _limpar_lugar(lugar_bruto)
    if not s or len(s.split()) > 9 or _NAO_E_LUGAR.search(s):
        return None
    if re.fullmatch(_PREP, s):
        return None
    m = _RE_LUGAR_E_RUA.match(s)
    if m:
        # "sao paulo na avenida paulista": o endereco acha melhor com a rua primeiro.
        cidade = m.group(1).strip()
        if _NAO_E_DESTINO.match(cidade) or _parece_globo(cidade):     # "streetview na avenida paulista"
            return {"lugar": m.group(2).strip(), "tipo": "rua"}
        return {"lugar": f"{m.group(2).strip()}, {cidade}", "tipo": "rua"}
    m = _RE_CAPITAL.match(s)
    if m:
        return {"lugar": _limpar_lugar(m.group(1) or ""), "tipo": "capital"}
    m = _RE_BAIRRO.match(s)
    if m:
        # "bairro centro em patos" vira "centro, patos": assim o endereco acha mais facil.
        partes = _RE_EM.split(m.group(1), maxsplit=1)
        return {"lugar": ", ".join(p.strip() for p in partes if p.strip()), "tipo": "bairro"}
    m = _RE_RUA.match(s)
    if m:
        partes = re.split(r"\s+(?:em|in)\s+", m.group(1), maxsplit=1)
        return {"lugar": ", ".join(p.strip() for p in partes if p.strip()), "tipo": "rua"}
    m = _RE_CIDADE.match(s)
    if m:
        return {"lugar": _limpar_lugar(m.group(1)), "tipo": "cidade"}
    m = _RE_PAIS.match(s)
    if m:
        return {"lugar": _limpar_lugar(m.group(1)), "tipo": "pais"}
    m = _RE_ESTADO.match(s)
    if m:
        return {"lugar": _limpar_lugar(m.group(1)), "tipo": "estado"}
    m = _RE_LUGAR_EM_LUGAR.match(s)
    if m and not _NAO_E_DESTINO.match(m.group(2)):
        return {"lugar": f"{m.group(1).strip()}, {m.group(2).strip()}", "tipo": ""}
    return {"lugar": s, "tipo": ""}


def interpretar(t: str, aberto: bool) -> dict | None:
    """Devolve o pedido para o globo, ou None se a frase nao for para ele.

    `so_se_existir=True`: a frase e' ambigua ("mostra o Japao" e "mostra as fotos"):
    quem chama confere se o lugar existe antes de assumir. Se nao existir, ela segue
    para o cerebro como qualquer outra.
    """
    t = _enxugar(" ".join(str(t or "").split()))
    if not t or len(t.split()) > 26:
        return None

    if _RE_FECHAR.match(t):
        return {"acao": "fechar"} if aberto else None

    # "entra na Avenida Paulista e vai andando explicando", "faz um passeio em Paris",
    # "pode ir percorrendo". De globo fechado so' com lugar: sem ele e' conversa.
    if _RE_PASSEIO.search(t) and not _RE_PRIMEIRA_PESSOA.match(t):
        a = _destino_do_passeio(t)
        if a:
            # "me mostra os pontos do campeonato": sem dizer o que e' (rua, cidade) nem falar em
            # andar ou no globo, quem sabe se e' um lugar e' o globo; de janela fechada, o cerebro.
            if a.get("tipo") or _RE_PASSEIO_FORTE.search(t):
                return {"acao": "passeio", **a}
            return {"acao": "passeio", **a, "so_se_existir": True} if aberto else None
        return {"acao": "passeio"} if aberto else None

    m = _RE_ABRIR.match(t)
    if m:
        # "abre o globo ai e entra na cidade de Sao Paulo": a segunda metade vira o pedido.
        resto = re.sub(r"^(?:(?:ai|aqui|agora|pra mim|para mim)\s+)*(?:e\s+)?", "", (m.group(1) or "").strip())
        if resto:
            r = interpretar(resto, True)
            if r and r.get("acao") != "abrir":
                r.pop("so_se_existir", None)
                r.pop("so_grandes", None)
                return r
            a = _alvo(resto)
            if a:
                return {"acao": "ir", **a}
        return {"acao": "abrir"}

    # "mostra o Japao no globo", "vai pro Chile no mapa": vale mesmo de janela fechada.
    pediu_no_globo = bool(_RE_NO_GLOBO.search(t))
    if not aberto and not pediu_no_globo:
        return None

    if _RE_VOLTAR.match(t):
        return {"acao": "voltar"}
    if _RE_CONTINUAR.match(t):
        return {"acao": "passeio"}

    tem_st = bool(_RE_ST.search(t))
    if tem_st or _RE_ST_SOLTO.match(t):
        resto = _RE_ST.sub(" ", t) if tem_st else ""
        # O que sobrou da frase pode ser o lugar: "street view de paris", "vai pro japao e entra no street view".
        resto = re.sub(rf"^{_PREFIXO}(?:me\s+)?(?:(?:{_VERBOS_MOSTRAR}|{_VERBOS_FORTES}|abrir)\s+)?", "", resto.strip())
        resto = re.sub(r"\s+e\s+(?:(?:me\s+)?(?:" + _VERBOS_MOSTRAR + r"|" + _VERBOS_FORTES + r"))?\s*(?:no|na|o|a)?\s*$", "", resto)
        resto = re.sub(r"^(?:(?:no|na|o|a|do|da|de|em)\s+)+", "", resto.strip())
        resto = re.sub(r"\s+(?:no|na|o|a|do|da|de|em)$", "", resto).strip()
        a = _alvo(resto) if resto else None
        return {"acao": "street_view", **(a or {})}

    if _RE_MAPS.search(t) and aberto:
        resto = _RE_MAPS.sub(" ", t)
        resto = re.sub(rf"^{_PREFIXO}(?:me\s+)?(?:(?:{_VERBOS_MOSTRAR}|{_VERBOS_FORTES})\s+)?", "", resto.strip())
        resto = re.sub(r"^(?:(?:no|na|o|a|do|da|de|em)\s+)+", "", resto.strip()).strip()
        resto = re.sub(r"\s+(?:no|na|o|a|do|da|de|em)$", "", resto).strip()
        a = _alvo(resto) if resto else None
        return {"acao": "google_maps", **(a or {})}

    if _RE_TERRA.search(t):
        return {"acao": "terra"}
    if _RE_MAIS_PERTO.match(t):
        return {"acao": "zoom", "direcao": "aproximar"}
    if _RE_MAIS_LONGE.match(t):
        return {"acao": "zoom", "direcao": "afastar"}
    m = _RE_MOVER.match(t)
    if m:
        return {"acao": "mover", "direcao": _DIRECOES[m.group(1)]}
    if _RE_PARAR_GIRO.match(t):
        return {"acao": "girar", "ligado": False}
    if _RE_GIRAR.match(t):
        return {"acao": "girar", "ligado": True}
    if _RE_INCLINAR.match(t):
        return {"acao": "inclinar"}
    if _RE_ONDE.match(t):
        return {"acao": "estado"}
    if _RE_NOITE_LIGA.match(t):
        return {"acao": "noite", "ligado": True}
    if _RE_NOITE_DESLIGA.match(t):
        return {"acao": "noite", "ligado": False}
    if _RE_MODO_MAPA.match(t):
        return {"acao": "modo", "modo": "mapa"}
    m = _RE_MODO.search(t)
    if m and len(t.split()) <= 5:
        nome = {"hologram": "holograma", "satellite": "satelite", "mapa de ruas": "mapa"}.get(m.group(1), m.group(1))
        return {"acao": "modo", "modo": nome}

    m = _RE_MEDIR_ENTRE.search(t) or _RE_MEDIR.search(t)
    if m:
        a, b = _limpar_lugar(m.group(1)), _limpar_lugar(m.group(2))
        if a and b:
            return {"acao": "medir", "origem": a, "destino": b}

    m = _RE_PERGUNTA_CAPITAL.match(t)
    if m:
        return {"acao": "ir", "lugar": _limpar_lugar(m.group(1)), "tipo": "capital"}
    m = _RE_ONDE_FICA.match(t)
    if m:
        a = _alvo(m.group(1))
        return {"acao": "ir", **a} if a else None

    # "vai para o Japao", "me leva pra Paris", "vai na capital do Chile".
    m = _RE_FORTE.match(t)
    if m:
        resto = m.group(1)
        a = _alvo(resto)
        if a is None:
            return None
        # "vai dormir", "vai fazer": sem preposicao nao e' viagem, a nao ser que exista.
        tem_prep = bool(_RE_TEM_PREP.match(resto)) or a["tipo"] in ("capital", "bairro", "rua", "cidade", "pais", "estado")
        return {"acao": "ir", **a, **({} if tem_prep else {"so_se_existir": True})}

    # "mostra o Japao", "procura Paris": podem ser outra coisa ("mostra as fotos").
    m = _RE_MOSTRAR.match(t)
    if m:
        a = _alvo(m.group(1))
        if a is None:
            return None
        forte = a["tipo"] in ("capital", "bairro", "rua", "cidade", "pais", "estado")
        return {"acao": "ir", **a, **({} if forte else {"so_se_existir": True})}

    # So' o nome, no meio da conversa com o globo aberto: "Chile", "e o Canada", "agora Paris".
    s = re.sub(_PREFIXO, "", t)
    s = _limpar_lugar(s)
    if s and len(s.split()) <= 4 and not _NAO_E_LUGAR.search(s):
        a = _alvo(s)
        if a and a["lugar"]:
            forte = a["tipo"] in ("capital", "bairro", "rua", "cidade", "pais", "estado")
            return {"acao": "ir", **a, **({} if forte else {"so_se_existir": True, "so_grandes": True})}
    return None


_RE_FALA_DE_LUGAR = re.compile(
    rf"\b(?:{_PALAVRA_GLOBO[3:-1]}|{_ST}|streetview|google maps|mapa|avenida|rua|bairro|capital|cidade de|"
    r"passe\w+|percorr\w+|pontos?|turistic\w+|andando|caminhando|andar por|andar pela|andar pelo)\b")


def fala_de_lugar(t: str) -> bool:
    """A conversa direta nao tem ferramenta nenhuma: fala de lugar vai para o cerebro."""
    return bool(_RE_FALA_DE_LUGAR.search(str(t or "")))


def quer_passeio(t: str) -> bool:
    """A rede do cerebro: pediu passeio, mas o modelo escolheu so' ir ate o lugar?"""
    t = _enxugar(" ".join(str(t or "").split()))
    return bool(_RE_PASSEIO.search(t)) and not _RE_PRIMEIRA_PESSOA.match(t)


def normalizar(texto: str) -> str:
    """Minuscula, sem acento e sem pontuacao: o jeito que `interpretar` recebe a frase."""
    import unicodedata  # noqa: PLC0415
    t = unicodedata.normalize("NFD", str(texto or "").strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join("".join(c if c.isalnum() else " " for c in t).split())


def _quilometros(km: int, idioma: str) -> str:
    n = f"{km:,}".replace(",", " " if idioma == "en" else ".")
    return f"{n} kilometers" if idioma == "en" else f"{n} quilômetros"


def frase(pedido: dict, r: dict | None, idioma: str = "pt") -> str:
    """O que o JARVIS fala de volta. Curto: quem esta falando e' o globo andando."""
    en = idioma == "en"
    acao = pedido.get("acao")
    r = r or {}
    if acao == "abrir":
        return "Opening the globe." if en else "Abrindo o globo."
    if acao == "fechar":
        return "Globe closed." if en else "Globo fechado."
    if r.get("ok") is False:
        if pedido.get("lugar") or pedido.get("origem"):
            return "I couldn't find that place." if en else "Não encontrei esse lugar."
        return "I couldn't do that on the globe." if en else "Não consegui fazer isso no globo."
    if acao in ("zoom", "mover", "inclinar", "girar", "noite", "voltar", "passeio"):
        return ""       # em tempo real: o movimento ja e' a resposta
    if acao == "terra":
        return "The whole Earth." if en else "A Terra inteira."
    if acao == "modo":
        m = {"satelite": ("Satellite.", "Satélite."), "mapa": ("Street map.", "Mapa de ruas."),
             "holograma": ("Hologram.", "Holograma.")}.get(str(pedido.get("modo")), ("", ""))
        return m[0] if en else m[1]
    if acao == "medir":
        km = int(r.get("km") or 0)
        de, ate = r.get("origem", ""), r.get("destino", "")
        return (f"{de} to {ate}: {_quilometros(km, 'en')}." if en
                else f"De {de} até {ate} são {_quilometros(km, 'pt')}.")
    if acao == "estado":
        nome = r.get("escolhido") or ""
        if nome:
            return f"We are at {nome}." if en else f"Estamos em {nome}."
        return "Looking at the Earth from space." if en else "Olhando a Terra do espaço."
    nome = r.get("nome") or ""
    if acao == "street_view":
        return f"Street View of {nome}." if en and nome else ("Street View." if en else (f"Street View de {nome}." if nome else "Street View."))
    if acao == "google_maps":
        return "Google Maps."
    if not nome:
        return ""
    if r.get("capital_de"):
        return f"{nome}, the capital." if en else f"{nome}, a capital."
    if r.get("tipo") == "pais":
        cap = r.get("capital") or ""
        if cap:
            return f"{nome}. Capital, {cap}." if en else f"{nome}. Capital, {cap}."
        return f"{nome}."
    if r.get("tipo") == "continente":
        return f"{nome}."
    if r.get("tipo") == "cidade":
        onde = r.get("estado") or r.get("pais") or ""
        return f"{nome}, {onde}." if onde else f"{nome}."
    return f"{nome}."
