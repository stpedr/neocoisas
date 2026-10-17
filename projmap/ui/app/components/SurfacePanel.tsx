"use client";

import { useState } from "react";
import { api } from "../lib/api";
import { validateQuad } from "../lib/geometry";
import type { MediaItem, Project, SourceKind, Surface } from "../lib/types";
import { DEFAULT_COLOR } from "../lib/types";
import AudioFxSection from "./AudioFxSection";
import ColorControls, { isNeutral } from "./ColorControls";
import ColorPresets from "./ColorPresets";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Input } from "./ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Slider } from "./ui/slider";

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
  { id: "capture", label: "Entrada de vídeo (câmera/captura)" },
  { id: "motion", label: "Motion (HTML)" },
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
  motion: ".html,.htm,text/html",
};

const UPLOAD_LABEL: Record<"video" | "gif" | "image" | "motion", string> = {
  video: "Vídeo",
  gif: "GIF",
  image: "Imagem",
  motion: "Motion",
};

const isMediaKind = (k: SourceKind) => k === "video" || k === "gif" || k === "image" || k === "motion";

export default function SurfacePanel({ surface: s, project, onChange, onDelete, onUpload, onError, onOpenGallery }: Props) {
  // Tipo escolhido que ainda não tem arquivo no projeto: a superfície continua
  // como está até o upload (o servidor recusa "vídeo" sem mídia).
  const [wantKind, setWantKind] = useState<SourceKind | null>(null);
  const shownKind = wantKind ?? s.source.kind;
  const media = Object.values(project.media).filter((m) => m.kind === shownKind);
  const needsMedia = isMediaKind(shownKind);

  const setKind = (kind: SourceKind) => {
    const isMedia = isMediaKind(kind);
    const keep = s.source.media && project.media[s.source.media]?.kind === kind ? s.source.media : null;
    const sha = keep ?? Object.values(project.media).find((m) => m.kind === kind)?.sha256 ?? null;
    if (isMedia && !sha) {
      setWantKind(kind);
      return;
    }
    setWantKind(null);
    onChange((cur) => ({
      ...cur,
      source: { ...cur.source, kind, media: isMedia ? sha : null, ...(kind === "capture" ? { device: cur.source.device || "auto" } : {}) },
    }));
  };

  const node = project.nodes.find((n) => n.id === s.node_id);
  const fullscreen = () => {
    if (!node) return;
    const { width: w, height: h } = node.output;
    onChange((c) => ({ ...c, warp: { ...c.warp, base: [[0, 0], [w, 0], [w, h], [0, h]] } }));
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
    <div className="flex flex-col gap-2 border-t border-border pt-2.5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="m-0 text-[15px] font-semibold text-foreground">{s.label || s.id}</h2>
        <label className="flex items-center gap-2 text-sm text-foreground">
          <Checkbox
            checked={s.visible}
            onCheckedChange={(v) => onChange((c) => ({ ...c, visible: v === true }))}
            aria-label="Visível"
          />
          Visível
        </label>
      </div>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        Nome
        <Input value={s.label} onChange={(e) => onChange((c) => ({ ...c, label: e.target.value }))} />
      </label>

      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        Fonte
        <Select value={shownKind} onValueChange={(v) => setKind(v as SourceKind)}>
          <SelectTrigger aria-label="Fonte">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {KINDS.map((k) => (
              <SelectItem key={k.id} value={k.id}>
                {k.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      {/* Galeria (miniaturas, pastas do Drive, sugestões) no lugar da lista suspensa */}
      {(() => {
        const cur = s.source.media ? project.media[s.source.media] : undefined;
        return (
          <button
            className="flex w-full items-center gap-2.5 rounded-radius-sm border border-dashed border-border-strong bg-secondary p-1.5 text-left hover:border-primary"
            onClick={() =>
              onOpenGallery((item) => {
                setWantKind(null);
                onChange((c) => ({ ...c, source: { ...c.source, kind: item.kind, media: item.sha256 } }));
              })
            }
          >
            {cur ? (
              <img src={api.mediaThumbUrl(cur.sha256)} alt="" className="h-10 w-16 shrink-0 rounded bg-black object-cover" />
            ) : (
              <span className="grid h-10 w-16 shrink-0 place-items-center rounded bg-black">🖼</span>
            )}
            <span className="flex min-w-0 flex-col text-foreground">
              <b className="truncate text-sm">{cur ? cur.filename : "Escolher na galeria"}</b>
              <span className="text-xs text-muted-foreground">{cur ? "trocar mídia" : "vídeos e fotos do projeto e das suas pastas"}</span>
            </span>
          </button>
        );
      })()}
      {needsMedia && media.length === 0 && !s.source.media && (
        <p className="m-0 text-xs text-muted-foreground">Nenhum arquivo deste tipo no projeto ainda: escolha na galeria ou envie abaixo.</p>
      )}

      <div className="flex flex-wrap gap-1.5">
        {(["video", "gif", "image", "motion"] as const).map((k) => (
          <label
            key={k}
            className="inline-flex h-[30px] cursor-pointer items-center rounded-radius-sm border border-border-strong bg-secondary px-2.5 text-xs font-semibold text-foreground hover:border-primary"
            title={k === "motion" ? "Motion Module v1 (.html): visual audio-reativo do Motion Studio ou gerado com Claude" : undefined}
          >
            + {UPLOAD_LABEL[k]}
            <input type="file" accept={ACCEPT[k]} hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
        ))}
      </div>

      {s.source.kind === "color" && (
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Cor
          <input
            type="color"
            className="h-9 w-full rounded-md border border-border bg-secondary p-0.5"
            value={rgbToHex(s.source.color)}
            onChange={(e) => onChange((c) => ({ ...c, source: { ...c.source, color: hexToRgb(e.target.value) } }))}
          />
        </label>
      )}

      {s.source.kind === "motion" && (
        <label
          className="flex flex-col gap-1 text-xs text-muted-foreground"
          title="Câmera ou placa de captura entregue ao motion (motion:video). Vazio = o motion não recebe vídeo."
        >
          Entrada de vídeo do motion
          <Input
            value={s.source.device ?? ""}
            placeholder="nenhuma · auto · índice ou parte do nome"
            maxLength={128}
            onChange={(e) => {
              const device = e.target.value;
              onChange((c) => ({ ...c, source: { ...c.source, device: device || null } }));
            }}
          />
        </label>
      )}

      {s.source.kind === "capture" && (
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" title="Webcam ou placa de captura HDMI deste PC">
          Dispositivo
          <Input
            value={s.source.device ?? ""}
            placeholder="auto (primeira câmera física), índice ou parte do nome"
            maxLength={128}
            onChange={(e) => {
              const device = e.target.value;
              onChange((c) => ({ ...c, source: { ...c.source, device } }));
            }}
          />
        </label>
      )}

      {needsMedia && s.source.kind === shownKind && (
        <div className="flex items-end gap-2">
          <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs text-muted-foreground">
            Ajuste
            <Select
              value={s.source.fit}
              onValueChange={(v) => onChange((c) => ({ ...c, source: { ...c.source, fit: v as Surface["source"]["fit"] } }))}
            >
              <SelectTrigger aria-label="Ajuste">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="stretch">Esticar</SelectItem>
                <SelectItem value="cover">Preencher (corta)</SelectItem>
                <SelectItem value="contain">Caber (tarjas)</SelectItem>
              </SelectContent>
            </Select>
          </label>
          {shownKind !== "image" && shownKind !== "motion" && (
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Velocidade
              <Input
                type="number"
                min={0.1}
                max={16}
                step={0.1}
                className="w-20"
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

      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        <span className="flex justify-between gap-2">
          Opacidade <span>{Math.round(s.opacity * 100)}%</span>
        </span>
        <Slider min={0} max={1} step={0.01} value={[s.opacity]} aria-label="Opacidade"
          onValueChange={([v]) => onChange((c) => ({ ...c, opacity: v }))} />
      </label>
      <label
        className="flex flex-col gap-1 text-xs text-muted-foreground"
        title="Esmaece as bordas da superfície até o preto: some com a 'moldura' dura e funde com a parede"
      >
        <span className="flex justify-between gap-2">
          Borda suave <span>{s.feather > 0 ? `${Math.round(s.feather * 100)}%` : "desligada"}</span>
        </span>
        <Slider min={0} max={0.5} step={0.005} value={[s.feather]} aria-label="Borda suave"
          onValueChange={([v]) => onChange((c) => ({ ...c, feather: v }))} />
      </label>
      <div className="flex items-end gap-2">
        <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs text-muted-foreground">
          Mistura
          <Select value={s.blend_mode} onValueChange={(v) => onChange((c) => ({ ...c, blend_mode: v as Surface["blend_mode"] }))}>
            <SelectTrigger aria-label="Mistura">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="normal">Normal</SelectItem>
              <SelectItem value="add">Somar (luz)</SelectItem>
              <SelectItem value="multiply">Multiplicar</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Camada (z)
          <Input
            type="number"
            step={1}
            className="w-20"
            value={s.z}
            onChange={(e) => onChange((c) => ({ ...c, z: Math.round(Number(e.target.value)) || 0 }))}
          />
        </label>
      </div>

      <details className="flex flex-col gap-2" open={(s.fx ?? []).length > 0}>
        <summary className="cursor-pointer text-xs text-muted-foreground">
          Efeitos de áudio{(s.fx ?? []).length ? ` · ${(s.fx ?? []).length}` : ""}
        </summary>
        <AudioFxSection fx={s.fx ?? []} onChange={(fx) => onChange((c) => ({ ...c, fx }))} />
      </details>

      <details className="flex flex-col gap-2" open={!isNeutral(s.color ?? DEFAULT_COLOR)}>
        <summary className="cursor-pointer text-xs text-muted-foreground">
          Imagem desta superfície (brilho, contraste, presets){isNeutral(s.color ?? DEFAULT_COLOR) ? "" : " · ajustada"}
        </summary>
        <p className="m-0 text-xs text-muted-foreground">Equilibre uma parede mais escura ou colorida que as outras. Soma-se ao ajuste do projetor.</p>
        <ColorPresets value={s.color ?? DEFAULT_COLOR} target="esta superfície" onError={onError}
                      onApply={(color) => onChange((c) => ({ ...c, color }))} />
        <ColorControls value={s.color ?? DEFAULT_COLOR} onChange={(color) => onChange((c) => ({ ...c, color }))} />
        {!isNeutral(s.color ?? DEFAULT_COLOR) && (
          <Button variant="default" size="sm" onClick={() => onChange((c) => ({ ...c, color: { ...DEFAULT_COLOR } }))}>
            Zerar ajustes
          </Button>
        )}
      </details>

      <details className="flex flex-col gap-1.5">
        <summary className="cursor-pointer text-xs text-muted-foreground">Cantos (px do projetor)</summary>
        {node && (
          <Button variant="default" size="sm" onClick={fullscreen} title="Mapeia a superfície na saída inteira do projetor">
            Tela cheia
          </Button>
        )}
        {s.warp.base.map((p, i) => (
          <div className="flex items-center gap-2" key={i}>
            <span className="w-6 text-[11px] font-bold text-muted-foreground">{["TL", "TR", "BR", "BL"][i]}</span>
            {[0, 1].map((axis) => (
              <Input
                key={axis}
                type="number"
                step={0.5}
                className="w-full"
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

      <Button
        variant="destructive"
        size="block"
        title="Atalho: tecla Delete com a superfície selecionada"
        onClick={onDelete}
      >
        Excluir superfície <span className="rounded border border-current px-1 text-[10px] font-bold opacity-80">Del</span>
      </Button>
    </div>
  );
}

function rgbToHex([r, g, b]: [number, number, number]) {
  return "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
