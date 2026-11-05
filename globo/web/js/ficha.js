// O painel da direita: o que se sabe sobre o lugar escolhido.

import { D, cidadesDoPais, cidadesPerto, fusoDaCidade, nomeCidade, nomeEstado, paisDaCidade } from "./dados.js";
import { bandeira } from "./busca.js";
import {
  areaKm2, coord, dinheiroMd, escapar, grande, horaNoFuso, idioma, nomeDaMoeda, nomesDeIdiomas, numero, t,
} from "./textos.js";

const el = () => document.getElementById("ficha");

let geracao = 0;      // resposta atrasada da internet nao pode cair na ficha de outro lugar
const _wiki = new Map();

function cabecalho(iso, titulo, sub) {
  return `<header class="f-cab">
      ${iso ? `<img class="f-band" alt="" src="img/bandeiras/${iso.toLowerCase()}.svg" onerror="this.style.display='none'">` : '<span class="f-band f-band-vazia"><svg class="ic"><use href="#i-alvo"/></svg></span>'}
      <div class="f-tit"><h2>${escapar(titulo)}</h2><small>${sub}</small></div>
      <button class="btn-ic f-x" data-acao="fechar"><svg class="ic"><use href="#i-fechar"/></svg></button>
    </header>`;
}

const dado = (rotulo, valor, largo = false) =>
  `<div class="f-dado${largo ? " largo" : ""}"><label>${escapar(rotulo)}</label><b>${valor}</b></div>`;

const botao = (acao, icone, texto, principal = false) =>
  `<button class="f-bt${principal ? " principal" : ""}" data-acao="${acao}"><svg class="ic${icone === "i-pessoa" ? " cheio" : ""}"><use href="#${icone}"/></svg><span>${escapar(texto)}</span></button>`;

function textoHora(fuso) {
  const h = horaNoFuso(fuso);
  return h ? `${h.hora} <small>${h.utc}</small>` : "—";
}

function listaCidades(cidades) {
  return `<ul class="f-lista">${cidades.map((c) => {
    return `<li><button data-cid="${c.i}"><span>${escapar(nomeCidade(c, idioma))}</span>${c.cap === 2 ? '<i class="f-cap">★</i>' : ""}<small>${grande(c.pop)}</small></button></li>`;
  }).join("")}</ul>`;
}

const BLOCO_WIKI = '<div class="f-wiki carregando" id="f-wiki"><i></i><i></i><i></i></div>';

function abrir(html) {
  const f = el();
  const nova = f.hidden;
  f.innerHTML = html;
  f.scrollTop = 0;
  f.hidden = false;
  document.body.classList.add("com-ficha");
  if (nova) {
    f.classList.remove("entrou");
    requestAnimationFrame(() => f.classList.add("entrou"));
  }
  return ++geracao;
}

export function esconder() {
  geracao++;
  const f = el();
  f.classList.remove("entrou");
  f.hidden = true;
  f.innerHTML = "";
  document.body.classList.remove("com-ficha");
}

// ── Wikipedia ────────────────────────────────────────────────────────────
async function apiWiki(params, sinal) {
  const base = `https://${idioma === "en" ? "en" : "pt"}.wikipedia.org/w/api.php`;
  const url = `${base}?action=query&format=json&origin=*&redirects=1&prop=extracts%7Cpageimages&exintro=1&explaintext=1&exsentences=3&exlimit=20&piprop=thumbnail&pithumbsize=720&${params}`;
  const r = await fetch(url, { signal: sinal });
  if (!r.ok) throw new Error(`wiki ${r.status}`);
  const j = await r.json();
  return Object.values(j?.query?.pages || {});
}

const chaveNome = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

async function wikiDoPais(nome) {
  const paginas = await apiWiki(`titles=${encodeURIComponent(nome)}`);
  return paginas.find((p) => p.extract) || null;
}

/** Cidade: procura pelas paginas perto do ponto, porque "Patos" sozinho e' um bicho. */
async function wikiDoLugar(nome, lat, lon) {
  const alvo = chaveNome(nome);
  const perto = await apiWiki(`generator=geosearch&ggscoord=${lat.toFixed(4)}%7C${lon.toFixed(4)}&ggsradius=10000&ggslimit=15`);
  const exato = perto.find((p) => chaveNome(p.title) === alvo)
    || perto.find((p) => chaveNome(p.title).startsWith(`${alvo} (`) || chaveNome(p.title).startsWith(`${alvo},`));
  return exato && exato.extract ? exato : null;
}

