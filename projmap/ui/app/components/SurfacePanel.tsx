"use client";

import { useState } from "react";
import { api } from "../lib/api";
import { validateQuad } from "../lib/geometry";
import type { MediaItem, Project, SourceKind, Surface } from "../lib/types";

interface Props {
  surface: Surface;
  project: Project;
  onChange: (fn: (s: Surface) => Surface) => void;
  onDelete: () => void;
  onUpload: (file: File) => Promise<MediaItem>;
  onError: (msg: string) => void;
  /** Abre a galeria; a mídia escolhida vira o fundo da superfície. */
  onOpenGallery: (onPick: (item: MediaItem) => void) => void;
}

const KINDS: { id: SourceKind; label: string }[] = [
  { id: "video", label: "Vídeo" },
  { id: "gif", label: "GIF animado" },
  { id: "image", label: "Imagem" },
  { id: "color", label: "Cor sólida" },
  { id: "test", label: "Cartela de teste" },
  { id: "interactive", label: "Cena interativa (IA + sensores)" },
  { id: "none", label: "Nada (preto)" },
];

const ACCEPT: Record<string, string> = {
  video: "video/*,.mp4,.mov,.mkv,.webm,.m4v,.avi",
  gif: "image/gif",
  image: "image/png,image/jpeg,image/webp,image/bmp",
};

