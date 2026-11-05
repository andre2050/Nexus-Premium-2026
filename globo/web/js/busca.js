// Busca: paises e 70 mil cidades na hora (sem internet); endereco e ponto turistico
// pela internet. A mesma funcao atende quem digita e quem fala com o JARVIS.

import { D, nomeCidade, nomeEstado, paisDaCidade } from "./dados.js";
import { cena } from "./cena.js";
import { escapar, grande, idioma, semAcento, t } from "./textos.js";

const C = window.Cesium;
const PHOTON = "https://photon.komoot.io/api/";

let _chaves = false;
let aoEscolher = null;

function prepararChaves() {
  if (_chaves) return;
  for (const c of D.cidades) c.k = semAcento(c.pt ? `${c.pt} ${c.n}` : c.n);
  _chaves = true;
}

function pontuar(chave, q) {
  if (chave === q) return 5;
  if (chave.startsWith(q)) return 4;
  const pos = chave.indexOf(q);
  if (pos < 0) return 0;
  if (chave[pos - 1] === " ") return 3;
  return q.length >= 4 ? 1 : 0;
}

/** O melhor primeiro. `q` pode trazer o estado ou o pais: "patos paraiba". */
export function buscarLocal(texto, limite = 8) {
  prepararChaves();
  const q = semAcento(texto).replace(/[,;]+/g, " ").replace(/\s+/g, " ").trim();
  if (q.length < 2) return [];
  const palavras = q.split(" ");
  const achados = [];

  for (const p of D.paises) {
    let nota = pontuar(semAcento(p.nome), q);
    if (!nota) nota = Math.min(3, pontuar(p.chave, q));
    if (p.iso.toLowerCase() === q || p.iso3.toLowerCase() === q) nota = 5;
    if (nota) achados.push({ tipo: "pais", obj: p, nota: nota * 1000 + 600 + Math.log10(p.pop + 1) * 10 });
  }

  const contexto = (c) => semAcento(`${nomeEstado(c)} ${paisDaCidade(c)?.nome || ""} ${paisDaCidade(c)?.en || ""}`);
  let vistos = 0;
  for (const c of D.cidades) {
    let nota = pontuar(c.k, q);
    if (!nota && c.ap) nota = Math.min(3, pontuar(c.ap, q));
    if (!nota && palavras.length > 1) {
      // "patos paraiba": a primeira parte e' o nome, o resto tem de bater com o lugar.
      for (let corte = palavras.length - 1; corte >= 1 && !nota; corte--) {
        const nome = palavras.slice(0, corte).join(" ");
        const n = pontuar(c.k, nome);
        if (n >= 3) {
          const ctx = contexto(c);
          if (palavras.slice(corte).every((w) => ctx.includes(w))) nota = n === 5 ? 4.5 : n;
        }
      }
    }
    if (!nota) continue;
    // Com nomes iguais ganha a maior, com folga para a capital do pais e, para quem
    // fala portugues, para a cidade do Brasil. Sede de provincia quase nao conta:
    // "Granada" e' a da Espanha, nao a da Nicaragua.
    let bonus = c.cap === 2 ? 180 : (c.cap === 1 ? 10 : 0);
    if (c.cc === (idioma === "en" ? "CA" : "BR")) bonus += 45;
    achados.push({ tipo: "cidade", obj: c, nota: nota * 1000 + Math.log10(c.pop + 1) * 70 + bonus });
    if (++vistos > 500) break;
  }
  achados.sort((a, b) => b.nota - a.nota);
  return achados.slice(0, limite);
}

/** Endereco, ponto turistico, bairro: o que nao esta na lista de cidades. */
export async function buscarInternet(texto, limite = 6, sinal, extra = "") {
  const centro = cena.camera.positionCartographic;
  // Olhando para uma cidade, o que esta em volta conta: "vai no bairro Centro" olhando
  // para Patos acha o Centro de Patos. De longe nao: a Torre Eiffel ia parar no Mexico.
  const vies = centro.height < 3.0e5
    ? `&lat=${C.Math.toDegrees(centro.latitude).toFixed(3)}&lon=${C.Math.toDegrees(centro.longitude).toFixed(3)}&zoom=13&location_bias_scale=0.2`
    : "";
  const url = `${PHOTON}?q=${encodeURIComponent(texto)}&limit=${limite}${extra}${vies}`;
  const r = await fetch(url, { signal: sinal });
  if (!r.ok) throw new Error(`photon ${r.status}`);
  const dados = await r.json();
  return (dados.features || []).map((f) => {
    const a = f.properties || {};
    const [lon, lat] = f.geometry.coordinates;
    const rua = a.street ? `${a.street}${a.housenumber ? `, ${a.housenumber}` : ""}` : "";
    const nome = a.name || rua || a.city || a.county || a.state || a.country || "";
    const partes = [a.name && rua ? rua : "", a.district || a.locality, a.city, a.state, a.country].filter(Boolean);
    return { tipo: "ponto", obj: { lat, lon, nome, endereco: [...new Set(partes)].join(", "), cc: String(a.countrycode || "").toUpperCase(), extent: a.extent || null } };
  }).filter((x) => x.obj.nome);
}

