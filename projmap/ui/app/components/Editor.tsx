"use client";

// Editor de mapeamento em canvas 2D (mouse e toque via Pointer Events).
//
// Duas vistas sobre o MESMO dado (quads em pixels do projetor):
//  - "photo": a foto tirada da posição do projetor; os quads são mostrados
//    através da homografia projetor→foto (inversa da "área projetada").
//  - "projector": o quadro do projetor em si (para ajuste fino olhando a parede).
// Arrastar em qualquer vista converte de volta para pixels do projetor; o
// renderer do nó e a parede atualizam no frame seguinte.

import { useCallback, useEffect, useRef, useState } from "react";
import { applyH, invert3, pointInQuad, validateQuad, type Mat3 } from "../lib/geometry";
import type { Node, Point, Surface } from "../lib/types";

export type View = "photo" | "projector";
export type Mode = "surfaces" | "boundary";

const HANDLE = 9; // raio visual do canto (px de tela)
const HIT = 22; // raio de toque (dedo no celular)
const COLORS = ["#7c5cff", "#34d399", "#4f8cff", "#fbbf24", "#f87171", "#22d3ee", "#e879f9", "#a3e635"];

interface Props {
  node: Node;
  surfaces: Surface[];
  view: View;
  mode: Mode;
  photo: HTMLImageElement | null;
  photoToProj: Mat3 | null; // pixel da foto → pixel do projetor
  selectedId: string | null;
  selectedCorner: number | null;
  onSelect: (id: string | null, corner: number | null) => void;
  onQuad: (id: string, quad: Point[]) => void;
  onBoundary: (boundary: Point[]) => void;
  onReject: (msg: string) => void;
}

type Drag =
  | { kind: "corner"; id: string; corner: number; quadView: Point[] }
  | { kind: "move"; id: string; start: Point; quadView: Point[] }
  | { kind: "boundary"; corner: number };

