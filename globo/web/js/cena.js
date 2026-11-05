// A cena 3D: a Terra, as camadas de imagem, a luz do sol, a aurora e a camera.
//
// Baseado no que aparece no video (Earth View do Mark 57), mas feito do zero com
// o CesiumJS: o codigo daquele projeto nao e publico e o dos anteriores proibe uso
// comercial (CC BY-NC).
//
// PENSADO PARA PC FRACO. O ciclo de desenho inteiro DORME quando nada muda (ver
// "o sono"): parado, o globo fica em ~0% de processador e de placa de video. So' o
// que a placa de cada PC aguenta e' ligado (ver `medirPlaca` e `criar`).

const C = window.Cesium;

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const RELEVO_URL = "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer";
const RAIO = 6378137;

export const cena = {
  widget: null, scene: null, camera: null, globe: null, canvas: null,
  modo: "satelite",
  noite: true,
  nomes: true,
  bordas: true,
  relevo: false,
  girar: false,
  nivel: "forte",        // forte | medio | leve: o que a placa de video aguenta
  placa: "",
  cor: "#00d4ff",
  aoAjustarAltura: [],   // funcoes(altura) chamadas quando a camera muda
  aoParar: [],           // camera parou de andar
  aoMover: [],           // camera andando
  emMovimento: false,
  emVoo: false,
  semInternet: false,
  aoMudarRede: null,
};

const camadas = {};

// ── o que a placa aguenta ────────────────────────────────────────────────
function medirPlaca() {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl2");
    if (!gl) return { suporta: false, placa: "" };
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    const placa = ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : "";
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return { suporta: true, placa };
  } catch {
    return { suporta: false, placa: "" };
  }
}

function classificar(placa) {
  const r = placa.toLowerCase();
  if (/swiftshader|llvmpipe|softpipe|basic render|warp|virgl|vmware|virtualbox|parallels/.test(r)) return "leve";
  if (/gma |hd graphics( [2-6]\d{2,3})?\b/.test(r) && !/uhd|iris/.test(r)) return "leve";
  if (/intel|uhd|iris|radeon\(tm\) (r\d|vega)|radeon graphics|vega \d|mali|adreno|gt \d{3}\b|gtx? [4-7]\d{2}\b|radeon hd|radeon r[5-7]/.test(r)) return "medio";
  return "forte";
}

export function temWebgl() {
  return medirPlaca().suporta;
}

// ── suavizacao ───────────────────────────────────────────────────────────
function faixa(h, alto, baixo) {
  if (h >= alto) return 0;
  if (h <= baixo) return 1;
  const t = (alto - h) / (alto - baixo);
  return t * t * (3 - 2 * t);
}

// ── camadas ──────────────────────────────────────────────────────────────
function piramide(pasta, credito) {
  return new C.UrlTemplateImageryProvider({
    url: `img/${pasta}/{z}/{x}/{y}.jpg`,
    tilingScheme: new C.GeographicTilingScheme(),
    tileWidth: 512,
    tileHeight: 512,
    minimumLevel: 0,
    maximumLevel: cena.nivel === "leve" ? 2 : 3,
    credit: new C.Credit(credito),
    enablePickFeatures: false,
    hasAlphaChannel: false,
  });
}

// Ordem da pilha, da de baixo para a de cima. Cada servico online custa dois pedidos
// so' para abrir: ele nasce quando for aparecer de verdade, nao na abertura.
const ORDEM = ["dia", "noite", "aurora", "satelite", "ruas", "escuro", "escuroNomes", "vias", "lugares", "cobertura"];
const SERVICOS = {
  satelite: ["World_Imagery", { nightAlpha: 0 }],
  ruas: ["World_Street_Map", {}],
  escuro: ["Canvas/World_Dark_Gray_Base", {}],
  escuroNomes: ["Canvas/World_Dark_Gray_Reference", {}],
  vias: ["Reference/World_Transportation", {}],
  lugares: ["Reference/World_Boundaries_and_Places", {}],
};

function posicaoNaPilha(chave) {
  return ORDEM.slice(0, ORDEM.indexOf(chave)).filter((k) => camadas[k]).length;
}

function camadaEsri(chave) {
  const [servico, opcoes] = SERVICOS[chave];
  const criar = () => {
    const camada = C.ImageryLayer.fromProviderAsync(
      C.ArcGisMapServerImageryProvider.fromUrl(`${ESRI}/${servico}/MapServer`, { enablePickFeatures: false }),
      { show: false, ...opcoes },
    );
    camada.errorEvent.addEventListener(() => {
      camadas[chave].falhou = true;
      marcarRede(true);
    });
    camada.readyEvent.addEventListener(() => {
      camadas[chave].falhou = false;
      marcarRede(Object.values(camadas).some((c) => c.falhou));
      cena.scene.requestRender();
    });
    return camada;
  };
  const info = { criar, falhou: false, camada: criar() };
  const pos = posicaoNaPilha(chave);
  camadas[chave] = info;
  cena.scene.imageryLayers.add(info.camada, pos);
  return info;
}

