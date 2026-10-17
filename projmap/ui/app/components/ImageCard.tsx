"use client";

// Imagem do projetor (conteúdo da gaveta): presets, ajustes finos e orientação
// (retroprojeção / teto). Vale para tudo o que o projetor mostra.

import type { Output } from "../lib/types";
import { DEFAULT_COLOR } from "../lib/types";
import ColorControls, { isNeutral } from "./ColorControls";
import ColorPresets from "./ColorPresets";
import { Button } from "./ui/button";

export default function ImageCard({
  output,
  onPatch,
  onError,
}: {
  output: Output;
  onPatch: (changes: Partial<Output>) => void;
  onError: (m: string) => void;
}) {
  const color = output.color ?? DEFAULT_COLOR;
  return (
    <>
      <p className="dim small">
        Vale para tudo o que o projetor mostra (os padrões de alinhamento continuam puros).
      </p>
      <ColorPresets
        value={color}
        target="o projetor"
        onError={onError}
        onApply={(c) => onPatch({ color: c })}
      />
      <details open={!isNeutral(color)}>
        <summary>Ajuste fino</summary>
        <ColorControls value={color} onChange={(c) => onPatch({ color: c })} />
        <p className="dim small">Duplo clique num controle volta ao padrão.</p>
        {!isNeutral(color) && (
          <Button size="sm" onClick={() => onPatch({ color: { ...DEFAULT_COLOR } })}>
            Zerar ajustes
          </Button>
        )}
      </details>
      <OrientationToggles output={output} onPatch={onPatch} />
    </>
  );
}

/** Retroprojeção / teto: também ficam na barra de cima, à mão. */
export function OrientationToggles({
  output,
  onPatch,
  compact = false,
}: {
  output: Output;
  onPatch: (changes: Partial<Output>) => void;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <div className="segmented orient-compact" role="group" aria-label="Orientação do projetor">
        <button
          className={output.flip_h ? "on" : ""}
          aria-pressed={output.flip_h}
          title="Retroprojeção: projetor ATRÁS de uma tela/tecido translúcido (a imagem sai espelhada)"
          onClick={() => onPatch({ flip_h: !output.flip_h })}
        >
          ⇋ Retroprojeção
        </button>
        <button
          className={output.flip_v ? "on" : ""}
          aria-pressed={output.flip_v}
          title="Projetor preso no teto, de cabeça para baixo (inverte a imagem)"
          onClick={() => onPatch({ flip_v: !output.flip_v })}
        >
          ⇅ Teto
        </button>
      </div>
    );
  }
  return (
    <div className="row orient-row" role="group" aria-label="Orientação do projetor">
      <Button
        size="sm"
        variant={output.flip_h ? "primary" : "default"}
        aria-pressed={output.flip_h}
        title="Retroprojeção: projetor ATRÁS de uma tela/tecido translúcido (a imagem sai espelhada)"
        onClick={() => onPatch({ flip_h: !output.flip_h })}
      >
        ⇋ Retroprojeção
      </Button>
      <Button
        size="sm"
        variant={output.flip_v ? "primary" : "default"}
        aria-pressed={output.flip_v}
        title="Projetor preso no teto, de cabeça para baixo (inverte a imagem)"
        onClick={() => onPatch({ flip_v: !output.flip_v })}
      >
        ⇅ Teto
      </Button>
    </div>
  );
}
