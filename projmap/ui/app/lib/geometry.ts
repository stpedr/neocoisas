// Geometria no navegador — espelho de projmap/core/geometry.py.
// A UI precisa dela para levar o que se desenha na FOTO para pixels do
// PROJETOR (homografia foto→projetor definida pela "área projetada") e para
// recusar, já no arraste, quads que o servidor recusaria (côncavo/cruzado).

import type { Point } from "./types";

export type Mat3 = number[]; // 9 números, linha a linha

export function applyH(h: Mat3, p: Point): Point {
  const x = h[0] * p[0] + h[1] * p[1] + h[2];
  const y = h[3] * p[0] + h[4] * p[1] + h[5];
  const w = h[6] * p[0] + h[7] * p[1] + h[8];
  return [x / w, y / w];
}

// Resolve A·x = b (8×8) por eliminação de Gauss com pivotamento parcial.
function solve(a: number[][], b: number[]): number[] | null {
  const n = b.length;
  const m = a.map((row, i) => [...row, b[i]]);
  for (let c = 0; c < n; c++) {
    let piv = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(m[r][c]) > Math.abs(m[piv][c])) piv = r;
    if (Math.abs(m[piv][c]) < 1e-12) return null;
    [m[c], m[piv]] = [m[piv], m[c]];
    for (let r = 0; r < n; r++) {
      if (r === c) continue;
      const f = m[r][c] / m[c][c];
      for (let k = c; k <= n; k++) m[r][k] -= f * m[c][k];
    }
  }
  return m.map((row, i) => row[n] / row[i]);
}

/** Homografia exata src→dst com 4 pares (h33 = 1). Pontos normalizados por
 * centróide/escala, como a DLT do Python, para não perder precisão em 4K. */
export function homography4(src: Point[], dst: Point[]): Mat3 | null {
  const norm = (pts: Point[]) => {
    const cx = pts.reduce((s, p) => s + p[0], 0) / 4;
    const cy = pts.reduce((s, p) => s + p[1], 0) / 4;
    const d = pts.reduce((s, p) => s + Math.hypot(p[0] - cx, p[1] - cy), 0) / 4 || 1;
    const k = Math.SQRT2 / d;
    return { t: [k, 0, -k * cx, 0, k, -k * cy, 0, 0, 1], pts: pts.map((p) => [(p[0] - cx) * k, (p[1] - cy) * k] as Point) };
  };
  const s = norm(src);
  const d = norm(dst);
  const a: number[][] = [];
  const b: number[] = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = s.pts[i];
    const [u, v] = d.pts[i];
    a.push([x, y, 1, 0, 0, 0, -u * x, -u * y]);
    b.push(u);
    a.push([0, 0, 0, x, y, 1, -v * x, -v * y]);
    b.push(v);
  }
  const hv = solve(a, b);
  if (!hv) return null;
  const hn = [...hv, 1];
  const tdInv = invert3(d.t);
  if (!tdInv) return null;
  const h = mul3(mul3(tdInv, hn), s.t);
  return h.map((v) => v / h[8]);
}

export function mul3(a: Mat3, b: Mat3): Mat3 {
  const r = new Array(9).fill(0);
  for (let i = 0; i < 3; i++)
    for (let j = 0; j < 3; j++) for (let k = 0; k < 3; k++) r[i * 3 + j] += a[i * 3 + k] * b[k * 3 + j];
  return r;
}

export function invert3(m: Mat3): Mat3 | null {
  const [a, b, c, d, e, f, g, h, i] = m;
  const A = e * i - f * h;
  const B = -(d * i - f * g);
  const C = d * h - e * g;
  const det = a * A + b * B + c * C;
  if (Math.abs(det) < 1e-15) return null;
  const inv = [A, -(b * i - c * h), b * f - c * e, B, a * i - c * g, -(a * f - c * d), C, -(a * h - b * g), a * e - b * d];
  return inv.map((v) => v / det);
}

export function rectQuad(x: number, y: number, w: number, h: number): Point[] {
  return [
    [x, y],
    [x + w, y],
    [x + w, y + h],
    [x, y + h],
  ];
}

/** Mesmas regras de validate_quad() do Python. Devolve mensagem ou null. */
export function validateQuad(q: Point[], minArea = 1): string | null {
  if (q.length !== 4) return "um quad precisa de 4 cantos";
  if (q.some((p) => !Number.isFinite(p[0]) || !Number.isFinite(p[1]))) return "coordenadas inválidas";
  let area = 0;
  for (let i = 0; i < 4; i++) {
    const [x0, y0] = q[i];
    const [x1, y1] = q[(i + 1) % 4];
    area += x0 * y1 - x1 * y0;
  }
  if (Math.abs(area / 2) < minArea) return "quad degenerado";
  const signs = [0, 1, 2, 3].map((i) => {
    const o = q[i];
    const a = q[(i + 1) % 4];
    const b = q[(i + 2) % 4];
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  });
  if (signs.some((s) => Math.abs(s) < 1e-9)) return "três cantos colineares";
  if (!(signs.every((s) => s > 0) || signs.every((s) => s < 0))) return "quad côncavo ou cruzado";
  return null;
}

export function pointInQuad(p: Point, q: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = q.length - 1; i < q.length; j = i++) {
    const [xi, yi] = q[i];
    const [xj, yj] = q[j];
    if (yi > p[1] !== yj > p[1] && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Homografia pixel da foto → pixel do projetor (área projetada → quadro inteiro). */
export function photoToProjector(boundaryNorm: Point[], photoW: number, photoH: number, outW: number, outH: number) {
  const src = boundaryNorm.map(([x, y]) => [x * photoW, y * photoH] as Point);
  return homography4(src, rectQuad(0, 0, outW, outH));
}