function marcarRede(falhou) {
  if (cena.semInternet !== falhou) {
    cena.semInternet = falhou;
    cena.aoMudarRede?.(falhou);
  }
}

/** A internet voltou: refaz, no mesmo lugar da pilha, as camadas que nao subiram. */
function refazerCamadasQueFalharam() {
  for (const info of Object.values(camadas)) {
    if (!info.falhou || !info.criar) continue;
    const L = cena.scene.imageryLayers;
    const pos = L.indexOf(info.camada);
    if (pos < 0) continue;
    const nova = info.criar();
    L.remove(info.camada, true);
    info.camada = nova;
    L.add(nova, pos);
  }
  ajustarCamadas(true);
}

// ── altura da camera -> o que aparece ────────────────────────────────────
let _ultimaAltura = -1;

export function altura() {
  return cena.camera.positionCartographic.height;
}

export function zoomEquivalente() {
  const h = Math.max(altura(), 1);
  const w = cena.canvas.clientWidth || 1600;
  return Math.log2((40075016 * (w / 256)) / (2 * h * Math.tan(cena.camera.frustum.fov / 2)));
}

function alfa(chave, valor, regraShow = true) {
  const mostrar = regraShow && valor > 0.005;
  let info = camadas[chave];
  if (!info) {
    if (!mostrar || !SERVICOS[chave]) return;
    info = camadaEsri(chave);
  }
  const c = info.camada;
  if (c.show !== mostrar) c.show = mostrar;
  if (Math.abs(c.alpha - valor) > 0.002) c.alpha = valor;
}

function ajustarCamadas(forcar = false) {
  const h = altura();
  if (!forcar && Math.abs(h - _ultimaAltura) < Math.max(1, _ultimaAltura * 0.004)) return;
  _ultimaAltura = h;

  const sat = cena.modo === "satelite";
  const map = cena.modo === "mapa";
  const hol = cena.modo === "holograma";

  // O motor apaga no lado escuro quem tem nightAlpha 0, em qualquer altura. Do
  // espaco e' isso que da a noite; de perto a foto tem de aparecer a qualquer hora.
  const perto = faixa(h, 6.5e6, 1.6e6);
  camadas.dia.camada.nightAlpha = perto;
  camadas.noite.camada.nightAlpha = 1 - perto;
  if (camadas.satelite) camadas.satelite.camada.nightAlpha = perto;

  alfa("dia", 1, sat);
  alfa("noite", 1, sat && cena.noite && perto < 0.995);
  // Da viagem do espaco ate a rua, o Blue Marble vira foto de satelite sem emenda.
  alfa("satelite", faixa(h, 6.5e6, 2.6e6), sat);
  alfa("ruas", 1, map);
  alfa("escuro", faixa(h, 3.5e6, 1.4e6), hol);
  alfa("escuroNomes", cena.nomes ? faixa(h, 1.2e6, 3.0e5) : 0, hol);
  alfa("vias", cena.nomes ? faixa(h, 1.1e5, 3.0e4) : 0, sat);
  alfa("lugares", cena.nomes ? faixa(h, 6.0e4, 1.8e4) : 0, sat);

  if (_pontosHolo) {
    _pontosHolo.show = hol && h > 6.5e5;
    _gradeHolo.show = hol && h > 1.5e6;
  }
  // A aurora e' uma imagem so', sem nada animando: nao pesa e nao pisca.
  if (camadas.aurora) {
    const a = camadas.aurora.camada;
    const v = (sat || hol) ? faixa(-h, -1.8e6, -4.5e6) * (hol ? 0.55 : 1) : 0;
    a.show = v > 0.005;
    a.alpha = v;
    // Com a luz do sol ligada o motor deixa a noite com 30%: o brilho devolve o resto.
    a.brightness = sat && cena.noite ? 3.0 : 1.15;
  }
  for (const f of cena.aoAjustarAltura) f(h);
  cena.scene.requestRender();
}