export default function Editor(props: Props) {
  const { node, surfaces, view, mode, photo, photoToProj, selectedId, selectedCorner } = props;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 450, dpr: 1 });
  const dragRef = useRef<Drag | null>(null);
  const [pointer, setPointer] = useState<Point | null>(null); // em px de tela, para a lupa
  const lastReject = useRef(0);

  const usePhoto = view === "photo" && photo !== null && photoToProj !== null;
  const viewW = usePhoto ? photo!.naturalWidth : node.output.width;
  const viewH = usePhoto ? photo!.naturalHeight : node.output.height;
  const projToPhoto = usePhoto ? invert3(photoToProj!) : null;

  // ---- mapeamentos: projetor <-> vista <-> tela
  const scale = Math.min(size.w / viewW, size.h / viewH);
  const ox = (size.w - viewW * scale) / 2;
  const oy = (size.h - viewH * scale) / 2;
  const viewToScreen = useCallback((p: Point): Point => [ox + p[0] * scale, oy + p[1] * scale], [ox, oy, scale]);
  const screenToView = useCallback((p: Point): Point => [(p[0] - ox) / scale, (p[1] - oy) / scale], [ox, oy, scale]);
  const projToView = useCallback(
    (p: Point): Point => (projToPhoto ? applyH(projToPhoto, p) : p),
    [projToPhoto],
  );
  const viewToProj = useCallback(
    (p: Point): Point => (usePhoto ? applyH(photoToProj!, p) : p),
    [usePhoto, photoToProj],
  );

  // ---- tamanho do canvas acompanha o contêiner (e a densidade da tela)
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setSize({ w: Math.max(200, r.width), h: Math.max(150, r.height), dpr: window.devicePixelRatio || 1 });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ---- desenho
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    cv.width = Math.round(size.w * size.dpr);
    cv.height = Math.round(size.h * size.dpr);
    const g = cv.getContext("2d");
    if (!g) return;
    g.setTransform(size.dpr, 0, 0, size.dpr, 0, 0);
    const css = getComputedStyle(cv);
    g.fillStyle = css.getPropertyValue("--canvas-bg") || "#05070b";
    g.fillRect(0, 0, size.w, size.h);

    const [x0, y0] = viewToScreen([0, 0]);
    const [x1, y1] = viewToScreen([viewW, viewH]);
    if (usePhoto) {
      g.drawImage(photo!, x0, y0, x1 - x0, y1 - y0);
    } else {
      g.fillStyle = "#000";
      g.fillRect(x0, y0, x1 - x0, y1 - y0);
      g.strokeStyle = "rgba(148,163,184,0.12)";
      g.lineWidth = 1;
      const step = Math.max(viewW, viewH) / 16;
      for (let x = 0; x <= viewW; x += step) line(g, viewToScreen([x, 0]), viewToScreen([x, viewH]));
      for (let y = 0; y <= viewH; y += step) line(g, viewToScreen([0, y]), viewToScreen([viewW, y]));
    }

    // Quadro do projetor: na vista de projetor é a borda; na de foto, a área projetada.
    const frame = usePhoto
      ? node.photo_boundary.map(([x, y]) => viewToScreen([x * viewW, y * viewH]))
      : [viewToScreen([0, 0]), viewToScreen([viewW, 0]), viewToScreen([viewW, viewH]), viewToScreen([0, viewH])];
    g.save();
    g.setLineDash([8, 6]);
    g.strokeStyle = mode === "boundary" ? "#fbbf24" : "rgba(251,191,36,0.6)";
    g.lineWidth = mode === "boundary" ? 2.5 : 1.5;
    poly(g, frame);
    g.stroke();
    g.restore();
    if (mode === "boundary" && usePhoto) {
      frame.forEach((p, i) => handle(g, p, "#fbbf24", ["TL", "TR", "BR", "BL"][i], true));
    }

    // Superfícies
    const ordered = [...surfaces].sort((a, b) => a.z - b.z);
    ordered.forEach((s) => {
      const idx = surfaces.indexOf(s);
      const color = COLORS[idx % COLORS.length];
      const pts = s.warp.base.map((p) => viewToScreen(projToView(p as Point)));
      const sel = s.id === selectedId;
      g.save();
      g.globalAlpha = s.visible ? 1 : 0.35;
      poly(g, pts);
      g.fillStyle = hexA(color, sel ? 0.28 : 0.16);
      g.fill();
      g.lineWidth = sel ? 2.5 : 1.5;
      g.strokeStyle = color;
      g.stroke();
      // Diagonais do quad selecionado: ajudam a ver a perspectiva.
      if (sel) {
        g.setLineDash([4, 4]);
        g.globalAlpha = 0.5;
        line(g, pts[0], pts[2]);
        line(g, pts[1], pts[3]);
        g.setLineDash([]);
        g.globalAlpha = 1;
      }
      const c = pts.reduce((a, p) => [a[0] + p[0] / 4, a[1] + p[1] / 4], [0, 0]);
      g.font = "600 12px Inter, system-ui, sans-serif";
      g.fillStyle = "#fff";
      g.textAlign = "center";
      g.shadowColor = "rgba(0,0,0,.8)";
      g.shadowBlur = 4;
      g.fillText(s.label || s.id, c[0], c[1]);
      g.restore();
      if (mode === "surfaces" && (sel || surfaces.length <= 6)) {
        pts.forEach((p, i) => handle(g, p, i === 0 ? "#f87171" : color, sel ? String(i + 1) : "", sel && i === selectedCorner));
      }
    });

    // Lupa: amplia a FOTO (não o canvas, que teria a bolinha do canto por cima)
    // e desenha só as arestas finas — precisão de canto, inclusive no toque.
    const d = dragRef.current;
    if (pointer && d && (d.kind === "corner" || d.kind === "boundary") && usePhoto) {
      const center = screenToView(pointer);
      let edges: Point[];
      if (d.kind === "boundary") edges = node.photo_boundary.map(([x, y]) => [x * viewW, y * viewH] as Point);
      else edges = (surfaces.find((s) => s.id === d.id)?.warp.base ?? []).map((p) => projToView(p as Point));
      loupe(g, photo!, center, pointer, scale, size, edges);
    }
  }, [size, surfaces, node, view, mode, photo, usePhoto, viewW, viewH, viewToScreen, screenToView, projToView, scale, selectedId, selectedCorner, pointer]);

  // ---- interação
  const eventPoint = (e: React.PointerEvent): Point => {
    const r = canvasRef.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };

  const onPointerDown = (e: React.PointerEvent) => {
    const sp = eventPoint(e);
    canvasRef.current!.setPointerCapture(e.pointerId);
    canvasRef.current!.focus();
    if (mode === "boundary") {
      if (!usePhoto) return;
      const frame = node.photo_boundary.map(([x, y]) => viewToScreen([x * viewW, y * viewH]));
      const i = nearest(frame, sp);
      if (i !== null) {
        dragRef.current = { kind: "boundary", corner: i };
        setPointer(sp);
      }
      return;
    }
    const byZ = [...surfaces].sort((a, b) => b.z - a.z);
    const sel = surfaces.find((s) => s.id === selectedId);
    const candidates = sel ? [sel, ...byZ.filter((s) => s !== sel)] : byZ;
    for (const s of candidates) {
      const quadView = s.warp.base.map((p) => projToView(p as Point));
      const i = nearest(quadView.map(viewToScreen), sp);
      if (i !== null) {
        dragRef.current = { kind: "corner", id: s.id, corner: i, quadView };
        props.onSelect(s.id, i);
        setPointer(sp);
        return;
      }
    }
    const vp = screenToView(sp);
    for (const s of candidates) {
      const quadView = s.warp.base.map((p) => projToView(p as Point));
      if (pointInQuad(vp, quadView)) {
        dragRef.current = { kind: "move", id: s.id, start: vp, quadView };
        props.onSelect(s.id, null);
        return;
      }
    }
    props.onSelect(null, null);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const sp = eventPoint(e);
    const vp = screenToView(sp);
    if (d.kind === "boundary") {
      setPointer(sp);
      const next = node.photo_boundary.map((p, i) => (i === d.corner ? ([vp[0] / viewW, vp[1] / viewH] as Point) : p));
      const err = validateQuad(next, 1e-4);
      if (err) return reject(err);
      props.onBoundary(next);
      return;
    }
    let quadView: Point[];
    if (d.kind === "corner") {
      setPointer(sp);
      quadView = d.quadView.map((p, i) => (i === d.corner ? vp : p));
    } else {
      const dx = vp[0] - d.start[0];
      const dy = vp[1] - d.start[1];
      quadView = d.quadView.map(([x, y]) => [x + dx, y + dy] as Point);
    }
    const quad = quadView.map(viewToProj).map(([x, y]) => [round2(x), round2(y)] as Point);
    const err = validateQuad(quad);
    if (err) return reject(err); // o canto "para" em vez de virar um laço
    props.onQuad(d.id, quad);
  };

  const onPointerUp = (e: React.PointerEvent) => {
    dragRef.current = null;
    setPointer(null);
    canvasRef.current?.releasePointerCapture(e.pointerId);
  };

  function reject(msg: string) {
    const now = Date.now();
    if (now - lastReject.current > 1500) {
      lastReject.current = now;
      props.onReject(msg);
    }
  }

  function nearest(pts: Point[], p: Point): number | null {
    let best: number | null = null;
    let bd = HIT;
    pts.forEach((q, i) => {
      const d = Math.hypot(q[0] - p[0], q[1] - p[1]);
      if (d < bd) {
        bd = d;
        best = i;
      }
    });
    return best;
  }

  return (
    <div ref={wrapRef} className="editor-wrap">
      <canvas
        ref={canvasRef}
        className="editor-canvas"
        style={{ width: size.w, height: size.h }}
        tabIndex={0}
        aria-label="Editor de mapeamento: arraste os cantos das superfícies"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      />
    </div>
  );
}

