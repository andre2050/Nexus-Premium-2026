// Street View e Google Maps dentro da janela, sem precisar de chave.
//
// Usa os enderecos de incorporacao publicos do Google. Se um dia ele mudar isso, o
// botao "Abrir no navegador" usa o endereco oficial documentado (Maps URLs).

import { cena, pausar, voar } from "./cena.js";
import { locale } from "./textos.js";

const C = window.Cesium;

const estado = { aberto: false, aba: "street", lugar: null, voltarPara: null, chamada: 0 };
let abrirFora = null;

const el = (id) => document.getElementById(id);

function urlStreet(l, rumo) {
  const ponto = `!2m2!1d${l.lat.toFixed(6)}!2d${l.lon.toFixed(6)}`;
  const pb = rumo === undefined ? `!6m6!1m5${ponto}!4f0!5f1` : `!6m7!1m6${ponto}!3f${rumo.toFixed(1)}!4f0!5f1`;
  return `https://www.google.com/maps/embed?origin=mfe&pb=${pb}&hl=${locale}`;
}

function urlMaps(l) {
  const q = l.busca || `${l.lat.toFixed(6)},${l.lon.toFixed(6)}`;
  return `https://maps.google.com/maps?q=${encodeURIComponent(q)}&z=${l.zoom || 16}&t=k&hl=${locale}&output=embed`;
}

function urlFora(l, aba) {
  if (aba === "street") return `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${l.lat.toFixed(6)},${l.lon.toFixed(6)}`;
  return `https://www.google.com/maps/search/?api=1&query=${l.lat.toFixed(6)},${l.lon.toFixed(6)}`;
}

const COBERTURA = (x, y, z) => `https://mts${(x + y) % 4}.googleapis.com/vt?hl=en&lyrs=svv%7Ccb_client:apiv3&style=40,18&x=${x}&y=${y}&z=${z}`;

function carregarLadrilho(x, y, z) {
  return new Promise((ok) => {
    const im = new Image();
    im.crossOrigin = "anonymous";
    im.onload = () => {
      try {
        const c = document.createElement("canvas");
        c.width = im.width;
        c.height = im.height;
        const g = c.getContext("2d", { willReadFrequently: true });
        g.drawImage(im, 0, 0);
        ok(g.getImageData(0, 0, im.width, im.height));
      } catch {
        ok(null);
      }
    };
    im.onerror = () => ok(null);
    im.src = COBERTURA(x, y, z);
    setTimeout(() => ok(null), 3500);
  });
}

const LINHA_MINIMA = 60;       // pixels juntos: menos que isso e' bolinha, nao rua

/** Para cada pixel opaco, o tamanho do pedaco a que ele pertence. */
function pedacosOpacos(d) {
  const { width: L, height: A, data } = d;
  const rotulo = new Int32Array(L * A);
  const tamanhoDe = [0];
  const pilha = [];
  for (let k = 0; k < L * A; k++) {
    if (rotulo[k] || data[k * 4 + 3] < 120) continue;
    const id = tamanhoDe.length;
    let total = 0;
    let naBorda = false;
    pilha.push(k);
    rotulo[k] = id;
    while (pilha.length) {
      const q = pilha.pop();
      total++;
      const x = q % L;
      const y = (q - x) / L;
      if (x === 0 || y === 0 || x === L - 1 || y === A - 1) naBorda = true;
      for (const v of [x > 0 ? q - 1 : -1, x < L - 1 ? q + 1 : -1, y > 0 ? q - L : -1, y < A - 1 ? q + L : -1]) {
        if (v >= 0 && !rotulo[v] && data[v * 4 + 3] >= 120) {
          rotulo[v] = id;
          pilha.push(v);
        }
      }
    }
    // Pedaco que encosta na beira do ladrilho continua no vizinho: e' rua.
    tamanhoDe.push(naBorda ? Math.max(total, LINHA_MINIMA) : total);
  }
  const saida = new Int32Array(L * A);
  for (let k = 0; k < L * A; k++) saida[k] = tamanhoDe[rotulo[k]] || 0;
  return saida;
}

/**
 * Onde tem Street View mais perto daqui? Le as linhas azuis do proprio Google. Sem
 * isto, clicar a 60 m de uma rua dava tela preta com "No Street View available".
 */
