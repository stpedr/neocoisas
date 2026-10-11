"use client";

// Camadas da superfície (F9): várias mídias numa superfície, cada uma com
// posição/tamanho próprios. A camada selecionada ganha alças no editor
// (arrastar canto = redimensionar mantendo a proporção; Shift libera).

import type { Layer, MediaItem, Project, SourceSpec, Surface } from "../lib/types";
import { DEFAULT_SOURCE } from "../lib/types";
import { mediaAspect, quadAspect } from "../lib/preview";
import { api } from "../lib/api";

interface Props {
  surface: Surface;
  project: Project;
  selectedLayerId: string | null;
  onSelectLayer: (id: string | null) => void;
  onChange: (fn: (s: Surface) => Surface) => void;
  onUpload: (file: File) => Promise<MediaItem>;
  onError: (msg: string) => void;
  onOpenGallery: (onPick: (item: MediaItem) => void) => void;
}

const ICON: Record<string, string> = { video: "🎬", gif: "🌀", image: "🖼", color: "■", test: "▦", interactive: "✦", none: "∅" };

export default function LayersPanel({ surface: s, project, selectedLayerId, onSelectLayer, onChange, onUpload, onError, onOpenGallery }: Props) {
  const layers = s.layers;
  const sel = layers.find((l) => l.id === selectedLayerId) ?? null;
  const media = Object.values(project.media);
  const qa = quadAspect(s.warp.base);

  const setLayers = (fn: (ls: Layer[]) => Layer[]) => onChange((c) => ({ ...c, layers: fn(c.layers) }));
  const patch = (id: string, changes: Partial<Layer>) =>
    setLayers((ls) => ls.map((l) => (l.id === id ? { ...l, ...changes } : l)));

  // Retângulo centralizado com a proporção da mídia (metade da largura da superfície).
  const fittedRect = (aspect: number, width = 0.5): Layer["rect"] => {
    const a = aspect > 0 ? aspect : 16 / 9;
    let w = width;
    let h = (w * qa) / a;
    if (h > 0.9) {
      h = 0.9;
      w = (h * a) / qa;
    }
    return [round((1 - w) / 2), round((1 - h) / 2), round(w), round(h)];
  };

  const addLayer = (item: MediaItem | null) => {
    const source: SourceSpec = item ? { ...DEFAULT_SOURCE, kind: item.kind, media: item.sha256 } : { ...DEFAULT_SOURCE, kind: "test" };
    const id = uniqueLayerId(s);
    const layer: Layer = {
      id,
      label: item ? item.filename : "Cartela",
      visible: true,
      source,
      rect: fittedRect(item ? mediaAspect(item) : 16 / 9),
      opacity: 1,
    };
    setLayers((ls) => [...ls, layer]);
    onSelectLayer(id);
  };

  const upload = async (file: File) => {
    try {
      addLayer(await onUpload(file));
    } catch (e) {
      onError(e instanceof Error ? e.message : "Falha no upload");
    }
  };

  const move = (id: string, delta: number) =>
    setLayers((ls) => {
      const i = ls.findIndex((l) => l.id === id);
      const j = i + delta;
      if (i < 0 || j < 0 || j >= ls.length) return ls;
      const next = [...ls];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const selMedia = sel?.source.media ? project.media[sel.source.media] : undefined;

  return (
    <section className="card">
      <div className="card-head">
        <h2>Camadas</h2>
        <span className="dim small">{layers.length ? `${layers.length} por cima do fundo` : "só o fundo"}</span>
      </div>

      {layers.length > 0 && (
        <ul className="layer-list">
          {/* topo da lista = desenhado por último (fica na frente) */}
          {[...layers].reverse().map((l) => (
            <li key={l.id} className={l.id === selectedLayerId ? "on" : ""}>
              <input type="checkbox" checked={l.visible} title="Visível"
                     onChange={(e) => patch(l.id, { visible: e.target.checked })} />
              <button className="layer-name" onClick={() => onSelectLayer(l.id === selectedLayerId ? null : l.id)}>
                {ICON[l.source.kind]} {l.label || l.id}
              </button>
              <button className="btn btn-small" title="Para frente" onClick={() => move(l.id, 1)}>▲</button>
              <button className="btn btn-small" title="Para trás" onClick={() => move(l.id, -1)}>▼</button>
            </li>
          ))}
        </ul>
      )}

      <div className="upload-row">
        <label className="btn btn-small">
          + Vídeo/foto/GIF
          <input type="file" accept="video/*,image/*,.mp4,.mov,.mkv,.webm,.m4v,.gif" hidden
                 onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
        </label>
        <button className="btn btn-small" onClick={() => onOpenGallery((m) => addLayer(m))}>+ Da galeria</button>
        <button className="btn btn-small" onClick={() => addLayer(null)}>+ Cartela</button>
      </div>

      {sel && (
        <div className="layer-props">
          <p className="dim small">
            No editor: arraste os quadrados brancos para redimensionar (Shift solta a proporção) e o meio para mover.
          </p>
          <label>
            Nome
            <input value={sel.label} onChange={(e) => patch(sel.id, { label: e.target.value })} />
          </label>
          <div className="row">
            <button className="media-pick" onClick={() => onOpenGallery((m) => patch(sel.id, { source: { ...sel.source, kind: m.kind, media: m.sha256 } }))}>
              {selMedia ? <img src={api.mediaThumbUrl(selMedia.sha256)} alt="" /> : <span className="media-pick-empty">{ICON[sel.source.kind]}</span>}
              <span>
                <b>{selMedia ? selMedia.filename : sel.source.kind === "color" ? "Cor sólida" : "Cartela de teste"}</b>
                <span className="dim small">trocar pela galeria</span>
              </span>
            </button>
          </div>
          <div className="upload-row">
            <button className="btn btn-small" onClick={() => patch(sel.id, { source: { ...sel.source, kind: "test", media: null } })}>▦ Cartela</button>
            <button className="btn btn-small" onClick={() => patch(sel.id, { source: { ...sel.source, kind: "color", media: null } })}>■ Cor</button>
          </div>
          {sel.source.kind === "color" && (
            <label>
              Cor
              <input type="color" value={rgbToHex(sel.source.color)}
                     onChange={(e) => patch(sel.id, { source: { ...sel.source, color: hexToRgb(e.target.value) } })} />
            </label>
          )}
          <div className="row">
            <label>
              Ajuste
              <select value={sel.source.fit} onChange={(e) => patch(sel.id, { source: { ...sel.source, fit: e.target.value as SourceSpec["fit"] } })}>
                <option value="stretch">Esticar no retângulo</option>
                <option value="contain">Caber</option>
                <option value="cover">Preencher (corta)</option>
              </select>
            </label>
            {(sel.source.kind === "video" || sel.source.kind === "gif") && (
              <label>
                Velocidade
                <input type="number" min={0.1} max={16} step={0.1} value={sel.source.speed}
                       onChange={(e) => { const v = Number(e.target.value); if (v > 0 && v <= 16) patch(sel.id, { source: { ...sel.source, speed: v } }); }} />
              </label>
            )}
          </div>
          <label className="slider">
            Opacidade <span className="dim">{Math.round(sel.opacity * 100)}%</span>
            <input type="range" min={0} max={1} step={0.01} value={sel.opacity}
                   onChange={(e) => patch(sel.id, { opacity: Number(e.target.value) })} />
          </label>
          <div className="row rect-row">
            {(["X", "Y", "Larg.", "Alt."] as const).map((name, i) => (
              <label key={name}>
                {name} %
                <input type="number" step={0.5} value={round(sel.rect[i] * 100, 2)}
                       onChange={(e) => {
                         const v = Number(e.target.value) / 100;
                         if (!Number.isFinite(v) || (i >= 2 && v < 0.01)) return;
                         const rect = [...sel.rect] as Layer["rect"];
                         rect[i] = v;
                         patch(sel.id, { rect });
                       }} />
              </label>
            ))}
          </div>
          <div className="upload-row">
            <button className="btn btn-small" onClick={() => patch(sel.id, { rect: [0, 0, 1, 1] })}>Preencher superfície</button>
            {selMedia && (
              <button className="btn btn-small" title="Corrige a altura para a proporção original da mídia"
                      onClick={() => {
                        const a = mediaAspect(selMedia);
                        if (!a) return onError("Mídia ainda carregando; tente de novo.");
                        const [x, y, w] = sel.rect;
                        patch(sel.id, { rect: [x, y, w, round((w * qa) / a)] });
                      }}>
                Proporção da mídia
              </button>
            )}
            <button className="btn btn-small" onClick={() => {
              const [, , w, h] = sel.rect;
              patch(sel.id, { rect: [round((1 - w) / 2), round((1 - h) / 2), w, h] });
            }}>Centralizar</button>
          </div>
          <button className="btn btn-danger btn-small" onClick={() => {
            setLayers((ls) => ls.filter((l) => l.id !== sel.id));
            onSelectLayer(null);
          }}>Remover camada</button>
        </div>
      )}
    </section>
  );
}

function uniqueLayerId(s: Surface) {
  const ids = new Set(s.layers.map((l) => l.id));
  let i = s.layers.length + 1;
  while (ids.has(`camada-${i}`)) i++;
  return `camada-${i}`;
}

function round(v: number, digits = 4) {
  const k = 10 ** digits;
  return Math.round(v * k) / k;
}

function rgbToHex([r, g, b]: [number, number, number]) {
  return "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
