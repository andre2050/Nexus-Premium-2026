// Os nomes em cima do globo. Como num mapa de verdade: aparece o que cabe, os mais
// importantes primeiro, e nenhum nome em cima do outro.
//
// SO' RECALCULA COM A CAMERA PARADA. Andando, cada nome ja desenhado fica grudado no
// lugar dele: refazer a lista no meio do movimento fazia os nomes piscarem e custava
// processador bem na hora em que a placa mais precisa de folga.

import { cena, altura, zoomEquivalente } from "./cena.js";
import { D, nomeCidade } from "./dados.js";
import { idioma } from "./textos.js";

const C = window.Cesium;

const RAIO2 = 6378137 * 6378137 * 0.985;
const FONTE = '"Bahnschrift", "Segoe UI", "DejaVu Sans", Arial, sans-serif';

let MAX_PAISES = 45;
let MAX_CIDADES = 70;

let colNomes = null;
let colPontos = null;
const vagasPais = [];         // { nome, obj } com a fonte certa desde o inicio
const vagasCidade = [];       // trocar a fonte de um nome refaz todas as letras dele
let ativos = [];
let ligado = true;
let prioridade = null;
let paisesOrdem = [];
let capitais = [];
let estaduais = [];
const _tela = new C.Cartesian2();

const CORES = {
  pais: C.Color.fromCssColorString("#dff7ff"),
  capital: C.Color.fromCssColorString("#ffffff"),
  cidade: C.Color.fromCssColorString("#d9f3ff"),
  contorno: C.Color.fromCssColorString("#00121c").withAlpha(0.92),
  ponto: C.Color.fromCssColorString("#ffffff"),
};
const _deslocaForte = new C.Cartesian2(9, 0);
const _deslocaFraco = new C.Cartesian2(7, 0);

export function construir() {
  if (cena.nivel === "leve") {
    MAX_PAISES = 26;
    MAX_CIDADES = 34;
  }
  colNomes = new C.LabelCollection({ scene: cena.scene });
  colPontos = new C.PointPrimitiveCollection();
  const destaque = C.Color.fromCssColorString(cena.cor);
  for (let i = 0; i < MAX_PAISES; i++) {
    vagasPais.push({
      obj: null,
      nome: colNomes.add({
        show: false,
        text: " ",
        font: `600 26px ${FONTE}`,
        scale: 0.5,
        style: C.LabelStyle.FILL_AND_OUTLINE,
        outlineWidth: 5,
        outlineColor: CORES.contorno,
        fillColor: CORES.pais,
        horizontalOrigin: C.HorizontalOrigin.CENTER,
        verticalOrigin: C.VerticalOrigin.CENTER,
        position: C.Cartesian3.ZERO,
      }),
    });
  }
  for (let i = 0; i < MAX_CIDADES; i++) {
    vagasCidade.push({
      obj: null,
      nome: colNomes.add({
        show: false,
        text: " ",
        font: `500 28px ${FONTE}`,
        scale: 0.48,
        style: C.LabelStyle.FILL_AND_OUTLINE,
        outlineWidth: 5,
        outlineColor: CORES.contorno,
        fillColor: CORES.cidade,
        horizontalOrigin: C.HorizontalOrigin.LEFT,
        verticalOrigin: C.VerticalOrigin.CENTER,
        pixelOffset: _deslocaFraco,
        position: C.Cartesian3.ZERO,
      }),
      ponto: colPontos.add({
        show: false,
        pixelSize: 4,
        color: CORES.ponto,
        outlineColor: destaque,
        outlineWidth: 1,
        position: C.Cartesian3.ZERO,
      }),
    });
  }
  cena.scene.primitives.add(colPontos);
  cena.scene.primitives.add(colNomes);

  for (const p of D.paises) {
    p.pos = C.Cartesian3.fromDegrees(p.lx, p.ly);
    p.rotulo = Array.from(p.nome.toUpperCase()).join(" ");
  }
  paisesOrdem = [...D.paises].sort((a, b) => a.minl - b.minl || b.pop - a.pop);
  capitais = D.cidades.filter((c) => c.cap === 2).sort((a, b) => b.pop - a.pop);
  estaduais = D.cidades.filter((c) => c.cap === 1);

  cena.aoParar.push(() => atualizar());
  atualizar();
}

export function definirLigado(v) {
  ligado = !!v;
  atualizar();
}

