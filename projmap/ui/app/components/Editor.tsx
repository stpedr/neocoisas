"use client";

// Editor de mapeamento em canvas 2D (mouse e toque via Pointer Events).
//
// Duas vistas sobre o MESMO dado (quads em pixels do projetor):
//  - "photo": a foto tirada da posição do projetor; os quads são mostrados
//    através da homografia projetor→foto (inversa da "área projetada").
//  - "projector": o quadro do projetor em si (para ajuste fino olhando a parede).
// Arrastar em qualquer vista converte de volta para pixels do projetor; o
// renderer do nó e a parede atualizam no frame seguinte.
//
// F9: as mídias (fundo + camadas) aparecem DENTRO das superfícies, em
// perspectiva e animadas (vídeo/GIF), como no MadMapper. Com uma camada
// selecionada, o retângulo dela ganha alças: arrastar um canto redimensiona
// mantendo a proporção (Shift libera) e arrastar por dentro move.
//
// Superfície selecionada ganha duas alças acima da borda de cima (estilo
// MindManager): a quadrada escala (puxar para fora aumenta, para dentro
// diminui) e a redonda gira (Shift = passos de 15°), sempre em torno do centro.

import { useCallback, useEffect, useRef, useState } from "react";
import { applyH, homography4, invert3, pointInQuad, validateQuad, type Mat3 } from "../lib/geometry";
import {
  drawableFor, drawWarpedImage, quadAspect, setMediaReadyCallback, textureRegion, unlockVideos, type UvToScreen,
} from "../lib/preview";
import type { DetectCandidate, Layer, MediaItem, Node, Point, SourceSpec, Surface } from "../lib/types";
import { DEFAULT_COLOR } from "../lib/types";
import { cssFilter, isNeutral } from "./ColorControls";

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
  media: Record<string, MediaItem>;
  showMedia: boolean;
  selectedLayerId: string | null;
  onLayerRect: (surfaceId: string, layerId: string, rect: Layer["rect"]) => void;
  candidates?: DetectCandidate[];
  candidateOn?: Set<number>;
  onToggleCandidate?: (i: number) => void;
}

const UNIT: Point[] = [[0, 0], [1, 0], [1, 1], [0, 1]];
const rectCorners = ([x, y, w, h]: Layer["rect"]): Point[] => [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];

type Drag =
  | { kind: "corner"; id: string; corner: number; quadView: Point[] }
  | { kind: "scale"; id: string; quadView: Point[]; center: Point; dir: Point; start: Point }
  | { kind: "rotate"; id: string; quadView: Point[]; center: Point; centerScreen: Point; startAngle: number }
  | { kind: "move"; id: string; start: Point; quadView: Point[] }
  | { kind: "boundary"; corner: number }
  | { kind: "layerCorner"; sid: string; lid: string; corner: number; start: Layer["rect"] }
  | { kind: "layerMove"; sid: string; lid: string; startUv: Point; start: Layer["rect"] };

