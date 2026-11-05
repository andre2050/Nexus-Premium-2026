// Liga tudo: abertura, mouse, teclado, botoes, escolha de lugar e comandos do JARVIS.

import {
  alternarInclinacao, altura, cena, criar, definirCobertura, definirGiro, definirModo, definirNoite, definirNomes,
  definirRelevo, marcarToque, moverPara, olharParaONorte, pontoDaTela, temWebgl, terraInteira, voarParaPonto,
  voarParaRetangulo, zoomDeBotao,
} from "./cena.js";
import {
  D, carregar, cidadeMaisProxima, fusoDaCidade, nomeCidade, nomeEstado, paisDaCidade, paisEm,
} from "./dados.js";
import * as paises from "./paises.js";
import * as rotulos from "./rotulos.js";
import * as busca from "./busca.js";
import * as ficha from "./ficha.js";
import * as medir from "./medir.js";
import * as rua from "./rua.js";
import {
  coord, definirIdioma, escapar, grande, horaNoFuso, idioma, km, locale, numero, semAcento, t,
} from "./textos.js";

const C = window.Cesium;
const TOKEN = new URLSearchParams(location.search).get("t") || "";
const el = (id) => document.getElementById(id);

const CONTINENTES = {
  "South America": [-82, -56, -34, 13],
  "North America": [-170, 7, -52, 72],
  Europe: [-25, 35, 45, 71],
  Africa: [-19, -35, 52, 38],
  Asia: [26, -11, 150, 60],
  Oceania: [110, -50, 180, 0],
};

let config = { idioma: "pt", cor: "#00d4ff", host: "", lugar: "" };
let sel = null;           // { tipo, obj, lat, lon, titulo }
let ferramenta = null;    // null | "rua"
let pino = null;
let pinoItem = null;

// ── conversa com o programa ──────────────────────────────────────────────
function post(caminho, corpo) {
  return fetch(caminho, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Token": TOKEN },
    body: JSON.stringify(corpo || {}),
  }).then((r) => r.json()).catch(() => ({ ok: false }));
}

function registrar(linha) {
  post("/api/log", { linha: String(linha).slice(0, 1500) });
}

window.addEventListener("error", (e) => registrar(`erro: ${e.message} (${(e.filename || "").split("/").pop()}:${e.lineno})`));
window.addEventListener("unhandledrejection", (e) => registrar(`promessa: ${e.reason?.message || e.reason}`));

function abrirFora(url) {
  if (config.host === "qt" || config.host === "navegador") post("/api/host", { acao: "externo", url });
  else window.open(url, "_blank", "noopener");
}

// ── avisos ───────────────────────────────────────────────────────────────
let avisoTimer = null;

function avisar(html, botaoLimpar = false, duracao = 0) {
  clearTimeout(avisoTimer);
  const a = el("aviso");
  a.innerHTML = `<span>${html}</span>${botaoLimpar ? `<button class="bt-texto" data-acao="limpar-aviso">${escapar(t("limpar"))}</button>` : ""}`;
  a.hidden = false;
  if (duracao) avisoTimer = setTimeout(() => { a.hidden = true; }, duracao);
}

function tirarAviso() {
  clearTimeout(avisoTimer);
  el("aviso").hidden = true;
}

function atualizarAvisoFerramenta() {
  if (ferramenta === "rua") {
    avisar(`${escapar(altura() > 30000 ? t("avisoRua") : t("avisoRuaPerto"))} <small>${escapar(t("avisoEsc"))}</small>`);
  } else if (medir.medida.ativo) {
    avisar(`${escapar(medir.medida.a ? t("avisoMedirB") : t("avisoMedirA"))} <small>${escapar(t("avisoEsc"))}</small>`);
  } else if (medir.medida.a && medir.medida.b) {
    avisar(medir.textoResultado(), true);
  } else {
    tirarAviso();
  }
  document.body.classList.toggle("mirando", !!ferramenta || medir.medida.ativo);
  el("bt-rua").classList.toggle("ativo", ferramenta === "rua");
  el("bt-medir").classList.toggle("ativo", medir.medida.ativo);
}

function definirFerramenta(f) {
  ferramenta = f;
  if (f === "rua" && medir.medida.ativo) medir.cancelar();
  // Bonequinho na mao: as ruas com Street View ficam azuis, como no Google Maps.
  definirCobertura(f === "rua");
  atualizarAvisoFerramenta();
}

// ── o pino do lugar escolhido ────────────────────────────────────────────
function desenharPino() {
  const c = document.createElement("canvas");
  c.width = 44; c.height = 60;
  const g = c.getContext("2d");
  const cor = config.cor;
  g.shadowColor = cor; g.shadowBlur = 8;
  g.beginPath();
  g.moveTo(22, 56);
  g.bezierCurveTo(22, 56, 6, 34, 6, 22);
  g.arc(22, 22, 16, Math.PI, 0);
  g.bezierCurveTo(38, 34, 22, 56, 22, 56);
  g.closePath();
  g.fillStyle = cor;
  g.fill();
  g.shadowBlur = 0;
  g.beginPath();
  g.arc(22, 22, 6.5, 0, 2 * Math.PI);
  g.fillStyle = "#00121c";
  g.fill();
  return c;
}

function moverPino(lat, lon, h = 0) {
  if (!pino) {
    pino = new C.BillboardCollection({ scene: cena.scene });
    pinoItem = pino.add({
      image: desenharPino(),
      verticalOrigin: C.VerticalOrigin.BOTTOM,
      scale: 0.72,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
      position: C.Cartesian3.ZERO,
      show: false,
    });
    cena.scene.primitives.add(pino);
  }
  if (lat === null) {
    pinoItem.show = false;
  } else {
    pinoItem.position = C.Cartesian3.fromDegrees(lon, lat, h);
    pinoItem.show = true;
  }
  cena.scene.requestRender();
}