/** Cidade escolhida: o nome dela aparece sempre, mesmo sem caber. */
export function definirPrioridade(c) {
  prioridade = c;
  atualizar();
}

function posCidade(c) {
  if (!c.p) c.p = C.Cartesian3.fromDegrees(c.lon, c.lat, cena.relevo ? c.alt : 0);
  return c.p;
}

function popMinima(z) {
  if (z < 2.9) return Infinity;
  if (z < 3.7) return 6e6;
  if (z < 4.5) return 2e6;
  if (z < 5.4) return 6e5;
  if (z < 6.3) return 2e5;
  if (z < 7.2) return 7e4;
  if (z < 8.2) return 2.5e4;
  return 0;
}

function colide(ocupados, x0, y0, x1, y1) {
  for (let i = 0; i < ocupados.length; i += 4) {
    if (x0 < ocupados[i + 2] && x1 > ocupados[i] && y0 < ocupados[i + 3] && y1 > ocupados[i + 1]) return true;
  }
  return false;
}

export function atualizar() {
  if (!colNomes) return;
  const usar = ligado && cena.modo !== "mapa";
  const h = altura();
  const z = zoomEquivalente();
  const L = cena.canvas.clientWidth;
  const A = cena.canvas.clientHeight;
  const cam = cena.camera.positionWC;
  const scene = cena.scene;
  const ocupados = [];
  const novos = [];
  const jaEntrou = new Set();
  let nPaises = 0;
  let nCidades = 0;

  const tentar = (obj, tipo, pos, texto, opcoes) => {
    if (jaEntrou.has(obj)) return false;
    if (tipo === "pais" ? nPaises >= MAX_PAISES : nCidades >= MAX_CIDADES) return false;
    // Do outro lado da Terra, ou atras do horizonte.
    if (C.Cartesian3.dot(pos, cam) < RAIO2) return false;
    const t = C.SceneTransforms.worldToWindowCoordinates(scene, pos, _tela);
    if (!t) return false;
    if (t.x < -40 || t.y < -20 || t.x > L + 40 || t.y > A + 20) return false;
    const larg = texto.length * opcoes.pxLetra + 6;
    let x0, x1;
    if (tipo === "pais") { x0 = t.x - larg / 2; x1 = t.x + larg / 2; } else { x0 = t.x - 5; x1 = t.x + 10 + larg; }
    const y0 = t.y - 10, y1 = t.y + 10;
    if (!opcoes.forcar && colide(ocupados, x0, y0, x1, y1)) return false;
    ocupados.push(x0 - 4, y0 - 2, x1 + 4, y1 + 2);
    jaEntrou.add(obj);
    novos.push({ obj, tipo, pos, texto, ...opcoes, dx0: x0 - t.x, dx1: x1 - t.x });
    if (tipo === "pais") nPaises++; else nCidades++;
    return true;
  };

  if (prioridade && cena.modo !== "mapa") {
    tentar(prioridade, "cidade", posCidade(prioridade), nomeCidade(prioridade, idioma), { pxLetra: 8.6, forte: true, forcar: true });
  }

  if (usar && h > 9000) {
    if (z < 8.6) {
      for (const p of paisesOrdem) {
        if (nPaises >= MAX_PAISES) break;
        if (z + 0.9 < p.minl || z > p.maxl + 2.6) continue;
        tentar(p, "pais", p.pos, p.rotulo, { pxLetra: 5.6, tamanho: z < 3 ? 0.46 : 0.5 });
      }
    }

    const minima = popMinima(z);
    if (minima !== Infinity) {
      const novaCidade = (c) => {
        if (c === prioridade || c.cap < 0) return;
        tentar(c, "cidade", posCidade(c), nomeCidade(c, idioma), { pxLetra: c.cap === 2 ? 7.8 : 7.1, forte: c.cap === 2 });
      };
      if (z >= 3.3) for (const c of capitais) { if (c.pop >= minima * 0.15 || z >= 4.5) novaCidade(c); }
      if (z >= 4.5) for (const c of estaduais) { if (c.pop >= minima * 0.3) novaCidade(c); }

      if (z < 6.3) {
        for (const c of D.cidades) {
          if (c.pop < minima || nCidades >= MAX_CIDADES) break;
          novaCidade(c);
        }
      } else {
        // De perto, olha so' as celulas que estao na tela.
        const ret = cena.camera.computeViewRectangle();
        if (ret) {
          const passo = 2;
          let oeste = C.Math.toDegrees(ret.west), leste = C.Math.toDegrees(ret.east);
          const sul = C.Math.toDegrees(ret.south), norte = C.Math.toDegrees(ret.north);
          if (leste < oeste) leste += 360;
          if (leste - oeste > 90) oeste = leste - 90;
          const lista = [];
          for (let la = Math.floor((sul + 90) / passo); la <= Math.floor((norte + 90) / passo); la++) {
            for (let lo = oeste; lo <= leste + passo; lo += passo) {
              const b = Math.floor((((lo + 180) % 360) + 360) % 360 / passo);
              const c = D.grade.get((la << 8) | b);
              if (c) for (const x of c) { if (x.pop < minima) break; lista.push(x); }
              if (lista.length > 4000) break;
            }
          }
          lista.sort((a, b) => b.pop - a.pop);
          for (const c of lista) {
            if (nCidades >= MAX_CIDADES) break;
            novaCidade(c);
          }
        }
      }
    }
  }

  aplicar(novos, vagasPais, "pais");
  aplicar(novos, vagasCidade, "cidade");
  ativos = novos;
  // As letras novas entram na textura um pouco depois: sem estes desenhos a mais, o
  // nome ficava sem letra ("Nova York" virava "Nova ork") ate o proximo movimento.
  scene.requestRender();
  for (const ms of [60, 160, 340, 700, 1300]) setTimeout(() => scene.requestRender(), ms);
}