async function ruaMaisPerto(lat, lon, z, raio) {
  const n = 2 ** z;
  const px = ((lon + 180) / 360) * n * 256;
  const sen = Math.sin((lat * Math.PI) / 180);
  const py = (0.5 - Math.log((1 + sen) / (1 - sen)) / (4 * Math.PI)) * n * 256;
  const tx = Math.floor(px / 256);
  const ty = Math.floor(py / 256);
  const pedidos = [];
  for (let dx = -raio; dx <= raio; dx++) {
    for (let dy = -raio; dy <= raio; dy++) {
      const x = ((tx + dx) % n + n) % n;
      const y = ty + dy;
      if (y < 0 || y >= n) continue;
      pedidos.push(carregarLadrilho(x, y, z).then((d) => ({ d, ox: (tx + dx) * 256, oy: y * 256 })));
    }
  }
  // RUA PRIMEIRO. O mesmo desenho traz as linhas (carro do Google) e bolinhas soltas
  // (foto de turista, muitas vezes dentro de uma igreja ou loja). Bolinha e' pedaco
  // pequeno e isolado: so' vale se nao tiver rua nenhuma por perto.
  let rua = null;
  let foto = null;
  for (const { d, ox, oy } of await Promise.all(pedidos)) {
    if (!d) continue;
    const tamanhos = pedacosOpacos(d);
    for (let i = 3, k = 0; i < d.data.length; i += 4, k++) {
      if (d.data[i] < 120) continue;
      const wx = ox + (k % d.width) + 0.5;
      const wy = oy + Math.floor(k / d.width) + 0.5;
      const dist = (wx - px) ** 2 + (wy - py) ** 2;
      if (tamanhos[k] >= LINHA_MINIMA) {
        if (!rua || dist < rua.dist) rua = { dist, wx, wy };
      } else if (!foto || dist < foto.dist) {
        foto = { dist, wx, wy };
      }
    }
  }
  const melhor = rua || foto;
  if (!melhor) return null;
  const lonAchada = (melhor.wx / (n * 256)) * 360 - 180;
  const m = Math.PI - (2 * Math.PI * melhor.wy) / (n * 256);
  const latAchada = (180 / Math.PI) * Math.atan(Math.sinh(m));
  return { lat: latAchada, lon: lonAchada };
}

/** Procura perto com detalhe; se nao tiver nada, abre a busca e volta a olhar de perto. */
async function acharRua(lat, lon) {
  try {
    let r = await ruaMaisPerto(lat, lon, 16, 1);
    if (r) return r;
    r = await ruaMaisPerto(lat, lon, 13, 2);
    if (r) return (await ruaMaisPerto(r.lat, r.lon, 16, 0)) || r;
    r = await ruaMaisPerto(lat, lon, 10, 2);
    if (r) {
      const perto = await ruaMaisPerto(r.lat, r.lon, 13, 1);
      if (perto) return (await ruaMaisPerto(perto.lat, perto.lon, 16, 0)) || perto;
      return r;
    }
  } catch { /* sem resposta: tenta no ponto pedido mesmo */ }
  return null;
}

function mostrarAba(aba) {
  estado.aba = aba;
  const corpo = el("rua-corpo");
  corpo.querySelectorAll("iframe").forEach((f) => { f.hidden = f.dataset.aba !== aba; });
  if (!corpo.querySelector(`iframe[data-aba="${aba}"]`)) {
    const f = document.createElement("iframe");
    f.dataset.aba = aba;
    f.allowFullscreen = true;
    f.referrerPolicy = "no-referrer-when-downgrade";
    f.setAttribute("allow", "accelerometer; gyroscope; fullscreen");
    f.src = aba === "street" ? urlStreet(estado.lugar) : urlMaps(estado.lugar);
    corpo.appendChild(f);
  }
  document.querySelectorAll("#rua-abas button").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === aba));
  el("rua-dica").hidden = aba !== "street";
}

export function estaAberto() {
  return estado.aberto;
}

/** Ainda procurando a rua ou mergulhando: "volta" e ESC tambem valem aqui. */
export function estaEntrando() {
  return estado.entrando;
}

/**
 * Entra no lugar. Antes de abrir, a camera mergulha ate o chao: e' o que da a
 * sensacao de sair do espaco e chegar na rua.
 */
