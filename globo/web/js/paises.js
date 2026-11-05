// Fronteiras, o pais embaixo do mouse e o pais escolhido.
//
// As fronteiras do mundo sao 100 mil pontos. Num `PolylineCollection` cada ponto vira
// objeto na memoria e quatro vertices por trecho na placa. Aqui viram uma linha fina
// fixa, entregue pronta para a placa: uma so' chamada de desenho e nada na memoria do
// programa depois de montada, e quem monta e' uma thread de fundo (a tela nao trava).

import { cena } from "./cena.js";
import { D } from "./dados.js";

const C = window.Cesium;

const VS = `
in vec3 position3DHigh;
in vec3 position3DLow;
in float batchId;
void main() {
  vec4 p = czm_computePosition();
  gl_Position = czm_modelViewProjectionRelativeToEye * p;
}`;

const FS = `
void main() {
  czm_materialInput m;
  czm_material mat = czm_getMaterial(m);
  out_FragColor = vec4(mat.diffuse + mat.emission, mat.alpha);
}`;

let bordas = null;
let estados = null;
let matBorda = null;
let matEstado = null;
let realce = null;
let selecaoLinhas = null;
let preenchimento = null;
let matRealce = null;
let matSelecao = null;
let paisRealcado = null;
let paisEscolhido = null;
const _cores = {};

function faixa(h, alto, baixo) {
  if (h >= alto) return 0;
  if (h <= baixo) return 1;
  const t = (alto - h) / (alto - baixo);
  return t * t * (3 - 2 * t);
}

/**
 * Tira do contorno as linhas que so' existem no mapa plano: a Russia e Fiji sao
 * "cortadas" no meridiano 180 e a Antartida fecha pelo polo. Num globo, desenhar
 * esses cortes faria aparecer um risco reto onde nao tem fronteira nenhuma.
 */
function pedacos(anel, passo = 1) {
  const saida = [];
  let atual = [];
  const n = anel.length;
  for (let i = 0; i < n; i += 2) {
    const x = anel[i], y = anel[i + 1];
    if (atual.length >= 2) {
      const px = atual[atual.length - 2], py = atual[atual.length - 1];
      const noMeridiano = Math.abs(px) >= 179.98 && Math.abs(x) >= 179.98;
      const noPolo = py < -89.4 && y < -89.4;
      if (noMeridiano || noPolo || Math.abs(x - px) > 180) {
        if (atual.length >= 4) saida.push(atual);
        atual = [];
      } else {
        // Trecho comprido (a fronteira EUA-Canada tem poucos pontos) acompanha a curva.
        const dx = x - px, dy = y - py;
        const fatias = Math.ceil(Math.max(Math.abs(dx), Math.abs(dy)) / 1.5);
        for (let k = 1; k < fatias; k++) atual.push(px + (dx * k) / fatias, py + (dy * k) / fatias);
      }
    }
    if (passo === 1 || i % (passo * 2) === 0 || i >= n - 2) atual.push(x, y);
  }
  if (atual.length >= 4) saida.push(atual);
  return saida;
}

function linhasFixas(listas, material) {
  const instancias = [];
  for (const pedaco of listas) {
    instancias.push(new C.GeometryInstance({
      geometry: new C.SimplePolylineGeometry({
        positions: C.Cartesian3.fromDegreesArray(pedaco),
        arcType: C.ArcType.NONE,
      }),
    }));
  }
  return new C.Primitive({
    geometryInstances: instancias,
    appearance: new C.Appearance({
      material,
      translucent: true,
      vertexShaderSource: VS,
      fragmentShaderSource: FS,
      renderState: {
        depthTest: { enabled: true },
        depthMask: false,
        blending: C.BlendingState.ALPHA_BLEND,
      },
    }),
    asynchronous: true,
    allowPicking: false,
    releaseGeometryInstances: true,
    vertexCacheOptimize: false,
    interleave: true,
    cull: false,
  });
}

export function construir() {
  const scene = cena.scene;
  // PC fraco: um ponto a cada tres. De longe ninguem ve a diferenca.
  const passo = cena.nivel === "leve" ? 3 : 1;

  matBorda = C.Material.fromType("Color", { color: C.Color.WHITE.withAlpha(0.3) });
  matEstado = C.Material.fromType("Color", { color: C.Color.WHITE.withAlpha(0.14) });
  matRealce = C.Material.fromType("Color", { color: C.Color.fromCssColorString("#ffffff").withAlpha(0.95) });
  matSelecao = cena.nivel === "leve"
    ? C.Material.fromType("Color", { color: C.Color.fromCssColorString(cena.cor) })
    : C.Material.fromType("PolylineGlow", { color: C.Color.fromCssColorString(cena.cor), glowPower: 0.22, taperPower: 1.0 });

  const listaPaises = [];
  for (const p of D.paises) {
    for (const parte of p.partes) {
      for (const anel of parte.aneis) listaPaises.push(...pedacos(anel, passo));
    }
  }
  const listaEstados = [];
  for (const linha of D.estadosLinhas) listaEstados.push(...pedacos(linha, passo));
  D.estadosLinhas = [];         // ja esta na placa: nao precisa ficar na memoria

  bordas = linhasFixas(listaPaises, matBorda);
  estados = linhasFixas(listaEstados, matEstado);
  realce = new C.PolylineCollection();
  selecaoLinhas = new C.PolylineCollection();
  scene.primitives.add(bordas);
  scene.primitives.add(estados);
  scene.primitives.add(selecaoLinhas);
  scene.primitives.add(realce);
  cena.aoAjustarAltura.push(ajustar);
  ajustar(cena.camera.positionCartographic.height);
}

