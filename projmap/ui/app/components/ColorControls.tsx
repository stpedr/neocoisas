"use client";

// Controles de ajuste de imagem: usados no card do projetor (vale para tudo),
// no painel da superfície (só ela) e, resumidos, no remote do celular.

import type { ColorAdjust } from "../lib/types";
import { DEFAULT_COLOR } from "../lib/types";

export const PRESETS: { name: string; hint: string; color: ColorAdjust }[] = [
  { name: "Original", hint: "sem ajuste", color: DEFAULT_COLOR },
  {
    name: "Ambiente claro",
    hint: "luz acesa / fim de tarde: realça médios e cores",
    color: { brightness: 1.1, contrast: 1.15, saturation: 1.2, gamma: 1.3, temperature: 0 },
  },
  {
    name: "Ambiente escuro",
    hint: "sala escura: pretos mais pretos, menos ofuscante",
    color: { brightness: 0.85, contrast: 1.1, saturation: 1.0, gamma: 0.9, temperature: 0 },
  },
  {
    name: "Cores vivas",
    hint: "festas, vitrines, conteúdo colorido",
    color: { brightness: 1.0, contrast: 1.15, saturation: 1.45, gamma: 1.05, temperature: 0 },
  },
  {
    name: "Parede amarelada",
    hint: "compensa parede creme/madeira (esfria a imagem)",
    color: { brightness: 1.05, contrast: 1.05, saturation: 1.1, gamma: 1.1, temperature: -0.45 },
  },
  {
    name: "Parede azulada",
    hint: "compensa parede fria/cinza-azulada (aquece a imagem)",
    color: { brightness: 1.05, contrast: 1.05, saturation: 1.1, gamma: 1.1, temperature: 0.45 },
  },
];

const FIELDS: { key: keyof ColorAdjust; label: string; min: number; max: number; step: number; fmt: (v: number) => string; tip: string }[] = [
  { key: "brightness", label: "Brilho", min: 0, max: 2, step: 0.01, fmt: pct, tip: "Clareia tudo. Acima de 100% os brancos estouram: para clarear sem estourar, use Médios." },
  { key: "gamma", label: "Médios (gama)", min: 0.4, max: 2.5, step: 0.01, fmt: (v) => v.toFixed(2), tip: "Acima de 1 clareia sombras e médios sem estourar o branco: o melhor ajuste para ambiente claro." },
  { key: "contrast", label: "Contraste", min: 0, max: 2, step: 0.01, fmt: pct, tip: "Separação entre claros e escuros." },
  { key: "saturation", label: "Saturação", min: 0, max: 2, step: 0.01, fmt: pct, tip: "Intensidade das cores. 0% = preto e branco." },
  { key: "temperature", label: "Temperatura", min: -1, max: 1, step: 0.01, fmt: temp, tip: "Esfria (azul) ou aquece (amarelo). Use para compensar a cor da parede." },
];

export default function ColorControls({ value, onChange, compact = false }: {
  value: ColorAdjust;
  onChange: (c: ColorAdjust) => void;
  compact?: boolean;
}) {
  const fields = compact ? FIELDS.filter((f) => f.key !== "temperature" && f.key !== "contrast") : FIELDS;
  return (
    <div className="color-controls">
      {fields.map((f) => (
        <label key={f.key} className="slider" title={f.tip}>
          <span className="color-row">
            {f.label} <span className="dim">{f.fmt(value[f.key])}</span>
          </span>
          <input type="range" min={f.min} max={f.max} step={f.step} value={value[f.key]}
                 onChange={(e) => onChange({ ...value, [f.key]: Number(e.target.value) })}
                 onDoubleClick={() => onChange({ ...value, [f.key]: DEFAULT_COLOR[f.key] })} />
        </label>
      ))}
    </div>
  );
}

export function isNeutral(c: ColorAdjust) {
  return (Object.keys(DEFAULT_COLOR) as (keyof ColorAdjust)[]).every((k) => Math.abs(c[k] - DEFAULT_COLOR[k]) < 1e-6);
}

/** Aproximação para a prévia do editor (canvas 2D não tem gama/temperatura). */
export function cssFilter(...cs: ColorAdjust[]): string {
  let b = 1, c = 1, s = 1, sepia = 0, hue = 0;
  for (const x of cs) {
    b *= x.brightness * (1 + (x.gamma - 1) * 0.35);
    c *= x.contrast;
    s *= x.saturation;
    if (x.temperature > 0) sepia += x.temperature * 0.35;
    else hue += x.temperature * -18;
  }
  const parts = [`brightness(${b.toFixed(3)})`, `contrast(${c.toFixed(3)})`, `saturate(${s.toFixed(3)})`];
  if (sepia > 0) parts.push(`sepia(${Math.min(1, sepia).toFixed(3)})`);
  if (hue) parts.push(`hue-rotate(${hue.toFixed(1)}deg)`);
  return parts.join(" ");
}

function pct(v: number) {
  return `${Math.round(v * 100)}%`;
}

function temp(v: number) {
  if (Math.abs(v) < 0.02) return "neutra";
  return v > 0 ? `quente +${Math.round(v * 100)}` : `fria ${Math.round(v * 100)}`;
}