/**
 * Cada nome continua na vaga em que ja estava. Assim o que nao mudou nem e' tocado:
 * so' some o que saiu e so' desenha letra para o que entrou. Era isso que piscava.
 */
function aplicar(novos, vagas, tipo) {
  const lista = novos.filter((n) => n.tipo === tipo);
  const quem = new Map();
  for (const n of lista) quem.set(n.obj, n);
  const livres = [];
  for (const v of vagas) {
    if (v.obj && quem.has(v.obj)) {
      vestir(v, quem.get(v.obj));
      quem.delete(v.obj);
    } else {
      livres.push(v);
    }
  }
  for (const n of quem.values()) {
    const v = livres.pop();
    if (!v) break;
    v.obj = n.obj;
    vestir(v, n);
  }
  for (const v of livres) {
    v.obj = null;
    if (v.nome.show) v.nome.show = false;
    if (v.ponto?.show) v.ponto.show = false;
  }
}

function vestir(v, n) {
  const lb = v.nome;
  if (lb.text !== n.texto) lb.text = n.texto;
  if (lb.position !== n.pos) lb.position = n.pos;
  if (n.tipo === "pais") {
    const esc = n.tamanho || 0.5;
    if (lb.scale !== esc) lb.scale = esc;
  } else {
    const esc = n.forte ? 0.54 : 0.48;
    if (lb.scale !== esc) lb.scale = esc;
    const cor = n.forte ? CORES.capital : CORES.cidade;
    if (lb.fillColor !== cor) lb.fillColor = cor;
    const desloca = n.forte ? _deslocaForte : _deslocaFraco;
    if (lb.pixelOffset !== desloca) lb.pixelOffset = desloca;
    const pt = v.ponto;
    if (pt.position !== n.pos) pt.position = n.pos;
    const tam = n.forte ? 5.5 : 4;
    if (pt.pixelSize !== tam) {
      pt.pixelSize = tam;
      pt.outlineWidth = n.forte ? 1.5 : 1;
    }
    if (!pt.show) pt.show = true;
  }
  if (!lb.show) lb.show = true;
}

/** O que esta embaixo do mouse: uma cidade (ponto ou nome) ou o nome de um pais. */
export function tocou(x, y) {
  let melhor = null;
  for (const a of ativos) {
    const t = C.SceneTransforms.worldToWindowCoordinates(cena.scene, a.pos, _tela);
    if (!t) continue;
    if (y < t.y - 11 || y > t.y + 11 || x < t.x + a.dx0 || x > t.x + a.dx1) continue;
    if (!melhor || (melhor.tipo === "pais" && a.tipo === "cidade")) melhor = a;
  }
  return melhor ? { tipo: melhor.tipo, obj: melhor.obj } : null;
}

/** O relevo mudou a altura do chao: as cidades prontas tem de ser recalculadas. */
export function esquecerPosicoes() {
  for (const c of D.cidades) if (c.p) c.p = null;
  atualizar();
}