/** O endereco que o Photon nao achou ainda pode estar no Nominatim. */
async function buscarNominatim(texto) {
  const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&addressdetails=1&q=${encodeURIComponent(texto)}&accept-language=${idioma === "en" ? "en" : "pt-BR"}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`nominatim ${r.status}`);
  const j = await r.json();
  if (!j[0]) return null;
  const a = j[0].address || {};
  const b = (j[0].boundingbox || []).map(Number);
  return {
    tipo: "ponto",
    obj: {
      lat: Number(j[0].lat), lon: Number(j[0].lon),
      nome: j[0].name || String(j[0].display_name || "").split(",")[0],
      endereco: [a.suburb, a.city || a.town || a.village, a.state, a.country].filter(Boolean).join(", "),
      cc: String(a.country_code || "").toUpperCase(),
      extent: b.length === 4 ? [b[2], b[1], b[3], b[0]] : null,
    },
  };
}

const _TAGS_BAIRRO = "&osm_tag=place:suburb&osm_tag=place:neighbourhood&osm_tag=place:quarter&osm_tag=place:city_district";

/**
 * Para voz e comando: a melhor resposta para um nome. `tipo` vem da frase ("cidade de
 * Patos", "bairro Centro", "rua X") e diz onde procurar primeiro.
 */
export async function resolver(texto, tipo = "") {
  const so = (t) => buscarLocal(texto, 12).find((r) => r.tipo === t) || null;
  if (tipo === "pais") {
    const p = so("pais");
    if (p) return p;
  }
  if (tipo === "cidade") {
    const c = so("cidade");
    if (c) return c;
  }
  const pertoDoChao = cena.camera.positionCartographic.height < 3.0e5;
  // O servico de endereco sempre devolve ALGUMA coisa: palavra mal ouvida ia parar num
  // vilarejo da Turquia ("golbulo" -> Gobul). Sem as palavras do pedido, nao e' o lugar.
  const palavras = semAcento(texto).replace(/[^a-z0-9 ]+/g, " ").split(" ")
    .filter((w) => w.length >= 3 && !["rua", "avenida", "bairro", "cidade", "estado", "praca", "the"].includes(w));
  // "Champs-Elysees, Paris": o que vem depois da virgula diz ONDE e'. Sem isto, um povoado da
  // Belgica com o mesmo nome passava na conta de metade das palavras.
  const fica = texto.includes(",") ? semAcento(texto.slice(texto.lastIndexOf(",") + 1)) : "";
  const deOnde = fica.replace(/[^a-z0-9 ]+/g, " ").split(" ").filter((w) => w.length >= 3);
  const confere = (r) => {
    if (!r || r.tipo !== "ponto" || !palavras.length) return !!r;
    const onde = semAcento(`${r.obj.nome} ${r.obj.endereco || ""}`);
    if (deOnde.length && !deOnde.some((w) => onde.includes(w))) return false;
    const batem = palavras.filter((w) => onde.includes(w)).length;
    return batem >= Math.ceil(palavras.length / 2);
  };
  // Cada servico responde bem uma coisa: o Nominatim acerta ponto turistico e endereco
  // inteiro; o Photon, com a camera ajudando, acha o bairro e a rua de onde se esta.
  const naInternet = async () => {
    const fila = pertoDoChao || tipo === "bairro"
      ? [() => (tipo === "bairro" ? buscarInternet(texto, 1, undefined, _TAGS_BAIRRO) : buscarInternet(texto, 1)),
        () => buscarNominatim(texto), () => buscarInternet(texto, 1)]
      : [() => buscarNominatim(texto), () => buscarInternet(texto, 1)];
    for (const passo of fila) {
      try {
        const r = await passo();
        const achado = Array.isArray(r) ? r[0] : r;
        if (achado && confere(achado)) return achado;
      } catch { /* este nao respondeu: tenta o proximo */ }
    }
    return null;
  };
  if (tipo === "bairro" || tipo === "rua" || tipo === "estado") {
    return (await naInternet()) || buscarLocal(texto, 1)[0] || null;
  }
  const locais = buscarLocal(texto, 1);
  if (locais[0] && locais[0].nota >= 3000) return locais[0];
  return (await naInternet()) || locais[0] || null;
}

/** A frase ambigua ("mostra o Japao", "Chile") so' vira comando se for um lugar mesmo. */
export function existeLugar(texto, soGrandes = false) {
  const r = buscarLocal(texto, 1)[0];
  if (!r) return false;
  const q = semAcento(texto).trim();
  if (r.tipo === "pais") return r.nota >= 4000 || r.obj.chave.split(" ").includes(q);
  // So' o nome solto no meio da conversa: cidade tem de ser conhecida, senao "bonito!" voa.
  if (soGrandes) return r.nota >= 5000 && (r.obj.pop >= 300000 || r.obj.cap === 2);
  return r.nota >= 4000;
}

