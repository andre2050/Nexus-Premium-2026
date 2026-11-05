// Medir distancia: dois pontos, o arco entre eles e os km, como no fim do video.

import { cena, voarParaPonto } from "./cena.js";
import { km, numero, t, escapar } from "./textos.js";

const C = window.Cesium;

export const medida = { ativo: false, a: null, b: null, metros: 0 };

let linhas = null;
let pontos = null;
let nomes = null;
let aoMudar = null;

export function preparar(callback) {
  aoMudar = callback;
  linhas = new C.PolylineCollection();
  pontos = new C.PointPrimitiveCollection();
  nomes = new C.LabelCollection({ scene: cena.scene });
  cena.scene.primitives.add(linhas);
  cena.scene.primitives.add(pontos);
  cena.scene.primitives.add(nomes);
}

function apagarDesenho() {
  linhas.removeAll();
  pontos.removeAll();
  nomes.removeAll();
  cena.scene.requestRender();
}

export function iniciar(pontoInicial = null) {
  limpar(false);
  medida.ativo = true;
  if (pontoInicial) clicar(pontoInicial);
  aoMudar?.();
}

export function cancelar() {
  medida.ativo = false;
  aoMudar?.();
}

export function limpar(avisar = true) {
  medida.ativo = false;
  medida.a = null;
  medida.b = null;
  medida.metros = 0;
  apagarDesenho();
  if (avisar) aoMudar?.();
}

function marcar(p) {
  const pos = C.Cartesian3.fromDegrees(p.lon, p.lat, 200);
  pontos.add({
    position: pos,
    pixelSize: 11,
    color: C.Color.fromCssColorString("#ffcc00"),
    outlineColor: C.Color.fromCssColorString("#00121c"),
    outlineWidth: 2,
    disableDepthTestDistance: 0,
  });
  if (p.nome) {
    nomes.add({
      position: pos,
      text: p.nome,
      font: '600 30px "Bahnschrift", "Segoe UI", Arial, sans-serif',
      scale: 0.5,
      style: C.LabelStyle.FILL_AND_OUTLINE,
      outlineWidth: 5,
      outlineColor: C.Color.fromCssColorString("#00121c").withAlpha(0.95),
      fillColor: C.Color.fromCssColorString("#ffe680"),
      verticalOrigin: C.VerticalOrigin.BOTTOM,
      pixelOffset: new C.Cartesian2(0, -11),
    });
  }
}

/** Devolve true quando fechou os dois pontos. */
export function clicar(p) {
  if (!medida.a || medida.b) {
    apagarDesenho();
    medida.a = p;
    medida.b = null;
    marcar(p);
    cena.scene.requestRender();
    aoMudar?.();
    return false;
  }
  medida.b = p;
  medida.ativo = false;
  desenhar(medida.a, medida.b);
  aoMudar?.();
  return true;
}

/** Mostra direto o arco de A ate B (o JARVIS pedindo por voz). */
export function medirEntre(a, b) {
  limpar(false);
  medida.a = a;
  medida.b = b;
  marcar(a);
  desenhar(a, b);
  aoMudar?.();
}

function desenhar(a, b) {
  const geo = new C.EllipsoidGeodesic(
    C.Cartographic.fromDegrees(a.lon, a.lat),
    C.Cartographic.fromDegrees(b.lon, b.lat),
  );
  medida.metros = geo.surfaceDistance;
  const passos = Math.max(24, Math.min(180, Math.ceil(geo.surfaceDistance / 80000)));
  const alto = Math.min(1.9e6, geo.surfaceDistance * 0.16);
  const pos = [];
  const carto = new C.Cartographic();
  for (let i = 0; i <= passos; i++) {
    const f = i / passos;
    geo.interpolateUsingFraction(f, carto);
    pos.push(C.Cartesian3.fromRadians(carto.longitude, carto.latitude, 200 + alto * Math.sin(Math.PI * f)));
  }
  linhas.add({
    positions: pos,
    width: 8,
    material: C.Material.fromType("PolylineGlow", {
      color: C.Color.fromCssColorString("#ffcc00"),
      glowPower: 0.2,
      taperPower: 1.0,
    }),
  });
  marcar(b);
  geo.interpolateUsingFraction(0.5, carto);
  const meio = { lat: C.Math.toDegrees(carto.latitude), lon: C.Math.toDegrees(carto.longitude) };
  nomes.add({
    position: C.Cartesian3.fromRadians(carto.longitude, carto.latitude, 200 + alto),
    text: km(geo.surfaceDistance),
    font: '700 34px "Bahnschrift", "Segoe UI", Arial, sans-serif',
    scale: 0.5,
    style: C.LabelStyle.FILL_AND_OUTLINE,
    outlineWidth: 6,
    outlineColor: C.Color.fromCssColorString("#00121c").withAlpha(0.95),
    fillColor: C.Color.WHITE,
    verticalOrigin: C.VerticalOrigin.BOTTOM,
    pixelOffset: new C.Cartesian2(0, -8),
    disableDepthTestDistance: Number.POSITIVE_INFINITY,
  });
  cena.scene.requestRender();
  const h = C.Math.clamp(geo.surfaceDistance * 1.45, 6000, 1.85e7);
  voarParaPonto(meio.lat, meio.lon, h, 2.0);
}

export function textoResultado() {
  if (!medida.a || !medida.b) return "";
  const horas = medida.metros / 1000 / 850;
  let voo = "";
  if (medida.metros > 150000) {
    const h = Math.floor(horas);
    const m = Math.round((horas - h) * 60);
    voo = ` · ≈ ${h ? `${numero(h)}h${m ? String(m).padStart(2, "0") : ""}` : `${m} min`} ${t("voo")}`;
  }
  const nomeA = medida.a.nome || "A";
  const nomeB = medida.b.nome || "B";
  return `<b>${escapar(nomeA)}</b> → <b>${escapar(nomeB)}</b> · <b class="ouro">${km(medida.metros)}</b>${voo}`;
}
