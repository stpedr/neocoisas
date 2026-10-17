// Prévia de mídia no editor (F9): desenha vídeo/GIF/imagem DENTRO das
// superfícies, já em perspectiva, num canvas 2D.
//
// O canvas 2D só faz transformações afins. Para a perspectiva, a região da
// mídia é dividida numa malha N×N e cada triângulo recebe o seu afim
// (textura → tela). Com N = 10 o erro fica abaixo de 1 px na tela.
//
// A matemática de posição espelha projmap/mapping/warp.py (fit_transform,
// layer_uvx): aqui a pergunta é "em que região do uv da superfície a textura
// inteira cai?" (o inverso de tex = uv·s + o).

import { API_BASE, withToken } from "./api";
import type { Fit, MediaItem, Point, SourceSpec } from "./types";

export type UvRect = [number, number, number, number]; // u0, v0, u1, v1

/** Proporção aparente do quad (média das arestas opostas), igual a quad_aspect. */
export function quadAspect(q: Point[]): number {
  const d = (a: Point, b: Point) => Math.hypot(b[0] - a[0], b[1] - a[1]);
  const w = (d(q[0], q[1]) + d(q[3], q[2])) / 2;
  const h = (d(q[0], q[3]) + d(q[1], q[2])) / 2;
  return h > 1e-9 ? w / h : 1;
}

/** Região do uv da superfície ocupada pela textura inteira.
 * ``rect`` = [x, y, w, h] (a superfície inteira para o fundo). */
export function textureRegion(rect: [number, number, number, number], fit: Fit, srcAspect: number, qAspect: number): UvRect {
  const [x, y, w, h] = rect;
  if (fit === "stretch" || !(srcAspect > 0)) return [x, y, x + w, y + h];
  const aRect = (qAspect * w) / h;
  let rw = w;
  let rh = h;
  const wider = srcAspect > aRect;
  if (fit === "contain") {
    if (wider) rh = h * (aRect / srcAspect);
    else rw = w * (srcAspect / aRect);
  } else {
    if (wider) rw = w * (srcAspect / aRect);
    else rh = h * (aRect / srcAspect);
  }
  const cx = x + w / 2;
  const cy = y + h / 2;
  return [cx - rw / 2, cy - rh / 2, cx + rw / 2, cy + rh / 2];
}

// ------------------------------------------------------------ cache de mídia
type MediaEl = HTMLImageElement | HTMLVideoElement;
const cache = new Map<string, MediaEl>();
let onReady: () => void = () => {};

/** Chamado quando uma mídia termina de carregar (o editor redesenha). */
export function setMediaReadyCallback(fn: () => void) {
  onReady = fn;
}

export function mediaElement(item: MediaItem): MediaEl {
  const hit = cache.get(item.sha256);
  if (hit) return hit;
  const url = withToken(`${API_BASE}/media/${item.sha256}`);
  let el: MediaEl;
  if (item.kind === "video") {
    const v = document.createElement("video");
    v.muted = true;
    v.loop = true;
    v.playsInline = true;
    v.preload = "auto";
    v.src = url;
    v.addEventListener("loadeddata", () => onReady());
    void v.play().catch(() => {
      /* autoplay bloqueado: a primeira interação no editor destrava (unlockVideos) */
    });
    el = v;
  } else {
    // GIF animado: o <img> continua animando e o drawImage pega o quadro atual.
    const img = new Image();
    img.decoding = "async";
    img.onload = () => onReady();
    img.src = url;
    el = img;
  }
  cache.set(item.sha256, el);
  return el;
}

/** Tenta dar play nos vídeos (chamar num gesto do usuário). */
export function unlockVideos() {
  cache.forEach((el) => {
    if (el instanceof HTMLVideoElement && el.paused) void el.play().catch(() => {});
  });
}

export function mediaSize(el: MediaEl): [number, number] {
  if (el instanceof HTMLVideoElement) return [el.videoWidth, el.videoHeight];
  return [el.naturalWidth, el.naturalHeight];
}

export function isReady(el: MediaEl): boolean {
  if (el instanceof HTMLVideoElement) return el.readyState >= 2;
  return el.complete && el.naturalWidth > 0;
}

/** Proporção conhecida da mídia (0 enquanto não carregou). */
export function mediaAspect(item: MediaItem): number {
  const [w, h] = mediaSize(mediaElement(item));
  return w > 0 && h > 0 ? w / h : 0;
}

// --------------------------------------------------------- cartela de teste
let testCard: HTMLCanvasElement | null = null;
function testCardCanvas(): HTMLCanvasElement {
  if (testCard) return testCard;
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 144;
  const g = c.getContext("2d")!;
  const bars = ["#c0c0c0", "#c0c000", "#00c0c0", "#00c000", "#c000c0", "#c00000", "#0000c0"];
  bars.forEach((col, i) => {
    g.fillStyle = col;
    g.fillRect((i * 256) / 7, 0, 256 / 7 + 1, 144);
  });
  g.strokeStyle = "rgba(0,0,0,.6)";
  g.lineWidth = 2;
  for (let x = 0; x <= 256; x += 32) {
    g.beginPath();
    g.moveTo(x, 0);
    g.lineTo(x, 144);
    g.stroke();
  }
  for (let y = 0; y <= 144; y += 36) {
    g.beginPath();
    g.moveTo(0, y);
    g.lineTo(256, y);
    g.stroke();
  }
  g.beginPath();
  g.arc(128, 72, 50, 0, Math.PI * 2);
  g.strokeStyle = "#fff";
  g.lineWidth = 3;
  g.stroke();
  testCard = c;
  return c;
}