// ── o caminho: Terra > continente > pais > cidade ────────────────────────
function pintarRastro() {
  const r = el("rastro");
  const partes = [];
  if (sel) {
    let pais = null;
    let cont = null;
    if (sel.tipo === "continente") cont = sel.obj;
    if (sel.tipo === "pais") pais = sel.obj;
    if (sel.tipo === "cidade") pais = paisDaCidade(sel.obj);
    if (sel.tipo === "ponto") pais = sel.pais || null;
    if (pais) cont = pais.cont;
    const nomeCont = cont && (idioma === "en" ? cont : (D.paises.find((p) => p.cont === cont)?.contPt || cont));
    partes.push(`<button data-rastro="terra">${escapar(t("terra"))}</button>`);
    if (nomeCont && CONTINENTES[cont]) partes.push(`<button data-rastro="continente" data-v="${escapar(cont)}">${escapar(nomeCont)}</button>`);
    else if (nomeCont) partes.push(`<span>${escapar(nomeCont)}</span>`);
    if (pais) partes.push(sel.tipo === "pais" ? `<b>${escapar(pais.nome)}</b>` : `<button data-rastro="pais" data-v="${pais.iso}">${escapar(pais.nome)}</button>`);
    if (sel.tipo === "cidade") partes.push(`<b>${escapar(nomeCidade(sel.obj, idioma))}</b>`);
    if (sel.tipo === "ponto" && sel.titulo) partes.push(`<b>${escapar(sel.titulo)}</b>`);
  }
  r.hidden = !partes.length;
  r.innerHTML = partes.join('<i class="seta">›</i>');
}

// ── escolher um lugar ────────────────────────────────────────────────────
export function limparSelecao(voltar = false) {
  sel = null;
  paises.escolher(null);
  rotulos.definirPrioridade(null);
  moverPino(null);
  ficha.esconder();
  pintarRastro();
  if (voltar) terraInteira();
}

function selecionarPais(p, opcoes = {}) {
  sel = { tipo: "pais", obj: p, lat: p.ly, lon: p.lx, titulo: p.nome };
  paises.escolher(p);
  rotulos.definirPrioridade(null);
  moverPino(null);
  ficha.mostrarPais(p);
  pintarRastro();
  if (opcoes.voar !== false) {
    if (p.en === "Antarctica") {
      voarParaPonto(-82, 20, 9.0e6);
    } else {
      const q = p.quadro;
      voarParaRetangulo(q[0], q[1], q[2], q[3]);
    }
  }
}

function selecionarCidade(c, opcoes = {}) {
  sel = { tipo: "cidade", obj: c, lat: c.lat, lon: c.lon, titulo: nomeCidade(c, idioma) };
  paises.escolher(paisDaCidade(c));
  rotulos.definirPrioridade(c);
  moverPino(c.lat, c.lon, cena.relevo ? c.alt : 0);
  ficha.mostrarCidade(c);
  pintarRastro();
  if (opcoes.voar !== false) {
    const h = 9000 + Math.sqrt(c.pop) * 25 + (cena.relevo ? c.alt : 0);
    voarParaPonto(c.lat, c.lon, h);
  }
}

let _ultimoReverso = 0;
let _controleReverso = null;

