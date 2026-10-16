"use client";

// Detecção automática de superfícies na foto (F3). O mestre sugere regiões
// (muro, porta, colunas…); o operador marca as que quer e cria as superfícies
// de uma vez. Nada muda no projeto até clicar em "Criar".

import { useState } from "react";
import { api, ApiError } from "../lib/api";
import type { DetectCandidate } from "../lib/types";
import { Button } from "./ui/button";
import { Card, CardHeader, CardTitle } from "./ui/card";
import { Checkbox } from "./ui/checkbox";
import { Slider } from "./ui/slider";

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
    <Card>
      <CardHeader>
        <CardTitle>Detectar superfícies</CardTitle>
        {p.candidates.length > 0 && (
          <Button variant="default" size="sm" onClick={p.onClear}>
            Limpar
          </Button>
        )}
      </CardHeader>
      <p className="m-0 text-xs text-muted-foreground">
        Analisa a foto e sugere paredes, portas, colunas e painéis. Marque as que quer e crie as superfícies;
        depois é só ajustar os cantos.
      </p>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        <span className="flex justify-between gap-2">
          Sensibilidade
          <span>{sensitivity < 0.35 ? "poucas e grandes" : sensitivity > 0.65 ? "muitas e detalhadas" : "equilibrada"}</span>
        </span>
        <Slider
          min={0}
          max={1}
          step={0.05}
          value={[sensitivity]}
          onValueChange={([v]) => setSensitivity(v)}
          aria-label="Sensibilidade"
        />
      </label>
      <Button variant="primary" size="block" disabled={!p.hasPhoto || busy} onClick={run}>
        {busy ? "Analisando a foto…" : p.hasPhoto ? "Detectar na foto" : "Envie a foto primeiro"}
      </Button>

      {p.candidates.length > 0 && (
        <>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {p.candidates.map((c, i) => (
              <li key={i} className="flex items-center justify-between gap-2 rounded-md border border-border px-1.5 py-1">
                <label className="flex items-center gap-2 text-sm text-foreground">
                  <Checkbox checked={p.selected.has(i)} onCheckedChange={() => p.onToggle(i)} />
                  <span
                    className="h-3.5 w-3.5 shrink-0 rounded border border-border-strong"
                    style={{ background: `rgb(${c.color.join(",")})` }}
                  />
                  {c.label}
                </label>
                <span className="text-xs text-muted-foreground" title="Quão retangular é a região (100% = quadrilátero perfeito)">
                  {Math.round(c.score * 100)}% · {Math.round(c.area * 100)}% da foto
                </span>
              </li>
            ))}
          </ul>
          <p className="m-0 text-xs text-muted-foreground">Também dá para clicar numa região no editor para marcar/desmarcar.</p>
          <Button variant="primary" size="block" disabled={p.selected.size === 0} onClick={p.onCreate}>
            Criar {p.selected.size} superfície{p.selected.size === 1 ? "" : "s"}
          </Button>
        </>
      )}
    </Card>
  );
}
