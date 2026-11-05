// Textos e numeros da tela. Tudo em dois idiomas porque o JARVIS tem cliente em
// ingles (config/idioma.json): o idioma vem de /api/config, o mesmo do programa.

const TEXTOS = {
  pt: {
    titulo: "GLOBO · EARTH VIEW",
    buscar: "Buscar país, cidade ou endereço…  (Ctrl+K)",
    semResultado: "Nada encontrado com esse nome",
    buscandoInternet: "Procurando na internet…",
    telaCheia: "Tela cheia  [F11]",
    fechar: "Fechar o globo",
    modoSatelite: "Satélite",
    modoMapa: "Mapa de ruas",
    modoHolograma: "Holograma",
    ferrRua: "Street View: clique no lugar",
    ferrMedir: "Medir distância",
    luzNoite: "Dia e noite em tempo real",
    luzNomes: "Nomes no mapa",
    luzBordas: "Fronteiras",
    luzRelevo: "Relevo 3D (montanhas)",
    luzGirar: "Girar a Terra",
    norte: "Voltar para o norte",
    inclinar: "Inclinar a visão",
    aproximar: "Aproximar",
    afastar: "Afastar",
    terraInteira: "Ver a Terra inteira",
    fontes: "De onde vêm os dados",
    terra: "Terra",
    voltarGlobo: "Voltar ao globo",
    abaStreet: "STREET VIEW",
    abaMaps: "GOOGLE MAPS",
    pararPasseio: "PARAR O PASSEIO",
    abrirNavegador: "Abrir no navegador",
    ruaDica: "Arraste para olhar em volta. Clique nas setas da rua para andar.",
    carregandoMotor: "Iniciando o motor gráfico",
    carregandoPaises: "Carregando países",
    carregandoCidades: "Carregando 70 mil cidades",
    carregandoTerra: "Montando a Terra",
    semWebgl: "Este computador não conseguiu ligar o gráfico 3D (WebGL).",
    semWebglDica: "Atualize o driver da placa de vídeo. Enquanto isso, você pode abrir o mapa pelo navegador.",
    abrirMapaNav: "Abrir o Google Maps",
    erroMotor: "O gráfico 3D parou de responder. Recarregando…",
    semInternet: "SEM INTERNET · imagem básica",
    capital: "Capital",
    populacao: "População",
    area: "Área",
    pib: "PIB",
    moeda: "Moeda",
    idiomas: "Idiomas",
    horaCapital: "Hora na capital",
    horaLocal: "Hora local",
    ddi: "DDI",
    dominio: "Internet",
    altitude: "Altitude",
    coordenadas: "Coordenadas",
    estado: "Estado",
    pais: "País",
    maioresCidades: "Maiores cidades",
    cidadesPerto: "Cidades por perto",
    vizinhos: "Fronteira com",
    paisesDaqui: "Países",
    verTerra: "ver no globo",
    acStreet: "Street View",
    acMaps: "Google Maps",
    acMedir: "Medir daqui",
    acCapital: "Ir à capital",
    acCopiar: "Copiar coordenadas",
    copiado: "Coordenadas copiadas",
    lerMais: "Ler mais na Wikipédia",
    localizando: "Localizando…",
    pertoDe: "Perto de",
    oceano: "Oceano",
    avisoRua: "Clique no lugar onde quer entrar no Street View",
    avisoRuaPerto: "Clique numa rua (as linhas azuis têm Street View)",
    avisoMedirA: "Clique no ponto de partida",
    avisoMedirB: "Agora clique no destino",
    avisoEsc: "ESC cancela",
    distancia: "Distância",
    voo: "de avião",
    a: "a",
    limpar: "Limpar",
    fontesTitulo: "De onde vêm os dados",
    fontesTexto: [
      ["Motor do globo", "CesiumJS (Apache 2.0)"],
      ["Terra de dia e de noite", "NASA Blue Marble e Black Marble"],
      ["Satélite, ruas e relevo", "Esri e parceiros"],
      ["Fronteiras", "Natural Earth"],
      ["Cidades", "GeoNames (CC BY 4.0)"],
      ["Endereços", "OpenStreetMap, Photon e Nominatim"],
      ["Textos e fotos", "Wikipédia (CC BY-SA)"],
      ["Street View e Google Maps", "Google"],
      ["Bandeiras", "flag-icons (MIT)"],
    ],
    mil: "mil", milhao: "milhão", milhoes: "milhões", bilhao: "bilhão", bilhoes: "bilhões", tri: "tri",
  },
  en: {
    titulo: "GLOBE · EARTH VIEW",
    buscar: "Search country, city or address…  (Ctrl+K)",
    semResultado: "Nothing found with that name",
    buscandoInternet: "Searching online…",
    telaCheia: "Full screen  [F11]",
    fechar: "Close the globe",
    modoSatelite: "Satellite",
    modoMapa: "Street map",
    modoHolograma: "Hologram",
    ferrRua: "Street View: click a place",
    ferrMedir: "Measure distance",
    luzNoite: "Real-time day and night",
    luzNomes: "Labels",
    luzBordas: "Borders",
    luzRelevo: "3D terrain (mountains)",
    luzGirar: "Spin the Earth",
    norte: "Back to north",
    inclinar: "Tilt the view",
    aproximar: "Zoom in",
    afastar: "Zoom out",
    terraInteira: "See the whole Earth",
    fontes: "Where the data comes from",
    terra: "Earth",
    voltarGlobo: "Back to the globe",
    abaStreet: "STREET VIEW",
    abaMaps: "GOOGLE MAPS",
    pararPasseio: "STOP THE WALK",
    abrirNavegador: "Open in browser",
    ruaDica: "Drag to look around. Click the arrows on the street to walk.",
    carregandoMotor: "Starting the graphics engine",
    carregandoPaises: "Loading countries",
    carregandoCidades: "Loading 70 thousand cities",
    carregandoTerra: "Building the Earth",
    semWebgl: "This computer could not start 3D graphics (WebGL).",
    semWebglDica: "Please update your graphics driver. Meanwhile, you can open the map in your browser.",
    abrirMapaNav: "Open Google Maps",
    erroMotor: "3D graphics stopped responding. Reloading…",
    semInternet: "OFFLINE · basic imagery",
    capital: "Capital",
    populacao: "Population",
    area: "Area",
    pib: "GDP",
    moeda: "Currency",
    idiomas: "Languages",
    horaCapital: "Time in the capital",
    horaLocal: "Local time",
    ddi: "Calling code",
    dominio: "Internet",
    altitude: "Elevation",
    coordenadas: "Coordinates",
    estado: "State",
    pais: "Country",
    maioresCidades: "Largest cities",
    cidadesPerto: "Nearby cities",
    vizinhos: "Borders",
    paisesDaqui: "Countries",
    verTerra: "see on the globe",
    acStreet: "Street View",
    acMaps: "Google Maps",
    acMedir: "Measure from here",
    acCapital: "Go to the capital",
    acCopiar: "Copy coordinates",
    copiado: "Coordinates copied",
    lerMais: "Read more on Wikipedia",
    localizando: "Locating…",
    pertoDe: "Near",
    oceano: "Ocean",
    avisoRua: "Click where you want to enter Street View",
    avisoRuaPerto: "Click a street (blue lines have Street View)",
    avisoMedirA: "Click the starting point",
    avisoMedirB: "Now click the destination",
    avisoEsc: "ESC cancels",
    distancia: "Distance",
    voo: "by plane",
    a: "to",
    limpar: "Clear",
    fontesTitulo: "Where the data comes from",
    fontesTexto: [
      ["Globe engine", "CesiumJS (Apache 2.0)"],
      ["Earth by day and night", "NASA Blue Marble and Black Marble"],
      ["Satellite, streets and terrain", "Esri and partners"],
      ["Borders", "Natural Earth"],
      ["Cities", "GeoNames (CC BY 4.0)"],
      ["Addresses", "OpenStreetMap, Photon and Nominatim"],
      ["Text and photos", "Wikipedia (CC BY-SA)"],
      ["Street View and Google Maps", "Google"],
      ["Flags", "flag-icons (MIT)"],
    ],
    mil: "K", milhao: "million", milhoes: "million", bilhao: "billion", bilhoes: "billion", tri: "tn",
  },
};