/** O endereco de um ponto clicado (OpenStreetMap). No maximo um pedido por segundo. */
async function localizar(lat, lon, minha) {
  _controleReverso?.abort();
  const espera = Math.max(0, 1100 - (performance.now() - _ultimoReverso));
  const controle = new AbortController();
  _controleReverso = controle;
  if (espera) await new Promise((r) => setTimeout(r, espera));
  if (controle.signal.aborted) return;
  _ultimoReverso = performance.now();
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat.toFixed(6)}&lon=${lon.toFixed(6)}&zoom=18&addressdetails=1&accept-language=${locale}`;
    const r = await fetch(url, { signal: controle.signal });
    if (!r.ok) throw new Error(String(r.status));
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    const a = j.address || {};
    const rua_ = a.road ? `${a.road}${a.house_number ? `, ${a.house_number}` : ""}` : "";
    const nome = j.name || rua_ || a.suburb || a.neighbourhood || a.village || a.town || a.city || a.county || a.state || a.country || "";
    const resto = [j.name && rua_ ? rua_ : "", a.suburb || a.neighbourhood, a.city || a.town || a.village || a.municipality, a.state, a.country]
      .filter((x) => x && x !== nome);
    if (sel?.tipo === "ponto") {
      sel.titulo = nome;
      pintarRastro();
    }
    ficha.atualizarPonto(minha, nome || "", [...new Set(resto)].join(", "), String(a.country_code || "").toUpperCase());
  } catch (e) {
    if (e.name !== "AbortError") {
      const perto = cidadeMaisProxima(lat, lon);
      ficha.atualizarPonto(minha, perto ? `${t("pertoDe")} ${nomeCidade(perto.c, idioma)}` : t("oceano"), "", perto?.c.cc || "");
    }
  }
}

function selecionarPonto(o, opcoes = {}) {
  const perto = cidadeMaisProxima(o.lat, o.lon);
  const pais = paisEm(o.lon, o.lat) || (o.cc ? D.porIso[o.cc] : null) || null;
  sel = { tipo: "ponto", obj: o, lat: o.lat, lon: o.lon, titulo: o.nome || "", pais };
  paises.escolher(pais);
  rotulos.definirPrioridade(null);
  moverPino(o.lat, o.lon);
  const minha = ficha.mostrarPonto({
    ...o,
    cc: o.cc || pais?.iso || "",
    fuso: perto ? fusoDaCidade(perto.c) : "",
    perto: perto && perto.d >= 0.5 ? perto : null,
  });
  pintarRastro();
  if (!o.nome) localizar(o.lat, o.lon, minha);
  if (opcoes.voar) {
    const e = o.extent;
    if (e && Math.abs(e[2] - e[0]) > 0.03) voarParaRetangulo(Math.min(e[0], e[2]), Math.min(e[1], e[3]), Math.max(e[0], e[2]), Math.max(e[1], e[3]));
    else voarParaPonto(o.lat, o.lon, 2500);
  }
}

function selecionarContinente(nome) {
  sel = { tipo: "continente", obj: nome };
  paises.escolher(null);
  rotulos.definirPrioridade(null);
  moverPino(null);
  ficha.mostrarContinente(nome);
  pintarRastro();
  const r = CONTINENTES[nome];
  if (r) voarParaRetangulo(r[0], r[1], r[2], r[3]);
}

function irResultado(r) {
  if (r.tipo === "pais") selecionarPais(r.obj);
  else if (r.tipo === "cidade") selecionarCidade(r.obj);
  else selecionarPonto(r.obj, { voar: true });
}

function lugarDoAlvo() {
  if (!sel) return null;
  if (sel.tipo === "pais") {
    const cap = sel.obj.capI != null ? D.cidades[sel.obj.capI] : null;
    if (cap) return { lat: cap.lat, lon: cap.lon, alt: cap.alt, titulo: `${nomeCidade(cap, idioma)}, ${sel.obj.nome}`, busca: `${cap.n}, ${sel.obj.en}`, zoom: 6, nome: sel.obj.nome };
    return { lat: sel.lat, lon: sel.lon, titulo: sel.obj.nome, busca: sel.obj.en, zoom: 5, nome: sel.obj.nome };
  }
  if (sel.tipo === "cidade") {
    const c = sel.obj;
    const pais = paisDaCidade(c);
    return {
      lat: c.lat, lon: c.lon, alt: c.alt,
      titulo: [nomeCidade(c, idioma), nomeEstado(c), pais?.nome].filter(Boolean).join(", "),
      busca: [c.n, nomeEstado(c), pais?.en].filter(Boolean).join(", "),
      zoom: c.pop > 2e6 ? 11 : (c.pop > 2e5 ? 12 : 14),
      nome: nomeCidade(c, idioma),
    };
  }
  if (sel.tipo === "ponto") {
    const titulo = document.querySelector("#ficha .f-tit h2")?.textContent || sel.titulo || coord(sel.lat, sel.lon, 4);
    return { lat: sel.lat, lon: sel.lon, titulo, zoom: 18, nome: titulo };
  }
  return null;
}

function abrirRuaEm(lugar, aba = "street") {
  if (!lugar) return;
  definirFerramenta(null);
  rua.abrir(lugar, aba);
}

// ── clique no globo ──────────────────────────────────────────────────────
function aoClicar(pos) {
  fecharMenu();
  marcarToque();
  const preciso = pontoDaTela(pos.x, pos.y, true);
  const tocado = rotulos.tocou(pos.x, pos.y);

  if (ferramenta === "rua") {
    if (!preciso) return;
    const h = altura();
    if (h > 30000) {
      // De longe o clique nao tem precisao de rua: chega perto de uma vez so', ja no
      // ponto em que as linhas azuis aparecem.
      voarParaPonto(preciso.lat, preciso.lon, 5000, 1.8).then(atualizarAvisoFerramenta);
      return;
    }
    const perto = cidadeMaisProxima(preciso.lat, preciso.lon);
    abrirRuaEm({
      lat: preciso.lat, lon: preciso.lon, alt: preciso.altura,
      titulo: perto ? `${t("pertoDe")} ${nomeCidade(perto.c, idioma)}` : coord(preciso.lat, preciso.lon, 4),
      zoom: 18,
    });
    return;
  }

  if (medir.medida.ativo) {
    if (tocado?.tipo === "cidade") {
      const c = tocado.obj;
      medir.clicar({ lat: c.lat, lon: c.lon, nome: nomeCidade(c, idioma) });
    } else if (preciso) {
      const perto = cidadeMaisProxima(preciso.lat, preciso.lon, 40);
      medir.clicar({ lat: preciso.lat, lon: preciso.lon, nome: perto ? nomeCidade(perto.c, idioma) : "" });
    }
    return;
  }

  if (tocado?.tipo === "cidade") return selecionarCidade(tocado.obj);
  if (tocado?.tipo === "pais") return selecionarPais(tocado.obj);
  if (!preciso) return;

  const h = altura();
  const p = paisEm(preciso.lon, preciso.lat);
  if (h > 420000) {
    if (!p) return limparSelecao();
    if (paises.paisAtual() !== p || sel?.tipo !== "pais") return selecionarPais(p);
    // Clicou de novo no pais que ja esta aberto: e' o lugar dentro dele que interessa.
  }
  selecionarPonto({ lat: preciso.lat, lon: preciso.lon, nome: "", endereco: "" });
}

function aoDuploClique(pos) {
  const p = pontoDaTela(pos.x, pos.y, true);
  if (!p) return;
  const h = altura();
  voarParaPonto(p.lat, p.lon, Math.max(120, h * 0.28), 1.1);
}

// ── mouse em cima do globo ───────────────────────────────────────────────
let arrastando = false;
let ultimoMouse = null;
let pendenteMouse = false;
let hoverUltimo = "";

let leituraAntes = "";
let leituraEm = 0;

function pintarLeitura(ll, forcar = false) {
  // Qualquer mudanca na pagina obriga a janela a compor de novo: dez vezes por
  // segundo ja e' mais que o olho acompanha num numero.
  const agora = performance.now();
  if (!forcar && agora - leituraEm < 100) return;
  leituraEm = agora;
  const h = altura();
  const alt = `<b>ALT</b> ${km(h)}`;
  const txt = ll ? `<b>LAT</b> ${numero(ll.lat, 3)}°  <b>LON</b> ${numero(ll.lon, 3)}°  ${alt}` : alt;
  if (txt !== leituraAntes) {
    leituraAntes = txt;
    el("leitura").innerHTML = txt;
  }
}

function tratarMouse() {
  pendenteMouse = false;
  const m = ultimoMouse;
  if (!m) return;
  const dica = el("dica-cursor");
  if (arrastando || cena.emVoo || ferramenta || medir.medida.ativo) {
    paises.realcar(null);
    dica.hidden = true;
    document.body.classList.remove("sobre-algo");
    if (ferramenta || medir.medida.ativo) pintarLeitura(pontoDaTela(m.x, m.y));
    return;
  }
  const ll = pontoDaTela(m.x, m.y);
  pintarLeitura(ll);
  const tocado = rotulos.tocou(m.x, m.y);
  const h = altura();
  let chave = "";
  let html = "";
  if (tocado?.tipo === "cidade") {
    const c = tocado.obj;
    chave = `c${c.i}`;
    html = `${busca.bandeira(c.cc)}<b>${escapar(nomeCidade(c, idioma))}</b>${nomeEstado(c) ? `<small>${escapar(nomeEstado(c))}</small>` : ""}<small>${grande(c.pop)}</small>`;
    paises.realcar(paisDaCidade(c));
  } else {
    const p = ll && h > 150000 ? paisEm(ll.lon, ll.lat) : null;
    paises.realcar(h > 420000 ? p : null);
    if (p && h > 420000) {
      chave = `p${p.iso || p.en}`;
      html = `${busca.bandeira(p.iso)}<b>${escapar(p.nome)}</b>`;
    }
  }
  document.body.classList.toggle("sobre-algo", !!chave);
  if (chave !== hoverUltimo) {
    hoverUltimo = chave;
    dica.innerHTML = html;
  }
  dica.hidden = !chave;
  if (chave) {
    const largura = dica.offsetWidth;
    const x = Math.min(window.innerWidth - largura - 12, m.x + 16);
    dica.style.transform = `translate(${x}px, ${m.y + 18}px)`;
  }
}

function pedirMouse() {
  if (pendenteMouse) return;
  pendenteMouse = true;
  requestAnimationFrame(tratarMouse);
}

// ── menu do botao direito ────────────────────────────────────────────────
let menuPonto = null;

function fecharMenu() {
  el("menu").hidden = true;
  menuPonto = null;
}

function abrirMenu(pos) {
  const p = pontoDaTela(pos.x, pos.y, true);
  if (!p) return fecharMenu();
  menuPonto = p;
  const m = el("menu");
  m.innerHTML = `<small>${escapar(coord(p.lat, p.lon, 4))}</small>
    <button data-menu="street"><svg class="ic cheio"><use href="#i-pessoa"/></svg>${escapar(t("acStreet"))}</button>
    <button data-menu="maps"><svg class="ic"><use href="#i-mapa"/></svg>${escapar(t("acMaps"))}</button>
    <button data-menu="medir"><svg class="ic"><use href="#i-regua"/></svg>${escapar(t("acMedir"))}</button>
    <button data-menu="copiar"><svg class="ic"><use href="#i-alvo"/></svg>${escapar(t("acCopiar"))}</button>`;
  m.hidden = false;
  const x = Math.min(window.innerWidth - m.offsetWidth - 8, pos.x);
  const y = Math.min(window.innerHeight - m.offsetHeight - 8, pos.y);
  m.style.transform = `translate(${x}px, ${y}px)`;
}

async function copiarCoordenadas(lat, lon) {
  const texto = `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
  try {
    await navigator.clipboard.writeText(texto);
  } catch {
    const a = document.createElement("textarea");
    a.value = texto;
    document.body.appendChild(a);
    a.select();
    document.execCommand("copy");
    a.remove();
  }
  avisar(escapar(`${t("copiado")}: ${texto}`), false, 2200);
}