// ── luz ──────────────────────────────────────────────────────────────────
function aplicarLuz() {
  const g = cena.globe;
  const s = cena.scene;
  const sat = cena.modo === "satelite";
  const luz = sat && cena.noite;
  g.enableLighting = luz;
  g.dynamicAtmosphereLighting = luz;
  g.dynamicAtmosphereLightingFromSun = luz;
  // A atmosfera do chao e' calculada pixel a pixel no disco inteiro da Terra: e' o
  // item mais caro de todos, e so' a placa forte fica com ela.
  g.showGroundAtmosphere = cena.modo !== "holograma" && cena.nivel === "forte";
  g.baseColor = cena.modo === "holograma" ? C.Color.fromCssColorString("#031a29") : C.Color.fromCssColorString("#000710");
  s.sun.show = cena.modo !== "holograma" && cena.nivel !== "leve";
  s.moon.show = cena.modo !== "holograma" && cena.nivel === "forte";
  s.requestRender();
}

// ── holograma ────────────────────────────────────────────────────────────
let _pontosHolo = null;
let _gradeHolo = null;
let _criandoHolo = false;

async function criarHolograma() {
  if (_pontosHolo || _criandoHolo) return;
  _criandoHolo = true;
  const cor = C.Color.fromCssColorString(cena.cor);
  const buf = await fetch("dados/holograma.bin").then((r) => r.arrayBuffer());
  const a = new Int16Array(buf);
  const pontos = new C.PointPrimitiveCollection({ blendOption: C.BlendOption.TRANSLUCENT });
  const corPonto = cor.withAlpha(0.85);
  const escala = new C.NearFarScalar(1.5e6, 0.7, 2.0e7, 1.0);
  const pulo = cena.nivel === "leve" ? 4 : 2;      // PC fraco: um ponto sim, um nao
  for (let i = 0; i < a.length; i += pulo) {
    pontos.add({
      position: C.Cartesian3.fromDegrees(a[i] / 150, a[i + 1] / 300),
      pixelSize: cena.nivel === "leve" ? 2.6 : 2.0,
      color: corPonto,
      scaleByDistance: escala,
    });
  }
  const grade = new C.PolylineCollection();
  const matGrade = C.Material.fromType("Color", { color: cor.withAlpha(0.12) });
  for (let lon = -180; lon < 180; lon += 15) {
    const arr = [];
    for (let lat = -90; lat <= 90; lat += 3) arr.push(lon, lat);
    grade.add({ positions: C.Cartesian3.fromDegreesArray(arr), width: 1, material: matGrade });
  }
  for (let lat = -75; lat <= 75; lat += 15) {
    const arr = [];
    for (let lon = -180; lon <= 180; lon += 3) arr.push(lon, lat);
    grade.add({ positions: C.Cartesian3.fromDegreesArray(arr), width: 1, material: matGrade });
  }
  cena.scene.primitives.add(pontos);
  cena.scene.primitives.add(grade);
  _pontosHolo = pontos;
  _gradeHolo = grade;
  ajustarCamadas(true);
}

// ── o que o resto da tela usa ────────────────────────────────────────────
export function definirModo(modo) {
  if (!["satelite", "mapa", "holograma"].includes(modo)) return;
  cena.modo = modo;
  if (modo === "holograma") criarHolograma();
  aplicarLuz();
  ajustarCamadas(true);
}

export function definirNoite(ligado) {
  cena.noite = !!ligado;
  aplicarLuz();
  ajustarCamadas(true);
}

export function definirNomes(ligado) {
  cena.nomes = !!ligado;
  ajustarCamadas(true);
}

let _provedorRelevo = null;

export async function definirRelevo(ligado) {
  cena.relevo = !!ligado;
  if (!ligado) {
    cena.scene.terrainProvider = new C.EllipsoidTerrainProvider();
    cena.scene.requestRender();
    return false;
  }
  try {
    _provedorRelevo ||= await C.ArcGISTiledElevationTerrainProvider.fromUrl(RELEVO_URL);
    if (cena.relevo) cena.scene.terrainProvider = _provedorRelevo;
    cena.scene.requestRender();
    return cena.relevo;
  } catch (exc) {
    console.warn("relevo indisponivel", exc);
    cena.relevo = false;
    return false;
  }
}

let _ultimoToque = 0;
let _ligouGiro = 0;

/** As linhas azuis do Google: onde tem Street View. So' aparecem com o bonequinho ligado. */
export function definirCobertura(ligado) {
  if (ligado && !camadas.cobertura) {
    const camada = new C.ImageryLayer(new C.UrlTemplateImageryProvider({
      url: "https://mts{s}.googleapis.com/vt?hl=en&lyrs=svv%7Ccb_client:apiv3&style=40,18&x={x}&y={y}&z={z}",
      subdomains: "0123",
      minimumLevel: 2,
      maximumLevel: 18,
      enablePickFeatures: false,
      hasAlphaChannel: true,
    }));
    const pos = posicaoNaPilha("cobertura");
    camadas.cobertura = { camada };
    cena.scene.imageryLayers.add(camada, pos);
  }
  if (camadas.cobertura) camadas.cobertura.camada.show = !!ligado;
  cena.scene.requestRender();
}