export async function abrir(lugar, aba = "street", mergulhar = true) {
  const minha = ++estado.chamada;
  const c = cena.camera;
  estado.entrando = true;
  estado.voltarPara = {
    destination: c.positionWC.clone(),
    orientation: { heading: c.heading, pitch: c.pitch, roll: c.roll },
  };
  // Street View: antes de mais nada, o ponto com imagem mais perto do que foi pedido.
  if (aba === "street") {
    const rua = await acharRua(lugar.lat, lugar.lon);
    if (minha !== estado.chamada) return;
    if (rua) {
      lugar = { ...lugar, lat: rua.lat, lon: rua.lon };
    } else {
      aba = "maps";       // nao tem Street View nesta regiao: o mapa ao menos mostra o lugar
    }
  }
  estado.lugar = lugar;
  estado.aba = aba;
  if (mergulhar && cena.nivel !== "leve") {
    const h0 = c.positionCartographic.height;
    await voar({
      destination: C.Cartesian3.fromDegrees(lugar.lon, lugar.lat, Math.max(220, (lugar.alt || 0) + 220)),
      orientation: { heading: c.heading, pitch: C.Math.toRadians(-38), roll: 0 },
      duration: C.Math.clamp(0.9 + Math.log10(Math.max(h0, 1000) / 1000) * 0.7, 1.0, 3.2),
      easingFunction: C.EasingFunction.QUADRATIC_IN_OUT,
    });
    if (minha !== estado.chamada) return;
  }
  estado.entrando = false;
  estado.aberto = true;
  pausar(true);
  el("rua-titulo").textContent = lugar.titulo || "";
  const painel = el("rua");
  painel.hidden = false;
  requestAnimationFrame(() => painel.classList.add("aberto"));
  mostrarAba(aba);
}

/**
 * O passeio reabre o Street View mais a frente quando as fotos da rua nao estao ligadas. A pagina
 * do Google recarrega; quem confere se chegou em um lugar novo e' o passeio.
 */
export async function saltar(lat, lon, rumo) {
  const f = el("rua-corpo").querySelector('iframe[data-aba="street"]');
  if (!estado.aberto || !f) return { ok: false };
  const achou = (await acharRua(lat, lon)) || { lat, lon };
  estado.lugar = { ...estado.lugar, lat: achou.lat, lon: achou.lon };
  f.src = urlStreet(estado.lugar, rumo);
  return { ok: true, lat: achou.lat, lon: achou.lon };
}

export function fechar(voltar = true) {
  estado.chamada++;
  if (!estado.aberto) {
    if (estado.entrando) {
      estado.entrando = false;
      if (voltar && estado.voltarPara) voar({ ...estado.voltarPara, duration: 1.0 });
      else cena.camera.cancelFlight();
    }
    return false;
  }
  estado.aberto = false;
  pausar(false);
  mostrarGuia(null);
  const painel = el("rua");
  painel.classList.remove("aberto");
  // Sem o iframe, o Street View para de gastar memoria e placa de video na hora.
  el("rua-corpo").innerHTML = "";
  setTimeout(() => { if (!estado.aberto) painel.hidden = true; }, 240);
  if (voltar && estado.voltarPara) {
    voar({ ...estado.voltarPara, duration: 1.3, easingFunction: C.EasingFunction.QUADRATIC_IN_OUT });
  }
  return true;
}

/** O cartao do lugar que o guia esta explicando. */
export function mostrarGuia(g) {
  const c = el("rua-guia");
  if (!g || !g.titulo) {
    c.hidden = true;
    return;
  }
  c.innerHTML = `${g.foto ? `<img alt="" src="${String(g.foto).replace(/"/g, "")}" onerror="this.remove()">` : ""}
    <div><small></small><b></b></div>`;
  c.querySelector("small").textContent = g.lado || "";
  c.querySelector("b").textContent = g.titulo;
  c.hidden = false;
}

export function marcarPasseio(ativo) {
  el("rua-parar").hidden = !ativo;
  el("rua-dica").hidden = !!ativo || estado.aba !== "street";
  if (!ativo) mostrarGuia(null);
}

export function preparar(aoAbrirFora) {
  abrirFora = aoAbrirFora;
  el("rua-voltar").addEventListener("click", () => fechar());
  el("rua-fora").addEventListener("click", () => {
    if (estado.lugar) abrirFora?.(urlFora(estado.lugar, estado.aba));
  });
  document.querySelectorAll("#rua-abas button").forEach((b) => {
    b.addEventListener("click", () => mostrarAba(b.dataset.aba));
  });
}