// ── botoes da tela ───────────────────────────────────────────────────────
function pintarModos() {
  document.querySelectorAll("[data-modo]").forEach((b) => b.classList.toggle("ativo", b.dataset.modo === cena.modo));
  el("bt-noite").classList.toggle("ativo", cena.noite);
  el("bt-noite").disabled = cena.modo !== "satelite";
  el("bt-nomes").classList.toggle("ativo", cena.nomes);
  el("bt-bordas").classList.toggle("ativo", cena.bordas);
  el("bt-relevo").classList.toggle("ativo", cena.relevo);
  el("bt-girar").classList.toggle("ativo", cena.girar);
  document.body.dataset.modo = cena.modo;
}

function trocarModo(modo) {
  definirModo(modo);
  rotulos.atualizar();
  paises.ajustar(altura());
  pintarModos();
}

function ligarBotoes() {
  document.querySelectorAll("[data-modo]").forEach((b) => b.addEventListener("click", () => trocarModo(b.dataset.modo)));
  el("bt-noite").addEventListener("click", () => { definirNoite(!cena.noite); pintarModos(); });
  el("bt-nomes").addEventListener("click", () => {
    definirNomes(!cena.nomes);
    rotulos.definirLigado(cena.nomes);
    pintarModos();
  });
  el("bt-bordas").addEventListener("click", () => {
    cena.bordas = !cena.bordas;
    paises.ajustar(altura());
    cena.scene.requestRender();
    pintarModos();
  });
  el("bt-relevo").addEventListener("click", async () => {
    const r = await definirRelevo(!cena.relevo);
    rotulos.esquecerPosicoes();
    if (!r && cena.semInternet) avisar(escapar(t("semInternet")), false, 2600);
    pintarModos();
  });
  el("bt-girar").addEventListener("click", () => { definirGiro(!cena.girar); pintarModos(); });
  el("bt-rua").addEventListener("click", () => definirFerramenta(ferramenta === "rua" ? null : "rua"));
  el("bt-medir").addEventListener("click", () => {
    ferramenta = null;
    if (medir.medida.ativo) medir.cancelar();
    else medir.iniciar();
  });
  el("bt-mais").addEventListener("click", () => { marcarToque(); zoomDeBotao(0.55); });
  el("bt-menos").addEventListener("click", () => { marcarToque(); zoomDeBotao(1.8); });
  el("bt-terra").addEventListener("click", () => { marcarToque(); limparSelecao(true); });
  el("bussola").addEventListener("click", () => { marcarToque(); olharParaONorte(); });
  el("bt-3d").addEventListener("click", () => { marcarToque(); alternarInclinacao(); });
  el("btn-fechar").addEventListener("click", () => {
    post("/api/host", { acao: "fechar" }).then(() => setTimeout(() => window.close(), 150));
  });
  el("btn-tela").addEventListener("click", () => {
    if (config.host === "qt") post("/api/host", { acao: "tela_cheia" });
    else if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  });
  el("bt-fontes").addEventListener("click", () => {
    const f = el("fontes-lista");
    if (f.hidden) {
      f.innerHTML = `<h3>${escapar(t("fontesTitulo"))}</h3><dl>${t("fontesTexto").map(([a, b]) => `<dt>${escapar(a)}</dt><dd>${escapar(b)}</dd>`).join("")}</dl>`;
    }
    f.hidden = !f.hidden;
  });

  el("rua-parar").addEventListener("click", () => {
    post("/api/host", { acao: "passeio_parar" });
    rua.marcarPasseio(false);
  });

  el("aviso").addEventListener("click", (e) => {
    if (e.target.closest('[data-acao="limpar-aviso"]')) medir.limpar();
  });

  el("rastro").addEventListener("click", (e) => {
    const b = e.target.closest("[data-rastro]");
    if (!b) return;
    marcarToque();
    if (b.dataset.rastro === "terra") limparSelecao(true);
    if (b.dataset.rastro === "continente") selecionarContinente(b.dataset.v);
    if (b.dataset.rastro === "pais") selecionarPais(D.porIso[b.dataset.v]);
  });

  el("menu").addEventListener("click", (e) => {
    const b = e.target.closest("[data-menu]");
    const p = menuPonto;
    fecharMenu();
    if (!b || !p) return;
    const perto = cidadeMaisProxima(p.lat, p.lon);
    const titulo = perto ? `${t("pertoDe")} ${nomeCidade(perto.c, idioma)}` : coord(p.lat, p.lon, 4);
    const lugar = { lat: p.lat, lon: p.lon, alt: p.altura, titulo, zoom: 17 };
    if (b.dataset.menu === "street") abrirRuaEm(lugar, "street");
    if (b.dataset.menu === "maps") abrirRuaEm(lugar, "maps");
    if (b.dataset.menu === "medir") {
      definirFerramenta(null);
      medir.iniciar({ lat: p.lat, lon: p.lon, nome: perto && perto.d < 40 ? nomeCidade(perto.c, idioma) : "" });
    }
    if (b.dataset.menu === "copiar") copiarCoordenadas(p.lat, p.lon);
  });

  el("ficha").addEventListener("click", (e) => {
    const cid = e.target.closest("[data-cid]");
    if (cid) return selecionarCidade(D.cidades[Number(cid.dataset.cid)]);
    const iso = e.target.closest("[data-iso]");
    if (iso) return selecionarPais(D.porIso[iso.dataset.iso]);
    const a = e.target.closest("[data-acao]");
    if (!a) return;
    const acao = a.dataset.acao;
    if (acao === "fechar") return limparSelecao();
    if (acao === "wiki") return abrirFora(a.dataset.url);
    if (acao === "capital" && sel?.tipo === "pais" && sel.obj.capI != null) return selecionarCidade(D.cidades[sel.obj.capI]);
    if (acao === "copiar" && sel) return copiarCoordenadas(sel.lat, sel.lon);
    const lugar = lugarDoAlvo();
    if (!lugar) return;
    if (acao === "street") return abrirRuaEm(lugar, "street");
    if (acao === "maps") return abrirRuaEm(lugar, "maps");
    if (acao === "medir") {
      definirFerramenta(null);
      medir.iniciar({ lat: lugar.lat, lon: lugar.lon, nome: lugar.nome });
    }
  });
}

