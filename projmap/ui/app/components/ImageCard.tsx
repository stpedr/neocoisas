"use client";

// Imagem do projetor: predefinições, ajustes finos e orientação (retroprojeção / teto).

import type { ColorAdjust, Output } from "../lib/types";
import { DEFAULT_COLOR } from "../lib/types";
import ColorControls, { isNeutral, PRESETS } from "./ColorControls";

export default function ImageCard({ output, onPatch }: { output: Output; onPatch: (changes: Partial<Output>) => void }) {
  const color = output.color ?? DEFAULT_COLOR;
  const active = PRESETS.find((p) => same(p.color, color));
  return (
    <section className="card">
      <div className="card-head">
        <h2>Imagem do projetor</h2>
        {!isNeutral(color) && <button className="btn btn-small" onClick={() => onPatch({ color: { ...DEFAULT_COLOR } })}>Zerar</button>}
      </div>
      <p className="dim small">Vale para tudo o que o projetor mostra (os padrões de alinhamento continuam puros).</p>
      <div className="preset-grid">
        {PRESETS.map((p) => (
          <button key={p.name} className={`btn btn-small ${active?.name === p.name ? "btn-accent" : ""}`} title={p.hint}
                  onClick={() => onPatch({ color: { ...p.color } })}>
            {p.name}
          </button>
        ))}
      </div>
      <details open={!active || active.name !== "Original"}>
        <summary>Ajuste fino</summary>
        <ColorControls value={color} onChange={(c) => onPatch({ color: c })} />
        <p className="dim small">Duplo clique num controle volta ao padrão.</p>
      </details>
      <div className="row orient-row">
        <label className="toggle" title="Projetor ATRÁS de uma tela/tecido translúcido: a imagem precisa sair espelhada">
          <input type="checkbox" checked={output.flip_h} onChange={(e) => onPatch({ flip_h: e.target.checked })} />
          Retroprojeção (espelhar)
        </label>
        <label className="toggle" title="Projetor preso no teto, de cabeça para baixo">
          <input type="checkbox" checked={output.flip_v} onChange={(e) => onPatch({ flip_v: e.target.checked })} />
          Projetor no teto (inverter)
        </label>
      </div>
    </section>
  );
}

function same(a: ColorAdjust, b: ColorAdjust) {
  return (Object.keys(a) as (keyof ColorAdjust)[]).every((k) => Math.abs(a[k] - b[k]) < 1e-6);
}