function pintarWiki(pagina, minha) {
  if (minha !== geracao) return;
  const b = document.getElementById("f-wiki");
  if (!b) return;
  if (!pagina) {
    b.remove();
    return;
  }
  const url = `https://${idioma === "en" ? "en" : "pt"}.wikipedia.org/wiki/${encodeURIComponent(pagina.title.replace(/ /g, "_"))}`;
  // Foto de pais costuma ser a propria bandeira, que ja esta no alto da ficha.
  const foto = /flag|bandeira/i.test(pagina.thumbnail?.source || "") ? "" : pagina.thumbnail?.source;
  const texto = pagina.extract.replace(/\s*\[[^\]]*\]/g, "").replace(/\s*\(\s*\)/g, "").replace(/\(\s*;\s*/g, "(");
  b.classList.remove("carregando");
  b.innerHTML = `${foto ? `<img class="f-foto" alt="" src="${escapar(foto)}" onerror="this.remove()">` : ""}
    <p>${escapar(texto)}</p>
    <button class="f-link" data-acao="wiki" data-url="${escapar(url)}">${escapar(t("lerMais"))} <svg class="ic"><use href="#i-fora"/></svg></button>`;
}

async function carregarWiki(chave, buscar, minha) {
  if (_wiki.has(chave)) {
    pintarWiki(_wiki.get(chave), minha);
    return;
  }
  try {
    const pagina = await buscar();
    _wiki.set(chave, pagina);
    pintarWiki(pagina, minha);
  } catch {
    pintarWiki(null, minha);     // sem internet: a ficha fica so' com os dados locais
  }
}

// ── as fichas ────────────────────────────────────────────────────────────
export function mostrarPais(p) {
  const capital = p.capI != null ? D.cidades[p.capI] : null;
  const nomeCap = capital ? nomeCidade(capital, idioma) : (p.cap || "—");
  const cidades = p.iso ? cidadesDoPais(p.iso, 12) : [];
  const vizinhos = (p.vizinhos || "").split(",").map((v) => D.porIso[v]).filter(Boolean);
  const html = `${cabecalho(p.iso, p.nome, escapar(idioma === "en" ? p.cont : p.contPt))}
    <div class="f-grade">
      ${dado(t("capital"), capital ? `<a data-cid="${capital.i}">${escapar(nomeCap)}</a>` : escapar(nomeCap))}
      ${dado(t("populacao"), grande(p.pop))}
      ${dado(t("area"), areaKm2(p.area))}
      ${dado(t("pib"), dinheiroMd(p.pib))}
      ${dado(t("moeda"), escapar(nomeDaMoeda(p.moeda, p.moedaNome)), true)}
      ${dado(t("idiomas"), escapar(nomesDeIdiomas(p.idiomas)), true)}
      ${capital ? `<div class="f-dado"><label>${escapar(t("horaCapital"))}</label><b data-fuso="${escapar(fusoDaCidade(capital))}">${textoHora(fusoDaCidade(capital))}</b></div>` : ""}
      ${p.ddi ? dado(t("ddi"), `+${escapar(p.ddi.replace(/^\+/, ""))}`) : ""}
    </div>
    <div class="f-acoes">
      ${capital ? botao("capital", "i-alvo", t("acCapital"), true) : ""}
      ${botao("maps", "i-mapa", t("acMaps"))}
      ${botao("medir", "i-regua", t("acMedir"))}
    </div>
    ${BLOCO_WIKI}
    ${cidades.length ? `<h3>${escapar(t("maioresCidades"))}</h3>${listaCidades(cidades)}` : ""}
    ${vizinhos.length ? `<h3>${escapar(t("vizinhos"))}</h3><div class="f-chips">${vizinhos.map((v) => `<button data-iso="${v.iso}">${bandeira(v.iso)}<span>${escapar(v.nome)}</span></button>`).join("")}</div>` : ""}`;
  const minha = abrir(html);
  carregarWiki(`p:${p.iso || p.en}`, () => wikiDoPais(p.nome), minha);
}