function ligarTeclado() {
  document.addEventListener("keydown", (e) => {
    marcarToque();
    const escrevendo = e.target.matches?.("input, textarea");
    if ((e.ctrlKey && e.key.toLowerCase() === "k") || (e.key === "/" && !escrevendo)) {
      e.preventDefault();
      busca.focar();
      return;
    }
    if (e.key === "Escape") {
      if (!el("menu").hidden) return fecharMenu();
      if (!el("fontes-lista").hidden) { el("fontes-lista").hidden = true; return; }
      if (rua.estaAberto() || rua.estaEntrando()) return rua.fechar();
      if (ferramenta) return definirFerramenta(null);
      if (medir.medida.ativo) return medir.cancelar();
      if (medir.medida.a) return medir.limpar();
      if (cena.emVoo) { cena.camera.cancelFlight(); return; }
      if (sel) return limparSelecao();
      return;
    }
    if (escrevendo || rua.estaAberto()) return;
    const h = altura();
    const passo = C.Math.clamp(h / 6378137, 0.002, 0.5) * 0.14;
    const cam = cena.camera;
    switch (e.key) {
      case "ArrowLeft": cam.rotate(C.Cartesian3.UNIT_Z, -passo); break;
      case "ArrowRight": cam.rotate(C.Cartesian3.UNIT_Z, passo); break;
      case "ArrowUp": cam.rotateUp(-passo); break;
      case "ArrowDown": cam.rotateDown(-passo); break;
      case "+": case "=": zoomDeBotao(0.6); break;
      case "-": zoomDeBotao(1.6); break;
      default: return;
    }
    e.preventDefault();
    cena.scene.requestRender();
  });
}