export function marcarToque() {
  const antes = _ultimoToque;
  _ultimoToque = performance.now();
  // O giro volta sozinho 6 s depois do ultimo toque.
  if (cena.girar && _ultimoToque - antes > 1000) setTimeout(() => acordar(200), 6100);
}

export function definirGiro(ligado) {
  cena.girar = !!ligado;
  _ligouGiro = performance.now();
  _ultimoToque = 0;
  acordar(300);
}

/** Ponto do globo embaixo do mouse, ou null se for o espaco. */
export function pontoDaTela(x, y, preciso = false) {
  const janela = new C.Cartesian2(x, y);
  let p;
  if (preciso && cena.relevo) {
    const raio = cena.camera.getPickRay(janela);
    if (raio) p = cena.globe.pick(raio, cena.scene);
  }
  p ||= cena.camera.pickEllipsoid(janela, cena.globe.ellipsoid);
  if (!p) return null;
  const c = C.Cartographic.fromCartesian(p);
  if (!c) return null;
  return { lat: C.Math.toDegrees(c.latitude), lon: C.Math.toDegrees(c.longitude), altura: c.height, cart: p };
}

function larguraOcupada() {
  const f = document.getElementById("ficha");
  return f && !f.hidden ? f.offsetWidth + 24 : 20;
}

export function voar(opcoes) {
  acordar(1000);
  return new Promise((ok) => {
    cena.camera.cancelFlight();
    cena.camera.flyTo({
      ...opcoes,
      complete: () => { acordar(700); ok(true); },
      cancel: () => { acordar(300); ok(false); },
    });
  });
}

/** Enquadra o retangulo na parte da tela que os paineis deixam livre. */
export function voarParaRetangulo(w, s, e, n, duracao = 2.2) {
  const L = cena.canvas.clientWidth;
  const A = cena.canvas.clientHeight;
  const esq = 76, dir = larguraOcupada(), topo = 76, baixo = 44;
  const largura = Math.max(((e - w) + 360) % 360 || (e - w), 0.5);
  const alturaG = Math.max(n - s, 0.4);
  const k = Math.max(largura / (L - esq - dir), alturaG / (A - topo - baixo));
  const cx = w + largura / 2 + ((dir - esq) / 2) * k;
  const cy = (s + n) / 2 + ((baixo - topo) / 2) * k;
  const meiaL = Math.min(179, (L / 2) * k);
  const meiaA = (A / 2) * k;
  let oeste = cx - meiaL;
  let leste = cx + meiaL;
  if (oeste < -180) oeste += 360;
  if (leste > 180) leste -= 360;
  const ret = C.Rectangle.fromDegrees(oeste, Math.max(-89, cy - meiaA), leste, Math.min(89, cy + meiaA));
  return voar({ destination: ret, duration: duracao, easingFunction: C.EasingFunction.QUADRATIC_IN_OUT });
}

/** Vai ate o ponto olhando de cima, deixando-o no meio da parte livre da tela. */
export function voarParaPonto(lat, lon, h, duracao = 2.2) {
  const L = cena.canvas.clientWidth;
  const dir = larguraOcupada();
  const metrosPorPixel = (2 * h * Math.tan(cena.camera.frustum.fov / 2)) / L;
  const desvio = ((dir - 76) / 2) * metrosPorPixel;
  const dLon = desvio / (111320 * Math.max(0.15, Math.cos(C.Math.toRadians(lat))));
  return voar({
    destination: C.Cartesian3.fromDegrees(lon + dLon, lat, h),
    orientation: { heading: 0, pitch: -C.Math.PI_OVER_TWO, roll: 0 },
    duration: duracao,
    easingFunction: C.EasingFunction.QUADRATIC_IN_OUT,
  });
}

export function terraInteira(lon = null, duracao = 2.2, lat = null) {
  const c = cena.camera.positionCartographic;
  const lonAqui = lon ?? C.Math.toDegrees(c.longitude);
  const latAqui = lat ?? Math.max(-25, Math.min(25, C.Math.toDegrees(c.latitude)));
  return voar({
    destination: C.Cartesian3.fromDegrees(lonAqui, latAqui, 1.75e7),
    orientation: { heading: 0, pitch: -C.Math.PI_OVER_TWO, roll: 0 },
    duration: duracao,
    easingFunction: C.EasingFunction.QUADRATIC_IN_OUT,
  });
}