export function mostrarCidade(c) {
  const pais = paisDaCidade(c);
  const nome = nomeCidade(c, idioma);
  const estado = nomeEstado(c);
  const sub = [estado, pais?.nome ? `<a data-iso="${pais.iso}">${escapar(pais.nome)}</a>` : ""].filter(Boolean).join(", ");
  const perto = cidadesPerto(c.lat, c.lon, 150, 8, c);
  const html = `${cabecalho(c.cc, nome, sub)}
    <div class="f-grade">
      ${dado(t("populacao"), grande(c.pop))}
      <div class="f-dado"><label>${escapar(t("horaLocal"))}</label><b data-fuso="${escapar(fusoDaCidade(c))}">${textoHora(fusoDaCidade(c))}</b></div>
      ${c.alt ? dado(t("altitude"), `${numero(c.alt)} m`) : ""}
      ${dado(t("coordenadas"), `<a data-acao="copiar">${escapar(coord(c.lat, c.lon, 3))}</a>`, !c.alt)}
    </div>
    <div class="f-acoes">
      ${botao("street", "i-pessoa", t("acStreet"), true)}
      ${botao("maps", "i-mapa", t("acMaps"))}
      ${botao("medir", "i-regua", t("acMedir"))}
    </div>
    ${BLOCO_WIKI}
    ${perto.length ? `<h3>${escapar(t("cidadesPerto"))}</h3>${listaCidades(perto.map((x) => x.c))}` : ""}`;
  const minha = abrir(html);
  carregarWiki(`c:${c.i}`, () => wikiDoLugar(c.pt || c.n, c.lat, c.lon), minha);
}

/** Um ponto qualquer do mapa. O endereco chega depois, pela internet. */
export function mostrarPonto(o) {
  const minha = abrir(`${cabecalho(o.cc || "", o.nome || t("localizando"), `<span id="f-endereco">${escapar(o.endereco || "")}</span>`)}
    <div class="f-grade">
      ${dado(t("coordenadas"), `<a data-acao="copiar">${escapar(coord(o.lat, o.lon, 5))}</a>`, true)}
      ${o.fuso ? `<div class="f-dado"><label>${escapar(t("horaLocal"))}</label><b data-fuso="${escapar(o.fuso)}">${textoHora(o.fuso)}</b></div>` : ""}
      ${o.perto ? dado(t("pertoDe"), `<a data-cid="${o.perto.c.i}">${escapar(nomeCidade(o.perto.c, idioma))}</a> <small>${numero(o.perto.d, o.perto.d < 10 ? 1 : 0)} km</small>`) : ""}
    </div>
    <div class="f-acoes">
      ${botao("street", "i-pessoa", t("acStreet"), true)}
      ${botao("maps", "i-mapa", t("acMaps"))}
      ${botao("medir", "i-regua", t("acMedir"))}
    </div>`);
  return minha;
}

export function atualizarPonto(minha, nome, endereco, cc) {
  if (minha !== geracao) return;
  const f = el();
  const h = f.querySelector(".f-tit h2");
  const e = f.querySelector("#f-endereco");
  if (h) h.textContent = nome;
  if (e) e.textContent = endereco || "";
  if (cc) {
    const vazia = f.querySelector(".f-band-vazia");
    if (vazia) {
      const img = document.createElement("img");
      img.className = "f-band";
      img.alt = "";
      img.src = `img/bandeiras/${cc.toLowerCase()}.svg`;
      img.onerror = () => { img.style.display = "none"; };
      vazia.replaceWith(img);
    }
  }
}

export function mostrarContinente(nome) {
  const paises = D.paises.filter((p) => p.cont === nome && p.iso).sort((a, b) => b.pop - a.pop);
  const total = paises.reduce((s, p) => s + p.pop, 0);
  const titulo = idioma === "en" ? nome : (paises[0]?.contPt || nome);
  const html = `${cabecalho("", titulo, `${numero(paises.length)} ${escapar(t("paisesDaqui").toLowerCase())} · ${grande(total)}`)}
    <h3>${escapar(t("paisesDaqui"))}</h3>
    <ul class="f-lista f-lista-paises">${paises.map((p) => `<li><button data-iso="${p.iso}">${bandeira(p.iso)}<span>${escapar(p.nome)}</span><small>${grande(p.pop)}</small></button></li>`).join("")}</ul>`;
  abrir(html);
}

// Os relogios da ficha andam sozinhos enquanto ela esta aberta.
setInterval(() => {
  const f = document.getElementById("ficha");
  if (!f || f.hidden) return;
  f.querySelectorAll("[data-fuso]").forEach((b) => { b.innerHTML = textoHora(b.dataset.fuso); });
}, 20000);