// ── relogio do canto ─────────────────────────────────────────────────────
let relogioAntes = "";

function pintarRelogio() {
  const agora = new Date();
  const hora = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(agora);
  if (hora === relogioAntes) return;
  relogioAntes = hora;
  el("relogio-hora").textContent = hora;
  const off = -agora.getTimezoneOffset();
  const sinal = off >= 0 ? "+" : "−";
  const hh = String(Math.floor(Math.abs(off) / 60)).padStart(2, "0");
  const mm = String(Math.abs(off) % 60).padStart(2, "0");
  el("relogio-fuso").textContent = `UTC${sinal}${hh}:${mm}`;
}

// ── comandos do JARVIS (voz) ─────────────────────────────────────────────
const NOMES_CONTINENTE = {
  "america do sul": "South America", "south america": "South America",
  "america do norte": "North America", "north america": "North America",
  europa: "Europe", europe: "Europe", africa: "Africa", asia: "Asia", oceania: "Oceania",
};

/** Capital do pais ou do estado: "capital do Japao", "capital da Paraiba". */
function acharCapital(texto) {
  const q = semAcento(texto).trim();
  if (!q) {
    // "vai na capital": a do pais que esta na tela.
    const p = sel?.tipo === "pais" ? sel.obj : (sel?.tipo === "cidade" ? paisDaCidade(sel.obj) : null);
    return p?.capI != null ? D.cidades[p.capI] : null;
  }
  const pais = busca.buscarLocal(texto, 12).find((r) => r.tipo === "pais");
  if (pais && pais.nota >= 3000 && pais.obj.capI != null) return D.cidades[pais.obj.capI];
  // Estado: a capital e' a cidade marcada como sede daquele estado.
  for (const c of D.cidades) {
    if (c.cap === 1 && semAcento(nomeEstado(c)) === q) return c;
  }
  return pais?.obj.capI != null ? D.cidades[pais.obj.capI] : null;
}

function resumo(r) {
  if (r.tipo === "pais") {
    const p = r.obj;
    const cap = p.capI != null ? D.cidades[p.capI] : null;
    return { ok: true, tipo: "pais", nome: p.nome, continente: idioma === "en" ? p.cont : p.contPt, capital: cap ? nomeCidade(cap, idioma) : p.cap, populacao: p.pop };
  }
  if (r.tipo === "cidade") {
    const c = r.obj;
    const hora = horaNoFuso(fusoDaCidade(c));
    return { ok: true, tipo: "cidade", nome: nomeCidade(c, idioma), estado: nomeEstado(c), pais: paisDaCidade(c)?.nome || "", populacao: c.pop, hora_local: hora?.hora || "" };
  }
  return { ok: true, tipo: "lugar", nome: r.obj.nome, endereco: r.obj.endereco || "", lat: r.obj.lat, lon: r.obj.lon };
}

function pontoDoResultado(r) {
  if (r.tipo === "pais") {
    const cap = r.obj.capI != null ? D.cidades[r.obj.capI] : null;
    return cap ? { lat: cap.lat, lon: cap.lon, nome: nomeCidade(cap, idioma) } : { lat: r.obj.ly, lon: r.obj.lx, nome: r.obj.nome };
  }
  if (r.tipo === "cidade") return { lat: r.obj.lat, lon: r.obj.lon, nome: nomeCidade(r.obj, idioma) };
  return { lat: r.obj.lat, lon: r.obj.lon, nome: r.obj.nome };
}