export let idioma = "pt";
export let locale = "pt-BR";

export function definirIdioma(i) {
  idioma = i === "en" ? "en" : "pt";
  locale = idioma === "en" ? "en-CA" : "pt-BR";
  document.documentElement.lang = locale;
  document.querySelectorAll("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
  document.querySelectorAll("[data-dica-t]").forEach((el) => { el.dataset.dica = t(el.dataset.dicaT); });
}

export function t(chave) {
  const v = TEXTOS[idioma][chave];
  return v === undefined ? chave : v;
}

// ── numeros ──────────────────────────────────────────────────────────────
export function numero(n, casas = 0) {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: casas }).format(n);
}

/** 92575 -> "92,6 mil"; 211049527 -> "211 milhões". */
export function grande(n) {
  if (!n) return "—";
  if (n >= 1e9) return `${numero(n / 1e9, 2)} ${n < 2e9 ? t("bilhao") : t("bilhoes")}`;
  if (n >= 1e6) return `${numero(n / 1e6, n >= 1e8 ? 0 : 1)} ${n < 2e6 ? t("milhao") : t("milhoes")}`;
  if (n >= 1e3) return idioma === "en" ? `${numero(n / 1e3, 1)}K` : `${numero(n / 1e3, n >= 1e5 ? 0 : 1)} ${t("mil")}`;
  return numero(n);
}