export function zoomDeBotao(fator) {
  const c = cena.camera;
  const pc = c.positionCartographic;
  const h = C.Math.clamp(pc.height * fator, 60, 3.2e7);
  voar({
    destination: C.Cartesian3.fromRadians(pc.longitude, pc.latitude, h),
    orientation: { heading: c.heading, pitch: c.pitch, roll: 0 },
    duration: 0.45,
    easingFunction: C.EasingFunction.QUADRATIC_OUT,
  });
}

/** Anda a camera para um lado: um quarto do que esta na tela. */
export function moverPara(direcao) {
  const c = cena.camera;
  const pc = c.positionCartographic;
  const graus = C.Math.clamp((pc.height / 111320) * 0.5, 0.002, 40);
  let lat = C.Math.toDegrees(pc.latitude);
  let lon = C.Math.toDegrees(pc.longitude);
  if (direcao === "norte") lat = Math.min(85, lat + graus);
  if (direcao === "sul") lat = Math.max(-85, lat - graus);
  if (direcao === "leste") lon += graus / Math.max(0.2, Math.cos(pc.latitude));
  if (direcao === "oeste") lon -= graus / Math.max(0.2, Math.cos(pc.latitude));
  voar({
    destination: C.Cartesian3.fromDegrees(lon, lat, pc.height),
    orientation: { heading: c.heading, pitch: c.pitch, roll: 0 },
    duration: 0.8,
    easingFunction: C.EasingFunction.QUADRATIC_IN_OUT,
  });
}

/** O ponto que esta no meio da tela, para girar ou inclinar em volta dele. */
function pontoCentral() {
  const L = cena.canvas.clientWidth;
  const A = cena.canvas.clientHeight;
  const p = pontoDaTela(L / 2, A / 2);
  return p ? p.cart : null;
}

export function olharParaONorte() {
  const c = cena.camera;
  const alvo = pontoCentral();
  if (!alvo) {
    voar({ destination: c.positionWC.clone(), orientation: { heading: 0, pitch: -C.Math.PI_OVER_TWO, roll: 0 }, duration: 0.8 });
    return;
  }
  const dist = C.Cartesian3.distance(c.positionWC, alvo);
  c.cancelFlight();
  acordar(1600);
  c.flyToBoundingSphere(new C.BoundingSphere(alvo, 0), {
    offset: new C.HeadingPitchRange(0, -C.Math.PI_OVER_TWO, dist),
    duration: 0.9,
    easingFunction: C.EasingFunction.QUADRATIC_IN_OUT,
  });
}

export function alternarInclinacao() {
  const c = cena.camera;
  const alvo = pontoCentral();
  if (!alvo) return;
  const dist = C.Cartesian3.distance(c.positionWC, alvo);
  const deitado = c.pitch > C.Math.toRadians(-75);
  c.cancelFlight();
  acordar(1800);
  c.flyToBoundingSphere(new C.BoundingSphere(alvo, 0), {
    offset: new C.HeadingPitchRange(c.heading, deitado ? -C.Math.PI_OVER_TWO : C.Math.toRadians(-32), dist),
    duration: 1.1,
    easingFunction: C.EasingFunction.QUADRATIC_IN_OUT,
  });
}

/**
 * Soltou a Terra torta? O norte volta para cima sozinho, bem de leve. So' de longe e
 * olhando reto para baixo (de perto, girar o mapa pode ser de proposito), e nunca
 * perto dos polos, onde "norte para cima" nao quer dizer nada.
 */
function endireitar() {
  const c = cena.camera;
  if (_apertado || cena.emVoo) return;
  const pc = c.positionCartographic;
  if (pc.height < 3.0e5 || c.pitch > C.Math.toRadians(-75)) return;
  if (Math.abs(C.Math.toDegrees(pc.latitude)) > 62) return;
  const torto = Math.min(c.heading, C.Math.TWO_PI - c.heading);
  if (torto < C.Math.toRadians(1)) return;
  voar({
    destination: c.positionWC.clone(),
    orientation: { heading: 0, pitch: -C.Math.PI_OVER_TWO, roll: 0 },
    duration: 0.55,
    easingFunction: C.EasingFunction.QUADRATIC_IN_OUT,
  });
}

// ── halo e aro em volta da Terra ─────────────────────────────────────────
let _halo = null;
let _aro = null;
let _haloAntes = "";
let _apertado = false;
let _opacidadeAntes = "";
const _centroTela = new C.Cartesian2();