async function executar(acao, d) {
  marcarToque();
  switch (acao) {
    case "ouvi":
      avisar(`<small class="ouvi">🎙</small> ${escapar(String(d.texto || ""))}`, false, 2600);
      return { ok: true };
    case "tem_lugar":
      return { ok: true, existe: busca.existeLugar(String(d.lugar || ""), !!d.so_grandes) };
    case "ir": {
      if (rua.estaAberto()) rua.fechar(false);
      definirFerramenta(null);
      const tipo = String(d.tipo || "");
      if (tipo === "capital") {
        const c = acharCapital(String(d.lugar || ""));
        if (!c) return { ok: false, erro: "capital nao encontrada" };
        selecionarCidade(c);
        return { ...resumo({ tipo: "cidade", obj: c }), capital_de: true };
      }
      const cont = NOMES_CONTINENTE[semAcento(String(d.lugar || "")).trim()];
      if (cont) {
        selecionarContinente(cont);
        return { ok: true, tipo: "continente", nome: sel?.obj && (idioma === "en" ? cont : D.paises.find((p) => p.cont === cont)?.contPt) };
      }
      const r = await busca.resolver(String(d.lugar || ""), tipo);
      if (!r) return { ok: false, erro: "lugar nao encontrado" };
      irResultado(r);
      return resumo(r);
    }
    case "guia":
      rua.mostrarGuia(d.titulo ? d : null);
      return { ok: true };
    case "passeio":
      rua.marcarPasseio(!!d.ativo);
      return { ok: true };
    case "rua_saltar":
      return rua.saltar(Number(d.lat), Number(d.lon), Number(d.rumo));
    case "mover":
      if (!rua.estaAberto()) moverPara(String(d.direcao || "norte"));
      return { ok: true };
    case "inclinar":
      if (!rua.estaAberto()) alternarInclinacao();
      return { ok: true };
    case "street_view":
    case "google_maps": {
      const aba = acao === "street_view" ? "street" : "maps";
      if (rua.estaAberto()) rua.fechar(false);
      if (d.lugar) {
        const r = await busca.resolver(String(d.lugar), String(d.tipo || ""));
        if (!r) return { ok: false, erro: "lugar nao encontrado" };
        irResultado(r);
        cena.camera.cancelFlight();
        abrirRuaEm(lugarDoAlvo(), aba);
        return resumo(r);
      }
      // Nada escolhido: e' o lugar que esta no meio da tela.
      let alvo = lugarDoAlvo();
      if (!alvo) {
        const meio = pontoDaTela(cena.canvas.clientWidth / 2, cena.canvas.clientHeight / 2);
        if (!meio) return { ok: false, erro: "nenhum lugar escolhido no globo" };
        const perto = cidadeMaisProxima(meio.lat, meio.lon, 300);
        const c = perto?.c;
        alvo = {
          lat: meio.lat, lon: meio.lon, alt: meio.altura, zoom: 15,
          titulo: c ? nomeCidade(c, idioma) : coord(meio.lat, meio.lon, 4),
          nome: c ? nomeCidade(c, idioma) : "",
        };
      }
      abrirRuaEm(alvo, aba);
      return { ok: true, nome: alvo.nome || alvo.titulo };
    }
    case "medir": {
      const a = await busca.resolver(String(d.origem || ""));
      const b = await busca.resolver(String(d.destino || ""));
      if (!a || !b) return { ok: false, erro: `nao encontrei ${!a ? d.origem : d.destino}` };
      if (rua.estaAberto()) rua.fechar(false);
      const pa = pontoDoResultado(a);
      const pb = pontoDoResultado(b);
      medir.medirEntre(pa, pb);
      return { ok: true, origem: pa.nome, destino: pb.nome, km: Math.round(medir.medida.metros / 1000) };
    }
    case "modo":
      trocarModo(String(d.modo || "satelite"));
      return { ok: true, modo: cena.modo };
    case "noite":
      definirNoite(d.ligado !== false);
      pintarModos();
      return { ok: true };
    case "girar":
      definirGiro(d.ligado !== false);
      pintarModos();
      return { ok: true };
    case "zoom":
      zoomDeBotao(String(d.direcao) === "afastar" ? 2.2 : 0.4);
      return { ok: true };
    case "terra":
      if (rua.estaAberto()) rua.fechar(false);
      limparSelecao(true);
      return { ok: true };
    case "voltar":
      if (rua.estaAberto() || rua.estaEntrando()) rua.fechar();
      else if (sel) limparSelecao(false);
      return { ok: true };
    case "estado":
      return {
        ok: true, modo: cena.modo, altura_km: Math.round(altura() / 1000),
        escolhido: sel ? sel.titulo || "" : "", street_view: rua.estaAberto(),
      };
    default:
      return { ok: false, erro: `comando desconhecido: ${acao}` };
  }
}

function ouvirJarvis() {
  if (!TOKEN) return;
  const fonte = new EventSource(`/api/eventos?t=${encodeURIComponent(TOKEN)}`);
  fonte.onmessage = async (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    let dados;
    try {
      dados = await executar(msg.acao, msg.dados || {});
    } catch (exc) {
      registrar(`comando ${msg.acao}: ${exc?.message || exc}`);
      dados = { ok: false, erro: String(exc?.message || exc) };
    }
    post("/api/resposta", { id: msg.id, dados });
  };
}

// ── falhas ───────────────────────────────────────────────────────────────
function mostrarFalha(titulo, dica) {
  el("carga").hidden = true;
  const f = el("falha");
  f.hidden = false;
  f.innerHTML = `<div class="vidro falha-caixa"><h2>${escapar(titulo)}</h2><p>${escapar(dica)}</p>
    <button class="f-bt principal" id="falha-maps"><svg class="ic"><use href="#i-mapa"/></svg><span>${escapar(t("abrirMapaNav"))}</span></button></div>`;
  el("falha-maps").addEventListener("click", () => abrirFora("https://www.google.com/maps"));
}

function recarregarUmaVez(motivo) {
  registrar(`grafico caiu: ${motivo}`);
  const vezes = Number(sessionStorage.getItem("globo_quedas") || 0);
  if (vezes >= 2) {
    mostrarFalha(t("semWebgl"), t("semWebglDica"));
    return;
  }
  sessionStorage.setItem("globo_quedas", String(vezes + 1));
  avisar(escapar(t("erroMotor")));
  setTimeout(() => location.reload(), 1200);
}

// ── abertura ─────────────────────────────────────────────────────────────
function progresso(p, texto) {
  el("carga-progresso").style.width = `${Math.round(p)}%`;
  if (texto) el("carga-texto").textContent = t(texto);
}

const proximoQuadro = () => new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));

function esperarImagem(limiteMs = 3500) {
  return new Promise((ok) => {
    const fim = performance.now() + limiteMs;
    const ver = () => {
      if (cena.globe.tilesLoaded || performance.now() > fim) return ok();
      setTimeout(ver, 80);
    };
    ver();
  });
}