export default function SurfacePanel({ surface: s, project, onChange, onDelete, onUpload, onError, onOpenGallery }: Props) {
  // Tipo escolhido que ainda não tem arquivo no projeto: a superfície continua
  // como está até o upload (o servidor recusa "vídeo" sem mídia).
  const [wantKind, setWantKind] = useState<SourceKind | null>(null);
  const shownKind = wantKind ?? s.source.kind;
  const media = Object.values(project.media).filter((m) => m.kind === shownKind);
  const needsMedia = shownKind === "video" || shownKind === "gif" || shownKind === "image";

  const setKind = (kind: SourceKind) => {
    const isMedia = kind === "video" || kind === "gif" || kind === "image";
    const keep = s.source.media && project.media[s.source.media]?.kind === kind ? s.source.media : null;
    const sha = keep ?? Object.values(project.media).find((m) => m.kind === kind)?.sha256 ?? null;
    if (isMedia && !sha) {
      setWantKind(kind);
      return;
    }
    setWantKind(null);
    onChange((cur) => ({ ...cur, source: { ...cur.source, kind, media: isMedia ? sha : null } }));
  };

  const upload = async (file: File) => {
    try {
      const item = await onUpload(file);
      setWantKind(null);
      onChange((cur) => ({ ...cur, source: { ...cur.source, kind: item.kind, media: item.sha256 } }));
    } catch (e) {
      onError(e instanceof Error ? e.message : "Falha no upload");
    }
  };

  return (
    <section className="card">
      <div className="card-head">
        <h2>Superfície</h2>
        <label className="toggle">
          <input type="checkbox" checked={s.visible} onChange={(e) => onChange((c) => ({ ...c, visible: e.target.checked }))} />
          Visível
        </label>
      </div>
      <label>
        Nome
        <input value={s.label} onChange={(e) => onChange((c) => ({ ...c, label: e.target.value }))} />
      </label>

      <label>
        Fonte
        <select value={shownKind} onChange={(e) => setKind(e.target.value as SourceKind)}>
          {KINDS.map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </select>
      </label>

      {/* Galeria (miniaturas, pastas do Drive, sugestões) no lugar da lista suspensa */}
      {(() => {
        const cur = s.source.media ? project.media[s.source.media] : undefined;
        return (
          <button
            className="media-pick"
            onClick={() =>
              onOpenGallery((item) => {
                setWantKind(null);
                onChange((c) => ({ ...c, source: { ...c.source, kind: item.kind, media: item.sha256 } }));
              })
            }
          >
            {cur ? <img src={api.mediaThumbUrl(cur.sha256)} alt="" /> : <span className="media-pick-empty">🖼</span>}
            <span>
              <b>{cur ? cur.filename : "Escolher na galeria"}</b>
              <span className="dim small">{cur ? "trocar mídia" : "vídeos e fotos do projeto e das suas pastas"}</span>
            </span>
          </button>
        );
      })()}
      {needsMedia && media.length === 0 && !s.source.media && (
        <p className="dim small">Nenhum arquivo deste tipo no projeto ainda: escolha na galeria ou envie abaixo.</p>
      )}

      <div className="upload-row">
        {(["video", "gif", "image"] as const).map((k) => (
          <label key={k} className="btn btn-small">
            + {k === "video" ? "Vídeo" : k === "gif" ? "GIF" : "Imagem"}
            <input type="file" accept={ACCEPT[k]} hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
        ))}
      </div>

      {s.source.kind === "color" && (
        <label>
          Cor
          <input
            type="color"
            value={rgbToHex(s.source.color)}
            onChange={(e) => onChange((c) => ({ ...c, source: { ...c.source, color: hexToRgb(e.target.value) } }))}
          />
        </label>
      )}

      {needsMedia && s.source.kind === shownKind && (
        <div className="row">
          <label>
            Ajuste
            <select
              value={s.source.fit}
              onChange={(e) => onChange((c) => ({ ...c, source: { ...c.source, fit: e.target.value as Surface["source"]["fit"] } }))}
            >
              <option value="stretch">Esticar</option>
              <option value="cover">Preencher (corta)</option>
              <option value="contain">Caber (tarjas)</option>
            </select>
          </label>
          {shownKind !== "image" && (
            <label>
              Velocidade
              <input
                type="number"
                min={0.1}
                max={16}
                step={0.1}
                value={s.source.speed}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (v > 0 && v <= 16) onChange((c) => ({ ...c, source: { ...c.source, speed: v } }));
                }}
              />
            </label>
          )}
        </div>
      )}

      <label className="slider">
        Opacidade <span className="dim">{Math.round(s.opacity * 100)}%</span>
        <input type="range" min={0} max={1} step={0.01} value={s.opacity} onChange={(e) => onChange((c) => ({ ...c, opacity: Number(e.target.value) }))} />
      </label>
      <label className="slider">
        Borda suave <span className="dim">{Math.round(s.feather * 100)}%</span>
        <input type="range" min={0} max={0.5} step={0.005} value={s.feather} onChange={(e) => onChange((c) => ({ ...c, feather: Number(e.target.value) }))} />
      </label>
      <div className="row">
        <label>
          Mistura
          <select value={s.blend_mode} onChange={(e) => onChange((c) => ({ ...c, blend_mode: e.target.value as Surface["blend_mode"] }))}>
            <option value="normal">Normal</option>
            <option value="add">Somar (luz)</option>
            <option value="multiply">Multiplicar</option>
          </select>
        </label>
        <label>
          Camada (z)
          <input type="number" step={1} value={s.z} onChange={(e) => onChange((c) => ({ ...c, z: Math.round(Number(e.target.value)) || 0 }))} />
        </label>
      </div>

      <details className="corners">
        <summary>Cantos (px do projetor)</summary>
        {s.warp.base.map((p, i) => (
          <div className="row" key={i}>
            <span className="corner-tag">{["TL", "TR", "BR", "BL"][i]}</span>
            {[0, 1].map((axis) => (
              <input
                key={axis}
                type="number"
                step={0.5}
                value={Math.round(p[axis] * 100) / 100}
                aria-label={`${["TL", "TR", "BR", "BL"][i]} ${axis ? "y" : "x"}`}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (!Number.isFinite(v)) return;
                  const base = s.warp.base.map((q, j) => (j === i ? (axis ? [q[0], v] : [v, q[1]]) : q)) as Surface["warp"]["base"];
                  const err = validateQuad(base);
                  if (err) return onError(`Canto recusado: ${err}`);
                  onChange((c) => ({ ...c, warp: { ...c.warp, base } }));
                }}
              />
            ))}
          </div>
        ))}
      </details>

      <button className="btn btn-danger btn-block" onClick={() => confirm(`Excluir "${s.label || s.id}"?`) && onDelete()}>
        Excluir superfície
      </button>
    </section>
  );
}

function rgbToHex([r, g, b]: [number, number, number]) {
  return "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