function corPara(chave, css, alfa) {
  _cores[chave] ||= new C.Color();
  C.Color.fromCssColorString(css, _cores[chave]);
  _cores[chave].alpha = alfa;
  return _cores[chave];
}

export function ajustar(h) {
  if (!bordas) return;
  const liga = cena.bordas;
  // Pertinho do chao a linha de 1 km de precisao fica torta em cima da foto.
  const perto = faixa(-h, -35e3, -160e3);
  let cor = "#d6f4ff", forca = 0.34;
  if (cena.modo === "mapa") { cor = "#2f5f80"; forca = 0.6; }
  if (cena.modo === "holograma") { cor = cena.cor; forca = 0.62; }
  const aPais = liga ? forca * perto : 0;
  const aEstado = liga ? forca * 0.62 * perto * faixa(h, 7.5e6, 3.2e6) : 0;
  matBorda.uniforms.color = corPara("b", cor, aPais);
  matEstado.uniforms.color = corPara("e", cor, aEstado);
  bordas.show = aPais > 0.01;
  estados.show = aEstado > 0.01;
  // Dentro do pais escolhido a tinta cobriria a tela toda: ela some ao chegar perto.
  if (preenchimento) preenchimento.show = h > 9.0e5;
  selecaoLinhas.show = h > 4.0e4;
}

function desenharContorno(colecao, p, material, largura) {
  colecao.removeAll();
  if (!p) return;
  const passo = cena.nivel === "leve" ? 2 : 1;
  for (const parte of p.partes) {
    for (const anel of parte.aneis) {
      for (const pedaco of pedacos(anel, passo)) {
        colecao.add({ positions: C.Cartesian3.fromDegreesArray(pedaco), width: largura, material });
      }
    }
  }
}

/** O pais embaixo do mouse: so' a linha, que e' instantanea. */
export function realcar(p) {
  if (p === paisRealcado) return;
  paisRealcado = p;
  // Em PC fraco o nome junto do mouse basta.
  if (realce && cena.nivel !== "leve") {
    desenharContorno(realce, p && p !== paisEscolhido ? p : null, matRealce, 1.6);
    cena.scene.requestRender();
  }
}

/** O pais escolhido: contorno com brilho e o miolo levemente pintado. */
export function escolher(p) {
  if (p === paisEscolhido) return;
  paisEscolhido = p;
  if (!selecaoLinhas) return;
  desenharContorno(selecaoLinhas, p, matSelecao, cena.nivel === "leve" ? 2.5 : 7);
  if (paisRealcado === p) desenharContorno(realce, null);
  if (preenchimento) {
    cena.scene.primitives.remove(preenchimento);
    preenchimento = null;
  }
  // A Antartida passa pelo polo: fica so' com o contorno.
  if (p && p.en !== "Antarctica") {
    const cor = C.ColorGeometryInstanceAttribute.fromColor(C.Color.fromCssColorString(cena.cor).withAlpha(0.15));
    const instancias = [];
    for (const parte of p.partes) {
      const [fora, ...buracos] = parte.aneis;
      if (fora.length < 8) continue;
      instancias.push(new C.GeometryInstance({
        geometry: new C.PolygonGeometry({
          polygonHierarchy: new C.PolygonHierarchy(
            C.Cartesian3.fromDegreesArray(fora),
            buracos.map((b) => new C.PolygonHierarchy(C.Cartesian3.fromDegreesArray(b))),
          ),
          arcType: C.ArcType.RHUMB,
          granularity: C.Math.toRadians(2.0),
          vertexFormat: C.PerInstanceColorAppearance.FLAT_VERTEX_FORMAT,
        }),
        attributes: { color: cor },
      }));
    }
    if (instancias.length) {
      preenchimento = new C.Primitive({
        geometryInstances: instancias,
        appearance: new C.PerInstanceColorAppearance({ flat: true, translucent: true, closed: false }),
        asynchronous: true,
        releaseGeometryInstances: true,
        allowPicking: false,
      });
      cena.scene.primitives.add(preenchimento);
      preenchimento.show = cena.camera.positionCartographic.height > 9.0e5;
    }
  }
  cena.scene.requestRender();
}

export function paisAtual() {
  return paisEscolhido;
}