function atualizarHalo() {
  if (!_halo) return;
  const c = cena.camera;
  const d = C.Cartesian3.magnitude(c.positionWC);
  const h = d - RAIO;
  const ver = h > 3.2e6 && c.pitch < C.Math.toRadians(-80);
  let opacidade = 0;
  if (ver) {
    opacidade = faixa(-h, -3.2e6, -7.0e6);
    const fr = c.frustum;
    const A = cena.canvas.clientHeight;
    const raioPx = (Math.tan(Math.asin(Math.min(0.999, RAIO / d))) / Math.tan(fr.fovy / 2)) * (A / 2);
    const centro = C.SceneTransforms.worldToWindowCoordinates(cena.scene, C.Cartesian3.ZERO, _centroTela);
    if (!centro) {
      opacidade = 0;
    } else {
      const escala = raioPx / 500;
      const t = `translate(${centro.x.toFixed(1)}px, ${centro.y.toFixed(1)}px) scale(${escala.toFixed(4)})`;
      if (t !== _haloAntes) {
        _haloAntes = t;
        _halo.style.transform = t;
        // O aro acompanha a Terra girando: anima junto com ela, nunca sozinho.
        const giro = C.Math.toDegrees(c.positionCartographic.longitude).toFixed(1);
        _aro.style.transform = `${t} rotate(${giro}deg)`;
      }
    }
  }
  const forca = cena.modo === "holograma" ? 1 : (cena.modo === "mapa" ? 0.55 : 0.8);
  const o = (opacidade * forca).toFixed(3);
  if (o !== _opacidadeAntes) {
    _opacidadeAntes = o;
    _halo.style.opacity = o;
    _aro.style.opacity = (opacidade * (cena.modo === "mapa" ? 0.45 : 0.75)).toFixed(3);
  }
}

// ── o sono ───────────────────────────────────────────────────────────────
// O laco normal do motor roda 60 vezes por segundo para sempre, mesmo sem desenhar
// nada. Aqui ele so' roda enquanto houver motivo: mouse, voo, inercia, imagem chegando.
let _acordadoAte = 0;
let _rodando = false;
let _ultimoQuadro = 0;
let _ultimoProgresso = 0;

/** Street View na frente: o globo esta coberto, entao nao gasta nada. */
export function pausar(sim) {
  cena.pausado = !!sim;
  if (!sim) acordar(800);
}

export function acordar(ms = 120) {
  if (cena.pausado) return;
  const agora = performance.now();
  if (agora + ms > _acordadoAte) _acordadoAte = agora + ms;
  if (!_rodando) {
    _rodando = true;
    requestAnimationFrame(quadro);
  }
}

function giroPode(agora) {
  // O giro nao fica para sempre: 3 minutos sem ninguem mexer e ele para, para nao
  // deixar a placa trabalhando com o globo esquecido na tela.
  return cena.camera.positionCartographic.height > 5.0e6
    && document.hasFocus()
    && !document.hidden
    && agora - _ultimoToque > 6000
    && agora - Math.max(_ultimoToque, _ligouGiro) < 180000;
}

function temMotivo(agora) {
  if (agora < _acordadoAte || cena.emVoo || cena.emMovimento) return true;
  if (cena.girar && giroPode(agora)) return true;
  // Imagem ainda chegando. Sem internet ela nunca chega: desiste depois de um tempo.
  if (!cena.globe.tilesLoaded && agora - _ultimoProgresso < 6000) return true;
  return false;
}

function quadro(agora) {
  if (document.hidden || cena.pausado) {   // minimizada ou coberta: dorme ate voltar
    _rodando = false;
    return;
  }
  // PC fraco trabalha a 30 quadros: metade do calor, e o movimento continua suave.
  if (cena.nivel === "leve" && agora - _ultimoQuadro < 30) {
    requestAnimationFrame(quadro);
    return;
  }
  const dt = Math.min(0.1, (agora - _ultimoQuadro) / 1000);
  _ultimoQuadro = agora;

  if (cena.girar && !cena.emVoo && giroPode(agora)) {
    cena.camera.rotate(C.Cartesian3.UNIT_Z, -C.Math.toRadians(1.3) * dt);
  }
  const w = cena.widget;
  w.resize();
  w.render();

  if (temMotivo(performance.now())) {
    requestAnimationFrame(quadro);
  } else {
    _rodando = false;
  }
}

// ── medidor: se a placa nao esta dando conta, a imagem baixa sozinha ─────
let _tAnterior = 0;
let _somaMs = 0;
let _quadros = 0;
let _quedas = 0;
let _ruins = 0;
let _inicio = 0;