// ── a caixa de busca ─────────────────────────────────────────────────────
const campo = () => document.getElementById("busca-campo");
const lista = () => document.getElementById("busca-lista");
let resultados = [];
let marcado = -1;
let timer = null;
let controle = null;
let ultimaBusca = "";

function linha(r, i) {
  const ativo = i === marcado ? " marcado" : "";
  if (r.tipo === "pais") {
    const p = r.obj;
    return `<button class="r${ativo}" data-i="${i}">${bandeira(p.iso)}<span class="r-txt"><b>${escapar(p.nome)}</b><small>${escapar(idioma === "en" ? p.cont : p.contPt)}</small></span></button>`;
  }
  if (r.tipo === "cidade") {
    const c = r.obj;
    const pais = paisDaCidade(c);
    const lugar = [nomeEstado(c), pais?.nome].filter(Boolean).join(", ");
    return `<button class="r${ativo}" data-i="${i}">${bandeira(c.cc)}<span class="r-txt"><b>${escapar(nomeCidade(c, idioma))}</b><small>${escapar(lugar)}</small></span><span class="r-num">${grande(c.pop)}</span></button>`;
  }
  const o = r.obj;
  return `<button class="r r-net${ativo}" data-i="${i}"><svg class="ic r-pino"><use href="#i-alvo"/></svg><span class="r-txt"><b>${escapar(o.nome)}</b><small>${escapar(o.endereco)}</small></span></button>`;
}

export function bandeira(iso) {
  if (!iso) return '<span class="r-band vazia"></span>';
  return `<img class="r-band" alt="" loading="lazy" src="img/bandeiras/${iso.toLowerCase()}.svg" onerror="this.style.visibility='hidden'">`;
}

function desenhar(estado = "") {
  const el = lista();
  if (!resultados.length && !estado) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  el.innerHTML = resultados.map(linha).join("") + (estado ? `<div class="r-estado">${escapar(estado)}</div>` : "");
}

function escolher(i, porEnter = false) {
  const r = resultados[i];
  if (!r) return;
  fecharLista();
  campo().blur();
  // Enter sem lugar conhecido na lista: o texto inteiro vai ao endereco completo, que
  // acerta o ponto turistico famoso (o clique numa linha fica com aquela linha).
  if (porEnter && r.tipo === "ponto") {
    buscarNominatim(campo().value).then((n) => aoEscolher?.(n || r)).catch(() => aoEscolher?.(r));
    return;
  }
  aoEscolher?.(r);
}

export function fecharLista() {
  lista().hidden = true;
  marcado = -1;
}

function aoDigitar() {
  const texto = campo().value;
  document.getElementById("busca-limpar").hidden = !texto;
  clearTimeout(timer);
  controle?.abort();
  ultimaBusca = texto;
  if (texto.trim().length < 2) {
    resultados = [];
    marcado = -1;
    desenhar();
    return;
  }
  resultados = buscarLocal(texto);
  marcado = resultados.length ? 0 : -1;
  const procurarFora = texto.trim().length >= 3;
  desenhar(procurarFora ? t("buscandoInternet") : (resultados.length ? "" : t("semResultado")));
  if (!procurarFora) return;
  timer = setTimeout(async () => {
    controle = new AbortController();
    try {
      const net = await buscarInternet(texto, 5, controle.signal);
      if (ultimaBusca !== texto) return;
      // Nao repete o que a lista de cidades ja mostrou.
      const novos = net.filter((n) => !resultados.some((r) => r.tipo !== "ponto"
        && semAcento(r.tipo === "cidade" ? nomeCidade(r.obj, idioma) : r.obj.nome) === semAcento(n.obj.nome)));
      resultados = [...resultados, ...novos].slice(0, 12);
      if (marcado < 0 && resultados.length) marcado = 0;
      desenhar(resultados.length ? "" : t("semResultado"));
    } catch (e) {
      if (e.name !== "AbortError" && ultimaBusca === texto) desenhar(resultados.length ? "" : t("semResultado"));
    }
  }, 320);
}

export function focar() {
  campo().focus();
  campo().select();
}

export function preparar(callback) {
  aoEscolher = callback;
  const c = campo();
  c.placeholder = t("buscar");
  c.addEventListener("input", aoDigitar);
  c.addEventListener("focus", () => {
    prepararChaves();
    if (resultados.length) desenhar();
  });
  c.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!resultados.length) return;
      marcado = (marcado + (e.key === "ArrowDown" ? 1 : -1) + resultados.length) % resultados.length;
      desenhar();
      lista().querySelector(".marcado")?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      escolher(marcado >= 0 ? marcado : 0, true);
    } else if (e.key === "Escape") {
      e.stopPropagation();
      if (!lista().hidden) fecharLista();
      else c.blur();
    }
  });
  lista().addEventListener("mousedown", (e) => {
    const b = e.target.closest("[data-i]");
    if (b) {
      e.preventDefault();
      escolher(Number(b.dataset.i));
    }
  });
  document.getElementById("busca-limpar").addEventListener("click", () => {
    c.value = "";
    aoDigitar();
    c.focus();
  });
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest("#busca")) fecharLista();
  });
}