// ---------------------------------------------------------------- desenho
function line(g: CanvasRenderingContext2D, a: Point, b: Point) {
  g.beginPath();
  g.moveTo(a[0], a[1]);
  g.lineTo(b[0], b[1]);
  g.stroke();
}

function poly(g: CanvasRenderingContext2D, pts: Point[]) {
  g.beginPath();
  pts.forEach((p, i) => (i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
  g.closePath();
}

function handle(g: CanvasRenderingContext2D, p: Point, color: string, label: string, active: boolean) {
  g.save();
  g.beginPath();
  g.arc(p[0], p[1], active ? HANDLE + 3 : HANDLE, 0, Math.PI * 2);
  g.fillStyle = active ? color : "rgba(5,7,11,.75)";
  g.fill();
  g.lineWidth = 2;
  g.strokeStyle = color;
  g.stroke();
  // mira fina no centro: o ponto exato é o centro, não a bolinha
  g.strokeStyle = active ? "#000" : "#fff";
  g.lineWidth = 1;
  line(g, [p[0] - 4, p[1]], [p[0] + 4, p[1]]);
  line(g, [p[0], p[1] - 4], [p[0], p[1] + 4]);
  if (label) {
    g.font = "600 10px Inter, system-ui, sans-serif";
    g.fillStyle = "#fff";
    g.textAlign = "left";
    g.fillText(label, p[0] + HANDLE + 4, p[1] - HANDLE);
  }
  g.restore();
}

function loupe(
  g: CanvasRenderingContext2D,
  img: HTMLImageElement,
  center: Point, // ponto sob o cursor, em px da foto
  pointer: Point, // cursor, em px de tela
  scale: number, // px de tela por px da foto
  size: { w: number; h: number },
  edges: Point[], // polígono em px da foto
) {
  const R = 72;
  const Z = 4; // aumento em relação ao que está na tela
  const cx = pointer[0] < size.w / 2 ? size.w - R - 12 : R + 12;
  const cy = R + 12;
  const k = scale * Z; // px da lupa por px da foto
  const toLoupe = (p: Point): Point => [cx + (p[0] - center[0]) * k, cy + (p[1] - center[1]) * k];
  g.save();
  g.beginPath();
  g.arc(cx, cy, R, 0, Math.PI * 2);
  g.clip();
  g.fillStyle = "#000";
  g.fillRect(cx - R, cy - R, R * 2, R * 2);
  g.imageSmoothingEnabled = false;
  const half = R / k;
  g.drawImage(img, center[0] - half, center[1] - half, half * 2, half * 2, cx - R, cy - R, R * 2, R * 2);
  if (edges.length) {
    g.strokeStyle = "#fbbf24";
    g.lineWidth = 1.5;
    poly(g, edges.map(toLoupe));
    g.stroke();
  }
  g.strokeStyle = "#fff";
  g.lineWidth = 1;
  line(g, [cx - 12, cy], [cx - 3, cy]);
  line(g, [cx + 3, cy], [cx + 12, cy]);
  line(g, [cx, cy - 12], [cx, cy - 3]);
  line(g, [cx, cy + 3], [cx, cy + 12]);
  g.restore();
  g.beginPath();
  g.arc(cx, cy, R, 0, Math.PI * 2);
  g.lineWidth = 2;
  g.strokeStyle = "#fbbf24";
  g.stroke();
}

function hexA(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function round2(v: number) {
  return Math.round(v * 100) / 100;
}
