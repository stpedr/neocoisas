"use client";

// Detecção automática de superfícies na foto (F3). O mestre sugere regiões
// (muro, porta, colunas…); o operador marca as que quer e cria as superfícies
// de uma vez. Nada muda no projeto até clicar em "Criar".

import { useState } from "react";
import { api, ApiError } from "../lib/api";
import type { DetectCandidate } from "../lib/types";

interface Props {
  nodeId: string;
  hasPhoto: boolean;
  candidates: DetectCandidate[];
  selected: Set<number>;
  onResult: (cands: DetectCandidate[]) => void;
  onToggle: (i: number) => void;
  onCreate: () => void;
  onClear: () => void;
  onError: (msg: string) => void;
}

export default function DetectPanel(p: Props) {
  const [sensitivity, setSensitivity] = useState(0.5);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const { candidates } = await api.detect(p.nodeId, sensitivity);
      p.onResult(candidates);
      if (!candidates.length) p.onError("Nenhuma superfície encontrada. Tente aumentar a sensibilidade.");
    } catch (e) {
      p.onError(e instanceof ApiError ? e.message : "Falha na detecção (mestre offline?)");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <div className="card-head">
        <h2>Detectar superfícies</h2>
        {p.candidates.length > 0 && <button className="btn btn-small" onClick={p.onClear}>Limpar</button>}
      </div>
      <p className="dim small">
        Analisa a foto e sugere paredes, portas, colunas e painéis. Marque as que quer e crie as superfícies;
        depois é só ajustar os cantos.
      </p>
      <label className="slider">
        Sensibilidade <span className="dim">{sensitivity < 0.35 ? "poucas e grandes" : sensitivity > 0.65 ? "muitas e detalhadas" : "equilibrada"}</span>
        <input type="range" min={0} max={1} step={0.05} value={sensitivity} onChange={(e) => setSensitivity(Number(e.target.value))} />
      </label>
      <button className="btn btn-accent btn-block" disabled={!p.hasPhoto || busy} onClick={run}>
        {busy ? "Analisando a foto…" : p.hasPhoto ? "Detectar na foto" : "Envie a foto primeiro"}
      </button>

      {p.candidates.length > 0 && (
        <>
          <ul className="cand-list">
            {p.candidates.map((c, i) => (
              <li key={i}>
                <label className="toggle">
                  <input type="checkbox" checked={p.selected.has(i)} onChange={() => p.onToggle(i)} />
                  <span className="swatch" style={{ background: `rgb(${c.color.join(",")})` }} />
                  {c.label}
                </label>
                <span className="dim small" title="Quão retangular é a região (100% = quadrilátero perfeito)">
                  {Math.round(c.score * 100)}% · {Math.round(c.area * 100)}% da foto
                </span>
              </li>
            ))}
          </ul>
          <p className="dim small">Também dá para clicar numa região no editor para marcar/desmarcar.</p>
          <button className="btn btn-accent btn-block" disabled={p.selected.size === 0} onClick={p.onCreate}>
            Criar {p.selected.size} superfície{p.selected.size === 1 ? "" : "s"}
          </button>
        </>
      )}
    </section>
  );
}