async function abrirTudo() {
  try {
    config = { ...config, ...(await fetch("/api/config").then((r) => r.json())) };
  } catch { /* fica o padrao */ }
  definirIdioma(config.idioma);
  document.documentElement.style.setProperty("--pri", config.cor || "#00d4ff");
  document.title = idioma === "en" ? "JARVIS — Globe" : "JARVIS — Globo";
  progresso(6, "carregandoMotor");

  if (!temWebgl()) {
    mostrarFalha(t("semWebgl"), t("semWebglDica"));
    registrar("sem WebGL2");
    return;
  }
  await proximoQuadro();

  try {
    criar(config.cor);
  } catch (exc) {
    registrar(`motor nao subiu: ${exc?.message || exc}`);
    mostrarFalha(t("semWebgl"), t("semWebglDica"));
    return;
  }
  const { scene, camera, canvas } = cena;
  camera.setView({
    destination: C.Cartesian3.fromDegrees(-30, 6, 2.9e7),
    orientation: { heading: 0, pitch: -C.Math.PI_OVER_TWO, roll: 0 },
  });

  scene.renderError.addEventListener((_, erro) => recarregarUmaVez(erro?.message || erro));
  canvas.addEventListener("webglcontextlost", (e) => {
    e.preventDefault();
    recarregarUmaVez("contexto perdido");
  });
  cena.aoMudarRede = (falhou) => {
    const r = el("estado-rede");
    r.textContent = t("semInternet");
    r.hidden = !falhou;
  };
  cena.aoBaixarQualidade = (fps, escala) => registrar(`qualidade baixou: ${fps.toFixed(0)} fps, escala ${escala.toFixed(2)} (${cena.placa})`);

  progresso(16);
  await carregar((etapa) => progresso(etapa === "paises" ? 26 : 48, etapa === "paises" ? "carregandoPaises" : "carregandoCidades"));
  progresso(66, "carregandoTerra");
  await proximoQuadro();
  paises.construir();
  progresso(78);
  await proximoQuadro();
  rotulos.construir();
  medir.preparar(atualizarAvisoFerramenta);
  rua.preparar(abrirFora);
  busca.preparar(irResultado);
  ligarBotoes();
  ligarTeclado();
  progresso(88);

  // Mouse: Cesium cuida de girar e aproximar; aqui e' so' o que escolhe lugar.
  const mao = new C.ScreenSpaceEventHandler(canvas);
  mao.setInputAction((e) => aoClicar(e.position), C.ScreenSpaceEventType.LEFT_CLICK);
  mao.setInputAction((e) => aoDuploClique(e.position), C.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
  mao.setInputAction((e) => abrirMenu(e.position), C.ScreenSpaceEventType.RIGHT_CLICK);
  canvas.addEventListener("pointermove", (e) => {
    ultimoMouse = { x: e.offsetX, y: e.offsetY };
    pedirMouse();
  }, { passive: true });
  canvas.addEventListener("pointerdown", () => {
    arrastando = true;
    marcarToque();
    fecharMenu();
    busca.fecharLista();
    el("fontes-lista").hidden = true;
    document.body.classList.add("arrastando");
  }, { passive: true });
  window.addEventListener("pointerup", () => {
    arrastando = false;
    document.body.classList.remove("arrastando");
  }, { passive: true });
  canvas.addEventListener("wheel", () => marcarToque(), { passive: true });
  canvas.addEventListener("pointerleave", () => {
    el("dica-cursor").hidden = true;
    paises.realcar(null);
  }, { passive: true });

  // O que o navegador faria sozinho e estragaria a tela.
  document.addEventListener("contextmenu", (e) => { if (!e.target.matches?.("input")) e.preventDefault(); });
  window.addEventListener("wheel", (e) => { if (e.ctrlKey) e.preventDefault(); }, { passive: false });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  // A bussola gira com a camera.
  const agulha = el("agulha");
  let rumoAntes = "";
  scene.postRender.addEventListener(() => {
    const rumo = `rotate(${(-C.Math.toDegrees(camera.heading)).toFixed(0)})`;
    if (rumo !== rumoAntes) {
      rumoAntes = rumo;
      agulha.setAttribute("transform", rumo);
    }
  });
  cena.aoMover.push(() => { if (!ultimoMouse) pintarLeitura(null); else pedirMouse(); });
  cena.aoParar.push(() => {
    if (ferramenta) atualizarAvisoFerramenta();
    pintarLeitura(ultimoMouse ? pontoDaTela(ultimoMouse.x, ultimoMouse.y) : null, true);
  });

  pintarRelogio();
  setInterval(pintarRelogio, 15000);
  pintarLeitura(null);
  definirModo("satelite");
  pintarModos();
  ouvirJarvis();

  await esperarImagem();
  progresso(100);
  sessionStorage.removeItem("globo_quedas");
  const carga = el("carga");
  carga.classList.add("saindo");
  setTimeout(() => { carga.hidden = true; }, 700);

  // A chegada: a Terra vem de longe e para em cima do Brasil.
  await terraInteira(-52, 2.6, 8);
  scene.requestRender();
  post("/api/pronta");

  if (config.lugar) {
    executar("ir", { lugar: config.lugar }).catch(() => {});
  }
}

abrirTudo().catch((exc) => {
  registrar(`abertura: ${exc?.stack || exc}`);
  mostrarFalha(t("semWebgl"), t("semWebglDica"));
});

// Para os testes e para depurar pelo console.
window.__globo = { cena, D, executar, selecionarPais, selecionarCidade, selecionarPonto, medir, rua, busca, semAcento };
