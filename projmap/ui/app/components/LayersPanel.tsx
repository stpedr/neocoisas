"use client";

// Camadas da superfície (F9): várias mídias numa superfície, cada uma com
// posição/tamanho próprios. A camada selecionada ganha alças no editor
// (arrastar canto = redimensionar mantendo a proporção; Shift libera).

import { motion, useReducedMotion } from "framer-motion";
import { api } from "../lib/api";
import { mediaAspect, quadAspect } from "../lib/preview";
import type { Layer, MediaItem, Project, SourceSpec, Surface } from "../lib/types";
import { DEFAULT_SOURCE } from "../lib/types";
import { cn } from "../lib/utils";
import { Button, buttonVariants } from "./ui/button";
import { Card, CardHeader, CardTitle } from "./ui/card";
import { Checkbox } from "./ui/checkbox";
import { Input } from "./ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Slider } from "./ui/slider";

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

const ICON: Record<string, string> = {
  video: "🎬",
  gif: "🌀",
  image: "🖼",
  color: "■",
  test: "▦",
  interactive: "✦",
  none: "∅",
};

export default function LayersPanel({
  surface: s,
  project,
  selectedLayerId,
  onSelectLayer,
  onChange,
  onUpload,
  onError,
  onOpenGallery,
}: Props) {
  const reduce = useReducedMotion();
  const layers = s.layers;
  const sel = layers.find((l) => l.id === selectedLayerId) ?? null;
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
    const source: SourceSpec = item
      ? { ...DEFAULT_SOURCE, kind: item.kind, media: item.sha256 }
      : { ...DEFAULT_SOURCE, kind: "test" };
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
    <Card className="rounded-radius-sm bg-secondary p-2.5">
      <CardHeader>
        <CardTitle className="text-xs">Camadas</CardTitle>
        <span className="text-xs text-muted-foreground">
          {layers.length ? `${layers.length} por cima do fundo` : "só o fundo"}
        </span>
      </CardHeader>

      {layers.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {/* topo da lista = desenhado por último (fica na frente) */}
          {[...layers].reverse().map((l) => (
            <motion.li
              key={l.id}
              layout={!reduce}
              transition={{ duration: 0.16, ease: "easeOut" }}
              className={cn(
                "flex items-center gap-1.5 rounded-lg border px-1.5 py-1",
                l.id === selectedLayerId ? "border-primary bg-primary/12" : "border-border",
              )}
            >
              <Checkbox
                checked={l.visible}
                title="Visível"
                aria-label={`Visível (${l.label || l.id})`}
                onCheckedChange={(v) => patch(l.id, { visible: v === true })}
              />
              <button
                type="button"
                className="min-w-0 flex-1 cursor-pointer truncate border-0 bg-transparent px-0.5 py-1 text-left text-[13px] text-foreground"
                onClick={() => onSelectLayer(l.id === selectedLayerId ? null : l.id)}
              >
                {ICON[l.source.kind]} {l.label || l.id}
              </button>
              <Button
                size="sm"
                className="h-[26px] px-2 py-0.5"
                title="Para frente"
                onClick={() => move(l.id, 1)}
              >
                ▲
              </Button>
              <Button
                size="sm"
                className="h-[26px] px-2 py-0.5"
                title="Para trás"
                onClick={() => move(l.id, -1)}
              >
                ▼
              </Button>
            </motion.li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-1.5">
        <label className={cn(buttonVariants({ size: "sm" }), "cursor-pointer text-foreground")}>
          + Vídeo/foto/GIF
          <input
            type="file"
            accept="video/*,image/*,.mp4,.mov,.mkv,.webm,.m4v,.gif"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void upload(f);
            }}
          />
        </label>
        <Button size="sm" onClick={() => onOpenGallery((m) => addLayer(m))}>
          + Da galeria
        </Button>
        <Button size="sm" onClick={() => addLayer(null)}>
          + Cartela
        </Button>
      </div>

      {sel && (
        <div className="flex flex-col gap-2 border-t border-border pt-2">
          <p className="m-0 text-xs text-muted-foreground">
            No editor: arraste os quadrados brancos para redimensionar (Shift solta a proporção) e o meio para mover.
          </p>
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Nome
            <Input value={sel.label} onChange={(e) => patch(sel.id, { label: e.target.value })} />
          </label>
          <div className="flex items-end gap-2">
            <button
              type="button"
              className="flex w-full cursor-pointer items-center gap-2.5 rounded-radius-sm border border-dashed border-border-strong bg-card p-1.5 text-left text-foreground hover:border-primary"
              onClick={() =>
                onOpenGallery((m) =>
                  patch(sel.id, { source: { ...sel.source, kind: m.kind, media: m.sha256 } }),
                )
              }
            >
              {selMedia ? (
                <img
                  src={api.mediaThumbUrl(selMedia.sha256)}
                  alt=""
                  className="h-10 w-16 flex-none rounded bg-black object-cover"
                />
              ) : (
                <span className="grid h-10 w-16 flex-none place-items-center rounded bg-black">
                  {ICON[sel.source.kind]}
                </span>
              )}
              <span className="flex min-w-0 flex-col">
                <b className="truncate text-[13px]">
                  {selMedia
                    ? selMedia.filename
                    : sel.source.kind === "color"
                      ? "Cor sólida"
                      : "Cartela de teste"}
                </b>
                <span className="text-xs text-muted-foreground">trocar pela galeria</span>
              </span>
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Button
              size="sm"
              onClick={() => patch(sel.id, { source: { ...sel.source, kind: "test", media: null } })}
            >
              ▦ Cartela
            </Button>
            <Button
              size="sm"
              onClick={() => patch(sel.id, { source: { ...sel.source, kind: "color", media: null } })}
            >
              ■ Cor
            </Button>
          </div>
          {sel.source.kind === "color" && (
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Cor
              <input
                type="color"
                value={rgbToHex(sel.source.color)}
                onChange={(e) =>
                  patch(sel.id, { source: { ...sel.source, color: hexToRgb(e.target.value) } })
                }
              />
            </label>
          )}
          <div className="flex items-end gap-2">
            <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs text-muted-foreground">
              Ajuste
              <Select
                value={sel.source.fit}
                onValueChange={(v) =>
                  patch(sel.id, { source: { ...sel.source, fit: v as SourceSpec["fit"] } })
                }
              >
                <SelectTrigger aria-label="Ajuste">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="stretch">Esticar no retângulo</SelectItem>
                  <SelectItem value="contain">Caber</SelectItem>
                  <SelectItem value="cover">Preencher (corta)</SelectItem>
                </SelectContent>
              </Select>
            </label>
            {(sel.source.kind === "video" || sel.source.kind === "gif") && (
              <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs text-muted-foreground">
                Velocidade
                <Input
                  type="number"
                  min={0.1}
                  max={16}
                  step={0.1}
                  value={sel.source.speed}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    if (v > 0 && v <= 16) patch(sel.id, { source: { ...sel.source, speed: v } });
                  }}
                />
              </label>
            )}
          </div>
          <div className="flex flex-col gap-1 text-xs text-muted-foreground">
            <div className="flex justify-between">
              <span>Opacidade</span>
              <span>{Math.round(sel.opacity * 100)}%</span>
            </div>
            <Slider
              aria-label="Opacidade"
              min={0}
              max={1}
              step={0.01}
              value={[sel.opacity]}
              onValueChange={([v]) => patch(sel.id, { opacity: v })}
            />
          </div>
          <div className="grid grid-cols-4 gap-2">
            {(["X", "Y", "Larg.", "Alt."] as const).map((name, i) => (
              <label key={name} className="flex min-w-0 flex-col gap-1 text-xs text-muted-foreground">
                {name} %
                <Input
                  type="number"
                  step={0.5}
                  value={round(sel.rect[i] * 100, 2)}
                  onChange={(e) => {
                    const v = Number(e.target.value) / 100;
                    if (!Number.isFinite(v) || (i >= 2 && v < 0.01)) return;
                    const rect = [...sel.rect] as Layer["rect"];
                    rect[i] = v;
                    patch(sel.id, { rect });
                  }}
                />
              </label>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Button size="sm" onClick={() => patch(sel.id, { rect: [0, 0, 1, 1] })}>
              Preencher superfície
            </Button>
            {selMedia && (
              <Button
                size="sm"
                title="Corrige a altura para a proporção original da mídia"
                onClick={() => {
                  const a = mediaAspect(selMedia);
                  if (!a) return onError("Mídia ainda carregando; tente de novo.");
                  const [x, y, w] = sel.rect;
                  patch(sel.id, { rect: [x, y, w, round((w * qa) / a)] });
                }}
              >
                Proporção da mídia
              </Button>
            )}
            <Button
              size="sm"
              onClick={() => {
                const [, , w, h] = sel.rect;
                patch(sel.id, { rect: [round((1 - w) / 2), round((1 - h) / 2), w, h] });
              }}
            >
              Centralizar
            </Button>
          </div>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => {
              setLayers((ls) => ls.filter((l) => l.id !== sel.id));
              onSelectLayer(null);
            }}
          >
            Remover camada
          </Button>
        </div>
      )}
    </Card>
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