function medirDesempenho() {
  const agora = performance.now();
  const dt = agora - _tAnterior;
  _tAnterior = agora;
  // So' vale em voo, quando cada quadro e' desenhado. Fora disso os quadros so' saem
  // quando chega imagem da internet, e 4 "fps" assim nao querem dizer nada: era isso
  // que baixava a qualidade a toa ate numa RTX 3080.
  if (!cena.emVoo || cena.pausado || document.hidden || agora - _inicio < 15000 || dt > 600) return;
  _somaMs += dt;
  if (++_quadros < 50) return;
  const fps = (1000 * _quadros) / _somaMs;
  _quadros = 0;
  _somaMs = 0;
  cena.fpsAndando = fps;
  // Duas medidas ruins seguidas: uma so' pode ser imagem chegando da internet.
  _ruins = fps < 22 ? _ruins + 1 : 0;
  if (_ruins >= 2 && _quedas < 3) {
    _ruins = 0;
    _quedas++;
    const w = cena.widget;
    w.resolutionScale = Math.max(0.6, w.resolutionScale * 0.85);
    if (cena.globe.maximumScreenSpaceError < 4) cena.globe.maximumScreenSpaceError += 1;
    cena.aoBaixarQualidade?.(fps, w.resolutionScale);
  }
}

