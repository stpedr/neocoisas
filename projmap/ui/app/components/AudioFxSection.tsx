"use client";

// Efeitos reativos ao áudio de uma superfície (Surface.fx). Valem para qualquer
// fonte — vídeo ao vivo, arquivo, GIF, imagem — e seguem uma banda da entrada
// de áudio do show (project.audio). Fórmulas: projmap/mapping/fx.py.

import type { AudioBand, AudioFx, FxType } from "../lib/types";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Slider } from "./ui/slider";

export const MAX_FX = 8;

const TYPES: { id: FxType; label: string }[] = [
  { id: "pulse", label: "Pulsar (brilho)" },
  { id: "strobe", label: "Flash (strobe)" },
  { id: "hue", label: "Girar cores" },
  { id: "zoom", label: "Zoom" },
  { id: "rgb_split", label: "Separar RGB" },
  { id: "shake", label: "Tremer" },
  { id: "invert", label: "Inverter" },
];

const BANDS: { id: AudioBand; label: string }[] = [
  { id: "bass", label: "Graves" },
  { id: "mid", label: "Médios" },
  { id: "high", label: "Agudos" },
  { id: "level", label: "Volume" },
  { id: "beat", label: "Batida" },
];

const NEW_FX: AudioFx = { type: "pulse", band: "bass", amount: 0.5, enabled: true };

interface Props {
  fx: AudioFx[];
  onChange: (fx: AudioFx[]) => void;
}

export default function AudioFxSection({ fx, onChange }: Props) {
  const set = (i: number, patch: Partial<AudioFx>) => onChange(fx.map((f, j) => (j === i ? { ...f, ...patch } : f)));

  return (
    <div className="flex flex-col gap-2">
      {fx.length === 0 && (
        <p className="m-0 text-xs text-muted-foreground">
          Nenhum efeito. Adicione um para a superfície reagir à música (entrada de áudio do show).
        </p>
      )}
      {fx.map((f, i) => {
        const n = i + 1;
        return (
          <div key={i} className="flex flex-col gap-1.5 rounded-radius-sm border border-border p-2">
            <div className="flex items-center gap-2">
              <Select value={f.type} onValueChange={(v) => set(i, { type: v as FxType })}>
                <SelectTrigger aria-label={`Efeito ${n}`} className="min-w-0 flex-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TYPES.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={f.band} onValueChange={(v) => set(i, { band: v as AudioBand })}>
                <SelectTrigger aria-label={`Reage a ${n}`} className="w-28">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BANDS.map((b) => (
                    <SelectItem key={b.id} value={b.id}>
                      {b.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              <span className="flex justify-between gap-2">
                Intensidade <span>{Math.round(f.amount * 100)}%</span>
              </span>
              <Slider min={0} max={1} step={0.05} value={[f.amount]} aria-label={`Intensidade ${n}`}
                onValueChange={([v]) => set(i, { amount: v })} />
            </label>
            <div className="flex items-center justify-between gap-2">
              <label className="flex items-center gap-2 text-sm text-foreground">
                <Checkbox checked={f.enabled} aria-label={`Ligado ${n}`}
                  onCheckedChange={(v) => set(i, { enabled: v === true })} />
                Ligado
              </label>
              <Button variant="ghost" size="sm" aria-label={`Remover efeito ${n}`}
                onClick={() => onChange(fx.filter((_, j) => j !== i))}>
                Remover
              </Button>
            </div>
          </div>
        );
      })}
      {fx.length < MAX_FX && (
        <Button variant="default" size="sm" onClick={() => onChange([...fx, { ...NEW_FX }])}>
          + Efeito
        </Button>
      )}
    </div>
  );
}