export function areaKm2(n) {
  if (!n) return "—";
  if (n >= 1e6) return `${numero(n / 1e6, 2)} ${t("milhoes")} km²`;
  return `${numero(n)} km²`;
}

export function dinheiroMd(mi) {
  if (!mi) return "—";
  if (mi >= 1e6) return `US$ ${numero(mi / 1e6, 2)} ${t("tri")}`;
  if (mi >= 1e3) return `US$ ${numero(mi / 1e3, 1)} ${idioma === "en" ? "bn" : "bi"}`;
  return `US$ ${numero(mi)} ${idioma === "en" ? "mn" : "mi"}`;
}

export function km(metros) {
  const k = metros / 1000;
  if (k >= 100) return `${numero(k)} km`;
  if (k >= 1) return `${numero(k, 1)} km`;
  return `${numero(metros)} m`;
}

export function coord(lat, lon, casas = 4) {
  const f = (v, pos, neg) => `${numero(Math.abs(v), casas)}° ${v >= 0 ? pos : neg}`;
  return `${f(lat, "N", "S")}, ${f(lon, idioma === "en" ? "E" : "L", idioma === "en" ? "W" : "O")}`;
}

// ── nomes que o proprio navegador sabe em qualquer idioma ────────────────
const _nomePais = {};
const _APARAR = { HK: { pt: "Hong Kong", en: "Hong Kong" }, MO: { pt: "Macau", en: "Macao" } };

export function nomeDoPais(iso, reserva) {
  if (!iso) return reserva;
  if (_APARAR[iso]) return _APARAR[iso][idioma];
  if (_nomePais[iso]) return _nomePais[iso];
  let nome = reserva;
  try {
    nome = new Intl.DisplayNames([locale], { type: "region" }).of(iso) || reserva;
  } catch { /* fica o da Natural Earth */ }
  _nomePais[iso] = nome;
  return nome;
}

export function nomeDaMoeda(cod, reserva) {
  if (!cod) return reserva || "—";
  try {
    const n = new Intl.DisplayNames([locale], { type: "currency" }).of(cod);
    return n ? `${n[0].toUpperCase()}${n.slice(1)} (${cod})` : reserva;
  } catch { return reserva || cod; }
}

export function nomesDeIdiomas(lista) {
  if (!lista) return "—";
  const vistos = [];
  const fmt = new Intl.DisplayNames([locale], { type: "language" });
  for (const cod of lista.split(",")) {
    const base = cod.trim().split("-")[0];
    if (!base) continue;
    let nome = base;
    try { nome = fmt.of(base) || base; } catch { /* codigo estranho */ }
    if (nome.length <= 3) continue;          // lingua sem nome conhecido: nao mostra o codigo
    if (!vistos.includes(nome)) vistos.push(nome);
    if (vistos.length >= 3) break;
  }
  return vistos.join(", ") || "—";
}

/** "18:44" e "UTC−3" de um fuso IANA, sempre com o horario de verao certo. */
export function horaNoFuso(fuso) {
  if (!fuso) return null;
  try {
    const agora = new Date();
    const hora = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", timeZone: fuso }).format(agora);
    const off = new Intl.DateTimeFormat("en-US", { timeZone: fuso, timeZoneName: "shortOffset" })
      .formatToParts(agora).find((p) => p.type === "timeZoneName")?.value || "GMT";
    return { hora, utc: off.replace("GMT", "UTC").replace("-", "−") };
  } catch { return null; }
}

export function semAcento(s) {
  return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function escapar(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