// ------------------------------------------------------------------ desenho
export type UvToScreen = (u: number, v: number) => Point;

/** Algo desenhável para uma fonte; null = nada (fonte "none" ou mídia ausente). */
export function drawableFor(spec: SourceSpec, media: Record<string, MediaItem>):
  | { kind: "image"; el: CanvasImageSource; w: number; h: number; animated: boolean }
  | { kind: "color"; color: string }
  | { kind: "label"; text: string }
  | null {
  if (spec.kind === "none") return null;
  if (spec.kind === "color") return { kind: "color", color: `rgb(${spec.color.join(",")})` };
  if (spec.kind === "test") {
    const c = testCardCanvas();
    return { kind: "image", el: c, w: c.width, h: c.height, animated: false };
  }
  if (spec.kind === "interactive") return { kind: "label", text: "cena interativa" };
  if (spec.kind === "capture") return { kind: "label", text: `entrada de vídeo · ${spec.device || "auto"}` };
  const item = spec.media ? media[spec.media] : undefined;
  if (!item) return null;
  const el = mediaElement(item);
  if (!isReady(el)) return { kind: "label", text: "carregando…" };
  const [w, h] = mediaSize(el);
  return { kind: "image", el, w, h, animated: item.kind !== "image" };
}

/** Desenha a imagem ocupando ``region`` (uv da superfície), deformada por ``map``. */
export function drawWarpedImage(
  g: CanvasRenderingContext2D,
  el: CanvasImageSource,
  w: number,
  h: number,
  region: UvRect,
  map: UvToScreen,
  n = 10,
) {
  const [u0, v0, u1, v1] = region;
  const grid: Point[][] = [];
  for (let j = 0; j <= n; j++) {
    const row: Point[] = [];
    for (let i = 0; i <= n; i++) row.push(map(u0 + ((u1 - u0) * i) / n, v0 + ((v1 - v0) * j) / n));
    grid.push(row);
  }
  const sw = w / n;
  const sh = h / n;
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      const p00 = grid[j][i];
      const p10 = grid[j][i + 1];
      const p01 = grid[j + 1][i];
      const p11 = grid[j + 1][i + 1];
      const sx = i * sw;
      const sy = j * sh;
      const cell: [number, number, number, number] = [sx, sy, sw, sh];
      triangle(g, el, cell, w, h, [sx, sy], [sx + sw, sy], [sx, sy + sh], p00, p10, p01);
      triangle(g, el, cell, w, h, [sx + sw, sy], [sx + sw, sy + sh], [sx, sy + sh], p10, p11, p01);
    }
  }
}

// Afim que leva o triângulo (s0,s1,s2) da textura ao (d0,d1,d2) da tela,
// recortado no triângulo de destino levemente inflado (evita frestas).
function triangle(
  g: CanvasRenderingContext2D,
  el: CanvasImageSource,
  cell: [number, number, number, number],
  w: number,
  h: number,
  s0: Point, s1: Point, s2: Point,
  d0: Point, d1: Point, d2: Point,
) {
  const den = (s1[0] - s0[0]) * (s2[1] - s0[1]) - (s2[0] - s0[0]) * (s1[1] - s0[1]);
  if (Math.abs(den) < 1e-9) return;
  const a = ((d1[0] - d0[0]) * (s2[1] - s0[1]) - (d2[0] - d0[0]) * (s1[1] - s0[1])) / den;
  const b = ((d1[1] - d0[1]) * (s2[1] - s0[1]) - (d2[1] - d0[1]) * (s1[1] - s0[1])) / den;
  const c = ((d2[0] - d0[0]) * (s1[0] - s0[0]) - (d1[0] - d0[0]) * (s2[0] - s0[0])) / den;
  const d = ((d2[1] - d0[1]) * (s1[0] - s0[0]) - (d1[1] - d0[1]) * (s2[0] - s0[0])) / den;
  const e = d0[0] - a * s0[0] - c * s0[1];
  const f = d0[1] - b * s0[0] - d * s0[1];
  const cx = (d0[0] + d1[0] + d2[0]) / 3;
  const cy = (d0[1] + d1[1] + d2[1]) / 3;
  const grow = (p: Point): Point => {
    const dx = p[0] - cx;
    const dy = p[1] - cy;
    const len = Math.hypot(dx, dy) || 1;
    return [p[0] + (dx / len) * 0.6, p[1] + (dy / len) * 0.6];
  };
  const [q0, q1, q2] = [grow(d0), grow(d1), grow(d2)];
  g.save();
  g.beginPath();
  g.moveTo(q0[0], q0[1]);
  g.lineTo(q1[0], q1[1]);
  g.lineTo(q2[0], q2[1]);
  g.closePath();
  g.clip();
  g.transform(a, b, c, d, e, f);
  // Copia só a célula (com 1 texel de folga), não a imagem inteira: com 200
  // triângulos por mídia, isso é o que mantém um vídeo 1080p fluido.
  const x0 = Math.max(0, Math.floor(cell[0] - 1));
  const y0 = Math.max(0, Math.floor(cell[1] - 1));
  const x1 = Math.min(w, Math.ceil(cell[0] + cell[2] + 1));
  const y1 = Math.min(h, Math.ceil(cell[1] + cell[3] + 1));
  if (x1 > x0 && y1 > y0) g.drawImage(el, x0, y0, x1 - x0, y1 - y0, x0, y0, x1 - x0, y1 - y0);
  g.restore();
}