export default function Editor(props: Props) {
  const { node, surfaces, view, mode, photo, photoToProj, selectedId, selectedCorner } = props;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 450, dpr: 1 });
  const dragRef = useRef<Drag | null>(null);
  const [pointer, setPointer] = useState<Point | null>(null); // em px de tela, para a lupa
  const lastReject = useRef(0);
  const drawRef = useRef<() => void>(() => {});
  const animatedRef = useRef(false);
  const liveRef = useRef<string>(""); // "120%" / "15°" durante escala/giro

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

  // uv da superfície → tela, passando por projetor → vista.
  const uvMapper = useCallback(
    (s: Surface): UvToScreen | null => {
      const h = homography4(UNIT, s.warp.base as Point[]);
      if (!h) return null;
      return (u, v) => viewToScreen(projToView(applyH(h, [u, v])));
    },
    [viewToScreen, projToView],
  );

  // Candidato (foto normalizada) → tela, passando pelo projetor: vale nas duas vistas.
  const candidateScreen = (c: DetectCandidate): Point[] | null => {
    if (!photo || !photoToProj) return null;
    return c.quad.map(([x, y]) =>
      viewToScreen(projToView(applyH(photoToProj, [x * photo.naturalWidth, y * photo.naturalHeight]))),
    );
  };

  // tela → uv da superfície (para arrastar camadas).
  const screenToUv = (s: Surface, sp: Point): Point | null => {
    const h = homography4(s.warp.base as Point[], UNIT);
    return h ? applyH(h, viewToProj(screenToView(sp))) : null;
  };

  // Laço de animação: só redesenha por frame quando há vídeo/GIF visível.
  useEffect(() => {
    setMediaReadyCallback(() => drawRef.current());
    let raf = 0;
    const tick = () => {
      if (animatedRef.current) drawRef.current();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      setMediaReadyCallback(() => {});
    };
  }, []);

  // ---- desenho (nas mudanças de estado e, havendo vídeo/GIF, a cada frame)
  useEffect(() => {
    drawRef.current = draw;
    draw();
    function draw() {
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
    let animated = false;
    const markAnimated = () => (animated = true);
    const ordered = [...surfaces].sort((a, b) => a.z - b.z);
    ordered.forEach((s) => {
      const idx = surfaces.indexOf(s);
      const color = COLORS[idx % COLORS.length];
      const pts = s.warp.base.map((p) => viewToScreen(projToView(p as Point)));
      const sel = s.id === selectedId;
      // Prévia da mídia: fundo e camadas, recortados pela superfície.
      let hasContent = false;
      const map = props.showMedia ? uvMapper(s) : null;
      if (map) {
        // Borda suave: pinta num canvas auxiliar e multiplica pela máscara
        // (mesma conta do shader: smoothstep(0, feather, distância à borda em uv)).
        const feather = s.feather > 0 ? featherLayer(cv.width, cv.height, size.dpr) : null;
        const gOut = g;
        const g2 = feather ? feather.g : g;
        const withCtx = (fn: (g: CanvasRenderingContext2D) => void) => fn(g2);
        withCtx((g) => {
        g.save();
        poly(g, pts);
        g.clip();
        const alpha = (s.visible ? 1 : 0.35) * s.opacity;
        const qa = quadAspect(s.warp.base as Point[]);
        // Ajuste de cor (superfície × projetor), aproximado com filtro CSS na prévia.
        const outColor = node.output.color ?? DEFAULT_COLOR;
        const surfColor = s.color ?? DEFAULT_COLOR;
        if (!isNeutral(outColor) || !isNeutral(surfColor)) g.filter = cssFilter(surfColor, outColor);
        hasContent = paint(g, s.source, [0, 0, 1, 1], qa, map, alpha, props.media, markAnimated);
        for (const layer of s.layers) {
          if (!layer.visible) continue;
          g.save();
          poly(g, rectCorners(layer.rect).map(([u, v]) => map(u, v)));
          g.clip();
          hasContent = paint(g, layer.source, layer.rect, qa, map, alpha * layer.opacity, props.media, markAnimated) || hasContent;
          g.restore();
        }
        g.restore();
        });
        if (feather) {
          applyFeather(feather.g, pts, s.feather);
          gOut.save();
          gOut.setTransform(1, 0, 0, 1, 0, 0);
          gOut.drawImage(feather.canvas, 0, 0);
          gOut.restore();
        }
      }
      g.save();
      g.globalAlpha = s.visible ? 1 : 0.35;
      poly(g, pts);
      // Com mídia à mostra, o véu colorido some (só um toque na selecionada).
      g.fillStyle = hexA(color, hasContent ? (sel ? 0.1 : 0) : sel ? 0.28 : 0.16);
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
      if (sel && transformHandlesOn()) {
        const th = transformHandles(pts);
        g.save();
        g.strokeStyle = color;
        g.lineWidth = 1.5;
        line(g, th.mid, th.rotate);
        // escala: quadrado com seta dupla
        g.fillStyle = "rgba(5,7,11,.85)";
        g.beginPath();
        g.roundRect(th.scale[0] - 11, th.scale[1] - 11, 22, 22, 5);
        g.fill();
        g.lineWidth = 2;
        g.stroke();
        // giro: círculo com seta curva
        g.beginPath();
        g.arc(th.rotate[0], th.rotate[1], 11, 0, Math.PI * 2);
        g.fill();
        g.stroke();
        g.fillStyle = "#fff";
        g.font = "700 13px Inter, system-ui, sans-serif";
        g.textAlign = "center";
        g.textBaseline = "middle";
        g.fillText("↕", th.scale[0], th.scale[1] + 1);
        g.fillText("⟳", th.rotate[0], th.rotate[1] + 1);
        const d = dragRef.current;
        if (d && (d.kind === "scale" || d.kind === "rotate") && d.id === s.id && liveRef.current) {
          g.font = "600 12px Inter, system-ui, sans-serif";
          g.shadowColor = "rgba(0,0,0,.9)";
          g.shadowBlur = 4;
          g.fillText(liveRef.current, th.rotate[0], th.rotate[1] - 22);
        }
        g.restore();
      }
    });

    animatedRef.current = animated;

    // Candidatos da detecção (F3): tracejado; os marcados ficam preenchidos.
    (props.candidates ?? []).forEach((c, i) => {
      const pts = candidateScreen(c);
      if (!pts) return;
      const on = props.candidateOn?.has(i) ?? false;
      const col = `rgb(${c.color.join(",")})`;
      g.save();
      poly(g, pts);
      g.fillStyle = on ? "rgba(52,211,153,0.28)" : "rgba(255,255,255,0.06)";
      g.fill();
      g.setLineDash(on ? [] : [7, 5]);
      g.lineWidth = on ? 2.5 : 1.5;
      g.strokeStyle = on ? "#34d399" : "rgba(255,255,255,0.85)";
      g.stroke();
      const ctr = pts.reduce((a, p) => [a[0] + p[0] / 4, a[1] + p[1] / 4], [0, 0]);
      g.setLineDash([]);
      g.beginPath();
      g.arc(ctr[0], ctr[1], 13, 0, Math.PI * 2);
      g.fillStyle = on ? "#34d399" : "rgba(5,7,11,.8)";
      g.fill();
      g.lineWidth = 2;
      g.strokeStyle = col;
      g.stroke();
      g.font = "700 12px Inter, system-ui, sans-serif";
      g.fillStyle = on ? "#05070b" : "#fff";
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(String(i + 1), ctr[0], ctr[1]);
      g.restore();
    });

    // Camada selecionada: retângulo deformado na superfície + alças.
    const selSurf = surfaces.find((s) => s.id === selectedId);
    const selLayer = selSurf?.layers.find((l) => l.id === props.selectedLayerId);
    const selMap = selSurf && selLayer && mode === "surfaces" ? uvMapper(selSurf) : null;
    if (selLayer && selMap) {
      const corners = rectCorners(selLayer.rect).map(([u, v]) => selMap(u, v));
      g.save();
      g.setLineDash([6, 4]);
      g.lineWidth = 2;
      g.strokeStyle = "#fff";
      poly(g, corners);
      g.stroke();
      g.setLineDash([]);
      for (const p of corners) {
        g.fillStyle = "#fff";
        g.strokeStyle = "#000";
        g.lineWidth = 1.5;
        g.fillRect(p[0] - 6, p[1] - 6, 12, 12);
        g.strokeRect(p[0] - 6, p[1] - 6, 12, 12);
      }
      const c = corners.reduce((a, p) => [a[0] + p[0] / 4, a[1] + p[1] / 4], [0, 0]);
      g.font = "600 11px Inter, system-ui, sans-serif";
      g.fillStyle = "#fff";
      g.textAlign = "center";
      g.shadowColor = "rgba(0,0,0,.9)";
      g.shadowBlur = 4;
      g.fillText(selLayer.label || selLayer.id, c[0], c[1] + 16);
      g.restore();
    }

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
    }
  }, [size, surfaces, node, view, mode, photo, usePhoto, viewW, viewH, viewToScreen, screenToView, projToView, uvMapper, scale,
      selectedId, selectedCorner, pointer, props.media, props.showMedia, props.selectedLayerId, props.candidates, props.candidateOn, photoToProj]);

  // ---- interação
  const eventPoint = (e: React.PointerEvent): Point => {
    const r = canvasRef.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };

  const onPointerDown = (e: React.PointerEvent) => {
    const sp = eventPoint(e);
    canvasRef.current!.setPointerCapture(e.pointerId);
    canvasRef.current!.focus();
    unlockVideos(); // o navegador só dá play depois de um gesto do usuário
    // Com candidatos da detecção na tela, clicar dentro de um marca/desmarca.
    if (mode === "surfaces" && props.candidates?.length && props.onToggleCandidate) {
      // o menor que contém o clique (uma porta dentro de uma parede)
      let hit = -1;
      let hitArea = Infinity;
      props.candidates.forEach((c, i) => {
        const pts = candidateScreen(c);
        if (pts && pointInQuad(sp, pts) && c.area < hitArea) {
          hit = i;
          hitArea = c.area;
        }
      });
      if (hit >= 0) {
        props.onToggleCandidate(hit);
        return;
      }
    }
    // Camada selecionada tem prioridade: alças dela, depois arrastar por dentro.
    if (mode === "surfaces" && props.selectedLayerId) {
      const s = surfaces.find((x) => x.id === selectedId);
      const layer = s?.layers.find((l) => l.id === props.selectedLayerId);
      const map = s ? uvMapper(s) : null;
      if (s && layer && map) {
        const corners = rectCorners(layer.rect).map(([u, v]) => map(u, v));
        const i = nearest(corners, sp);
        if (i !== null) {
          dragRef.current = { kind: "layerCorner", sid: s.id, lid: layer.id, corner: i, start: layer.rect };
          return;
        }
        const uv = screenToUv(s, sp);
        if (uv && pointInQuad(sp, corners)) {
          dragRef.current = { kind: "layerMove", sid: s.id, lid: layer.id, startUv: uv, start: layer.rect };
          return;
        }
      }
    }
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
    if (sel && transformHandlesOn()) {
      const quadView = sel.warp.base.map((p) => projToView(p as Point));
      const th = transformHandles(quadView.map(viewToScreen));
      const center = centroid(quadView);
      if (dist(sp, th.scale) <= 16) {
        dragRef.current = { kind: "scale", id: sel.id, quadView, center, dir: th.dir, start: sp };
        liveRef.current = "100%";
        return;
      }
      if (dist(sp, th.rotate) <= 16) {
        const cs = viewToScreen(center);
        dragRef.current = { kind: "rotate", id: sel.id, quadView, center, centerScreen: cs,
                            startAngle: Math.atan2(sp[1] - cs[1], sp[0] - cs[0]) };
        liveRef.current = "0°";
        return;
      }
    }
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
    const sp = eventPoint(e);
    if (!d) {
      hoverCursor(sp);
      return;
    }
    const vp = screenToView(sp);
    if (d.kind === "scale" || d.kind === "rotate") {
      let quadView: Point[];
      if (d.kind === "scale") {
        // projeção do arraste na direção "para fora" da borda de cima
        const along = (sp[0] - d.start[0]) * d.dir[0] + (sp[1] - d.start[1]) * d.dir[1];
        const f = Math.min(20, Math.max(0.05, Math.exp(along / 160)));
        liveRef.current = `${Math.round(f * 100)}%`;
        quadView = d.quadView.map(([x, y]) => [d.center[0] + (x - d.center[0]) * f, d.center[1] + (y - d.center[1]) * f] as Point);
      } else {
        let a = Math.atan2(sp[1] - d.centerScreen[1], sp[0] - d.centerScreen[0]) - d.startAngle;
        a = Math.atan2(Math.sin(a), Math.cos(a));
        if (e.shiftKey) a = (Math.round((a * 180) / Math.PI / 15) * 15 * Math.PI) / 180;
        liveRef.current = `${Math.round((a * 180) / Math.PI)}°`;
        const cos = Math.cos(a);
        const sin = Math.sin(a);
        quadView = d.quadView.map(([x, y]) => {
          const dx = x - d.center[0];
          const dy = y - d.center[1];
          return [d.center[0] + dx * cos - dy * sin, d.center[1] + dx * sin + dy * cos] as Point;
        });
      }
      const quad = quadView.map(viewToProj).map(([x, y]) => [round2(x), round2(y)] as Point);
      const err = validateQuad(quad);
      if (err) return reject(err);
      props.onQuad(d.id, quad);
      return;
    }
    if (d.kind === "layerCorner" || d.kind === "layerMove") {
      const s = surfaces.find((x) => x.id === d.sid);
      const uv = s ? screenToUv(s, sp) : null;
      if (!uv) return;
      const rect = d.kind === "layerMove" ? moveRect(d.start, d.startUv, uv) : resizeRect(d.start, d.corner, uv, !e.shiftKey);
      props.onLayerRect(d.sid, d.lid, rect);
      return;
    }
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

  // Cursor certo ao passar sobre as alças (o canvas é um elemento só).
  const hoverCursor = (sp: Point) => {
    const cv = canvasRef.current;
    if (!cv) return;
    let cursor = "crosshair";
    const sel = surfaces.find((s) => s.id === selectedId);
    if (sel && transformHandlesOn()) {
      const th = transformHandles(sel.warp.base.map((p) => viewToScreen(projToView(p as Point))));
      if (dist(sp, th.scale) <= 16) cursor = "ns-resize";
      else if (dist(sp, th.rotate) <= 16) cursor = "grab";
    }
    if (cv.style.cursor !== cursor) cv.style.cursor = cursor;
  };

  function transformHandlesOn() {
    return mode === "surfaces" && !props.selectedLayerId && !(props.candidates?.length);
  }

  const onPointerUp = (e: React.PointerEvent) => {
    liveRef.current = "";
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

function centroid(pts: Point[]): Point {
  return pts.reduce((a, p) => [a[0] + p[0] / pts.length, a[1] + p[1] / pts.length], [0, 0] as Point);
}

function dist(a: Point, b: Point) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

/** Alças acima do meio da borda de cima (TL–TR), na direção "para fora". */
function transformHandles(pts: Point[]) {
  const mid: Point = [(pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2];
  const c = centroid(pts);
  let dir: Point = [mid[0] - c[0], mid[1] - c[1]];
  const len = Math.hypot(dir[0], dir[1]);
  dir = len > 1e-6 ? [dir[0] / len, dir[1] / len] : [0, -1];
  const at = (k: number): Point => [mid[0] + dir[0] * k, mid[1] + dir[1] * k];
  return { mid, dir, scale: at(26), rotate: at(56) };
}

// ------------------------------------------------------- borda suave (prévia)
let fLayer: { canvas: HTMLCanvasElement; g: CanvasRenderingContext2D } | null = null;
function featherLayer(w: number, h: number, dpr: number) {
  if (!fLayer) {
    const canvas = document.createElement("canvas");
    fLayer = { canvas, g: canvas.getContext("2d")! };
  }
  const { canvas, g } = fLayer;
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.globalCompositeOperation = "source-over";
  g.filter = "none";
  g.clearRect(0, 0, w, h);
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  return fLayer;
}

/** Multiplica o que já está no canvas por uma rampa em cada borda do quad
 * (smoothstep, como o shader). Cada borda é um gradiente linear perpendicular a
 * ela, com largura = feather × distância até a borda oposta: aproxima a conta em
 * uv do shader sem emendas de malha. */
function applyFeather(g: CanvasRenderingContext2D, pts: Point[], f: number) {
  const c = centroid(pts);
  g.save();
  g.globalCompositeOperation = "destination-in";
  for (let i = 0; i < 4; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % 4];
    const oa = pts[(i + 2) % 4];
    const ob = pts[(i + 3) % 4];
    const mid: Point = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    let n: Point = [-(b[1] - a[1]), b[0] - a[0]];
    const len = Math.hypot(n[0], n[1]) || 1;
    n = [n[0] / len, n[1] / len];
    if ((c[0] - mid[0]) * n[0] + (c[1] - mid[1]) * n[1] < 0) n = [-n[0], -n[1]];
    const opp: Point = [(oa[0] + ob[0]) / 2, (oa[1] + ob[1]) / 2];
    const w = Math.max(0.5, f * Math.abs((opp[0] - mid[0]) * n[0] + (opp[1] - mid[1]) * n[1]));
    const grad = g.createLinearGradient(mid[0], mid[1], mid[0] + n[0] * w, mid[1] + n[1] * w);
    for (let k = 0; k <= 8; k++) {
      const t = k / 8;
      grad.addColorStop(t, `rgba(0,0,0,${(t * t * (3 - 2 * t)).toFixed(4)})`);
    }
    g.fillStyle = grad;
    g.beginPath();
    poly(g, pts);
    g.fill();
  }
  g.restore();
}

function hexA(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function round2(v: number) {
  return Math.round(v * 100) / 100;
}

// ------------------------------------------------------------ prévia (F9)
// Pinta uma fonte ocupando `rect` (uv da superfície). Devolve se desenhou algo.
function paint(
  g: CanvasRenderingContext2D,
  spec: SourceSpec,
  rect: Layer["rect"],
  qAspect: number,
  map: UvToScreen,
  alpha: number,
  media: Record<string, MediaItem>,
  markAnimated: () => void,
): boolean {
  const d = drawableFor(spec, media);
  if (!d || alpha <= 0) return false;
  g.save();
  g.globalAlpha = alpha;
  const [x, y, w, h] = rect;
  if (d.kind === "color") {
    poly(g, rectCorners(rect).map(([u, v]) => map(u, v)));
    g.fillStyle = d.color;
    g.fill();
  } else if (d.kind === "image") {
    if (d.animated) markAnimated();
    drawWarpedImage(g, d.el, d.w, d.h, textureRegion(rect, spec.fit, d.w / d.h, qAspect), map);
  } else {
    const c = map(x + w / 2, y + h / 2);
    g.font = "600 12px Inter, system-ui, sans-serif";
    g.fillStyle = "rgba(255,255,255,.75)";
    g.textAlign = "center";
    g.fillText(d.text, c[0], c[1] + 18);
  }
  g.restore();
  return true;
}

const MIN_SIDE = 0.01;

function moveRect(start: Layer["rect"], from: Point, to: Point): Layer["rect"] {
  const [x, y, w, h] = start;
  return roundRect([x + to[0] - from[0], y + to[1] - from[1], w, h]);
}

// O canto oposto fica parado. `keep`: mantém a proporção do início do arraste.
function resizeRect(start: Layer["rect"], corner: number, p: Point, keep: boolean): Layer["rect"] {
  const opp = rectCorners(start)[(corner + 2) % 4];
  let w = Math.max(MIN_SIDE, Math.abs(p[0] - opp[0]));
  let h = Math.max(MIN_SIDE, Math.abs(p[1] - opp[1]));
  if (keep) {
    const r = start[2] / start[3];
    if (w / r > h) h = w / r;
    else w = h * r;
  }
  const x = p[0] >= opp[0] ? opp[0] : opp[0] - w;
  const y = p[1] >= opp[1] ? opp[1] : opp[1] - h;
  return roundRect([x, y, w, h]);
}

function roundRect(r: Layer["rect"]): Layer["rect"] {
  return r.map((v) => Math.round(v * 10000) / 10000) as Layer["rect"];
}