// ── cria tudo ────────────────────────────────────────────────────────────
export function criar(cor) {
  const { placa } = medirPlaca();
  cena.placa = placa;
  cena.nivel = new URLSearchParams(location.search).get("nivel") || classificar(placa);
  cena.cor = cor || "#00d4ff";
  document.body.dataset.nivel = cena.nivel;

  C.Ion.defaultAccessToken = "";
  C.RequestScheduler.requestsByServer["server.arcgisonline.com:443"] = cena.nivel === "leve" ? 8 : 12;
  C.RequestScheduler.requestsByServer["elevation3d.arcgis.com:443"] = 8;

  const forte = cena.nivel === "forte";
  const widget = new C.CesiumWidget("palco", {
    baseLayer: false,
    terrainProvider: new C.EllipsoidTerrainProvider(),
    scene3DOnly: true,
    shouldAnimate: true,
    requestRenderMode: true,
    maximumRenderTimeChange: 45,
    orderIndependentTranslucency: false,
    showRenderLoopErrors: false,
    useDefaultRenderLoop: false,        // quem manda no desenho e' o `quadro`
    useBrowserRecommendedResolution: true,
    msaaSamples: forte ? 2 : 1,
    creditContainer: "creditos",
    contextOptions: { webgl: { alpha: false, powerPreference: "high-performance" } },
  });
  const scene = widget.scene;
  const globe = scene.globe;
  const camera = scene.camera;
  cena.widget = widget;
  cena.scene = scene;
  cena.globe = globe;
  cena.camera = camera;
  cena.canvas = scene.canvas;
  scene.rethrowRenderErrors = false;

  const requestRender = scene.requestRender.bind(scene);
  scene.requestRender = () => {
    requestRender();
    acordar();
  };
  scene.cameraEventWaitTime = 250;

  // O QUE CADA PLACA AGUENTA. Cada item foi escolhido pelo que custa na tela inteira.
  if (cena.nivel === "leve") {
    widget.resolutionScale = 0.75;
    globe.maximumScreenSpaceError = 4;
    globe.tileCacheSize = 25;
    globe.preloadAncestors = false;
    scene.skyBox.show = false;
    scene.sunBloom = false;
  } else if (cena.nivel === "medio") {
    globe.maximumScreenSpaceError = 2.5;
    globe.tileCacheSize = 60;
    scene.sunBloom = false;
  } else {
    globe.tileCacheSize = 150;
  }

  // ── a Terra ──────────────────────────────────────────────────────────
  globe.baseColor = C.Color.fromCssColorString("#000710");
  globe.atmosphereLightIntensity = 12;
  globe.lightingFadeOutDistance = 1.6e6;
  globe.lightingFadeInDistance = 6.5e6;
  // Valores altos de proposito. Com o padrao, de longe a "atmosfera do chao" troca
  // a cor do lado escuro pela dela, quase preta, e as luzes das cidades somem.
  globe.nightFadeOutDistance = 6.0e7;
  globe.nightFadeInDistance = 7.0e7;
  globe.showWaterEffect = false;
  globe.depthTestAgainstTerrain = false;
  globe.preloadSiblings = false;

  scene.highDynamicRange = false;
  scene.fog.enabled = true;
  scene.fog.density = 1.0e-4;
  scene.skyAtmosphere.show = true;
  scene.skyAtmosphere.atmosphereLightIntensity = 28;
  scene.skyAtmosphere.saturationShift = 0.12;
  scene.skyAtmosphere.brightnessShift = 0.06;

  // ── camadas fixas (as da internet nascem quando forem aparecer) ──────
  const L = scene.imageryLayers;
  // Sem a atmosfera, a Terra de dia fica um pouco mais apagada: as placas sem ela
  // compensam no brilho e na saturacao.
  const dia = new C.ImageryLayer(piramide("dia", "NASA Blue Marble"), {
    dayAlpha: 1, nightAlpha: 0, brightness: forte ? 1.08 : 1.18, saturation: forte ? 1.12 : 1.2, contrast: 1.06,
  });
  // O motor deixa o lado escuro com 30% da luz: o brilho aqui devolve o que falta.
  const noite = new C.ImageryLayer(piramide("noite", "NASA Black Marble"), {
    dayAlpha: 0, nightAlpha: 1, brightness: 3.4, gamma: 0.62, saturation: 1.2, show: false,
  });
  L.add(dia);
  L.add(noite);
  camadas.dia = { camada: dia };
  camadas.noite = { camada: noite };
  window.addEventListener("online", () => setTimeout(refazerCamadasQueFalharam, 1500));
  setInterval(() => { if (cena.semInternet && navigator.onLine) refazerCamadasQueFalharam(); }, 45000);

  // ── controles ────────────────────────────────────────────────────────
  const ctl = scene.screenSpaceCameraController;
  ctl.minimumZoomDistance = 40;
  ctl.maximumZoomDistance = 3.2e7;
  ctl.enableCollisionDetection = true;
  ctl.inertiaSpin = 0.88;
  ctl.inertiaTranslate = 0.88;
  ctl.inertiaZoom = 0.72;
  camera.percentageChanged = 0.015;
  // SEM EIXO FIXO. Com ele a Terra gira em volta do eixo dos polos, e perto do polo
  // o mesmo movimento do mouse gira para um lado na metade de cima da tela e para o
  // outro na de baixo: era o "inverte os lados". Livre, o ponto agarrado acompanha o
  // mouse em qualquer lugar. Quem endireita o norte depois e' o `endireitar`.
  camera.constrainedAxis = undefined;
  camera.frustum.fov = C.Math.toRadians(50);

  // ── eventos da camera ────────────────────────────────────────────────
  camera.moveStart.addEventListener(() => { cena.emMovimento = true; acordar(); });
  camera.moveEnd.addEventListener(() => {
    cena.emMovimento = false;
    for (const f of cena.aoParar) f();
    endireitar();
  });
  camera.changed.addEventListener(() => { for (const f of cena.aoMover) f(); });
  scene.preUpdate.addEventListener(() => {
    ajustarCamadas();
    cena.emVoo = camera._currentFlight !== undefined && camera._currentFlight !== null;
  });
  scene.postRender.addEventListener(() => {
    atualizarHalo();
    medirDesempenho();
  });
  globe.tileLoadProgressEvent.addEventListener(() => { _ultimoProgresso = performance.now(); });

  _halo = document.getElementById("halo");
  _aro = document.getElementById("aro");

  aplicarLuz();
  if (cena.nivel !== "leve") {
    const aurora = new C.ImageryLayer(new C.SingleTileImageryProvider({
      url: "img/aurora.png", tileWidth: 2048, tileHeight: 1024,
    }), { dayAlpha: 0.2, nightAlpha: 1, show: false });
    camadas.aurora = { camada: aurora };
    L.add(aurora);
  }
  ajustarCamadas(true);

  _ultimoQuadro = performance.now();
  _inicio = _ultimoQuadro;
  _ultimoProgresso = _ultimoQuadro;

  // Tudo que acorda o desenho vindo de fora dele.
  const tela = cena.canvas;
  const longo = () => acordar(2600);     // cobre a inercia depois de soltar o mouse
  tela.addEventListener("pointerdown", () => { _apertado = true; longo(); }, { passive: true });
  window.addEventListener("pointerup", () => { _apertado = false; longo(); }, { passive: true });
  tela.addEventListener("wheel", longo, { passive: true });
  tela.addEventListener("pointermove", (e) => { if (e.buttons) acordar(800); }, { passive: true });
  window.addEventListener("resize", () => acordar(500));
  window.addEventListener("focus", () => acordar(500));
  document.addEventListener("visibilitychange", () => { if (!document.hidden) acordar(800); });
  // O sol anda: um desenho por minuto mantem a linha do dia e da noite no lugar.
  setInterval(() => { if (!document.hidden) cena.scene.requestRender(); }, 60000);
  // Imagem pedida que chega depois do motor dormir (internet lenta).
  C.RequestScheduler.requestCompletedEvent.addEventListener(() => {
    _ultimoProgresso = performance.now();
    acordar(300);
  });
  setInterval(() => { if (!document.hidden && !cena.globe.tilesLoaded) acordar(300); }, 4000);
  acordar(1500);
  return cena;
}
