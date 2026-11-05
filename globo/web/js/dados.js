// Paises e cidades: tudo vem da propria pasta do JARVIS, entao o globo responde
// na hora e continua funcionando sem internet.

import { nomeDoPais, semAcento } from "./textos.js";

export const D = {
  paises: [],
  porIso: {},
  cidades: [],
  fusos: [],
  estados: {},
  estadosLinhas: [],
  grade: new Map(),          // celula de 2 graus -> cidades, da mais populosa para a menor
};

function celula(lat, lon) {
  return (Math.floor((lat + 90) / 2) << 8) | Math.floor(((lon + 180) % 360) / 2);
}

export async function carregar(aoAvancar) {
  const pedir = async (arq) => {
    const r = await fetch(arq);
    if (!r.ok) throw new Error(`${arq}: ${r.status}`);
    return r;
  };

  aoAvancar?.("paises");
  const [paises, estados, linhas] = await Promise.all([
    pedir("dados/paises.json").then((r) => r.json()),
    pedir("dados/estados.json").then((r) => r.json()),
    pedir("dados/estados_linhas.json").then((r) => r.json()),
  ]);
  D.estados = estados;
  D.estadosLinhas = linhas;

  for (const p of paises) {
    p.nome = nomeDoPais(p.iso, p.pt);
    p.partes = p.geo.map((poly) => {
      // Caixa de cada pedaco: a mao corre em cima disto a cada movimento do mouse.
      let w = 999, e = -999, s = 999, n = -999;
      const a = poly[0];
      for (let i = 0; i < a.length; i += 2) {
        if (a[i] < w) w = a[i];
        if (a[i] > e) e = a[i];
        if (a[i + 1] < s) s = a[i + 1];
        if (a[i + 1] > n) n = a[i + 1];
      }
      return { aneis: poly, w, e, s, n };
    });
    if (p.iso) D.porIso[p.iso] = p;
    p.chave = semAcento([p.nome, p.pt, p.en, p.iso, p.iso3, ...(p.apelidos || [])].join(" "));
  }
  D.paises = paises;
  aoAvancar?.("cidades");

  const bruto = await pedir("dados/cidades.json").then((r) => r.json());
  D.fusos = bruto.fusos;
  D.cidades = bruto.c.map((c, i) => ({
    i, n: c[0], lat: c[1], lon: c[2], cc: c[3], a1: c[4], pop: c[5], fuso: c[6], cap: c[7], alt: c[8], pt: c[9], ap: c[10] || "",
  }));
  for (const c of D.cidades) {
    const k = celula(c.lat, c.lon);
    let lista = D.grade.get(k);
    if (!lista) D.grade.set(k, (lista = []));
    lista.push(c);
  }
}

export function nomeCidade(c, idioma) {
  return (idioma !== "en" && c.pt) || c.n;
}

export function nomeEstado(c) {
  return D.estados[c.cc]?.[c.a1] || "";
}

export function paisDaCidade(c) {
  return D.porIso[c.cc] || null;
}

export function fusoDaCidade(c) {
  return D.fusos[c.fuso];
}

function dentroDoAnel(lon, lat, a) {
  let dentro = false;
  for (let i = 0, j = a.length - 2; i < a.length; j = i, i += 2) {
    const xi = a[i], yi = a[i + 1], xj = a[j], yj = a[j + 1];
    if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}

/** Qual pais esta neste ponto? Conta feita no processador: nao pesa na placa. */
export function paisEm(lon, lat) {
  for (const p of D.paises) {
    const b = p.bbox;
    if (lat < b[1] || lat > b[3] || lon < b[0] || lon > b[2]) continue;
    for (const parte of p.partes) {
      if (lat < parte.s || lat > parte.n || lon < parte.w || lon > parte.e) continue;
      if (!dentroDoAnel(lon, lat, parte.aneis[0])) continue;
      let noBuraco = false;
      for (let h = 1; h < parte.aneis.length; h++) {
        if (dentroDoAnel(lon, lat, parte.aneis[h])) { noBuraco = true; break; }
      }
      if (!noBuraco) return p;
    }
  }
  return null;
}

export function distanciaKm(aLat, aLon, bLat, bLon) {
  const r = Math.PI / 180;
  const dLat = (bLat - aLat) * r;
  const dLon = (bLon - aLon) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(aLat * r) * Math.cos(bLat * r) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Cidades ao redor de um ponto, da mais populosa para a menor. */
export function cidadesPerto(lat, lon, raioKm, limite = 10, ignorar = null) {
  const graus = Math.ceil(raioKm / 110 / 2) + 1;
  const a = Math.floor((lat + 90) / 2);
  const b = Math.floor(((lon + 180) % 360) / 2);
  const achadas = [];
  for (let x = a - graus; x <= a + graus; x++) {
    for (let y = b - graus * 2; y <= b + graus * 2; y++) {
      const lista = D.grade.get((x << 8) | ((y + 180) % 180));
      if (!lista) continue;
      for (const c of lista) {
        if (c === ignorar || c.cap < 0) continue;
        const d = distanciaKm(lat, lon, c.lat, c.lon);
        if (d <= raioKm) achadas.push({ c, d });
      }
    }
  }
  achadas.sort((p, q) => q.c.pop - p.c.pop);
  return achadas.slice(0, limite);
}

export function cidadeMaisProxima(lat, lon, raioKm = 120) {
  const graus = Math.ceil(raioKm / 110 / 2) + 1;
  const a = Math.floor((lat + 90) / 2);
  const b = Math.floor(((lon + 180) % 360) / 2);
  let melhor = null;
  for (let x = a - graus; x <= a + graus; x++) {
    for (let y = b - graus * 2; y <= b + graus * 2; y++) {
      const lista = D.grade.get((x << 8) | ((y + 180) % 180));
      if (!lista) continue;
      for (const c of lista) {
        const d = distanciaKm(lat, lon, c.lat, c.lon);
        if (d <= raioKm && (!melhor || d < melhor.d)) melhor = { c, d };
      }
    }
  }
  return melhor;
}

export function cidadesDoPais(iso, limite = 12) {
  const lista = [];
  for (const c of D.cidades) {                 // ja vem da maior para a menor
    if (c.cc === iso && c.cap >= 0) {
      lista.push(c);
      if (lista.length >= limite) break;
    }
  }
  return lista;
}
