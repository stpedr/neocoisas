"use client";

// Gaveta "Interação": presets de cena, pessoa simulada e estado ao vivo.
// Descrever a cena com IA (LLM) fica num botão à parte (AiDialog): só usa a IA
// quem pedir. O visual aparece em superfícies com a fonte "Cena interativa"
// (ou no TouchDesigner, via OSC).

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { InteractState } from "../lib/types";
import EffectsSection from "./EffectsSection";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Slider } from "./ui/slider";

export default function InteractPanel({ st, setSt, caught, onError, onOpenAi }: {
  st: InteractState | null;
  setSt: (s: InteractState) => void;
  caught: boolean;
  onError: (msg: string) => void;
  onOpenAi: () => void;
}) {
  const [presets, setPresets] = useState<Record<string, { title: string; description: string }>>({});

  useEffect(() => {
    api.interactPresets().then(setPresets).catch(() => {});
  }, []);

  const run = async (fn: () => Promise<InteractState>) => {
    try {
      setSt(await fn());
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao falar com o mestre");
    }
  };

  const player = st?.players[0];
  const counts = (st?.entities ?? []).reduce<Record<string, number>>((acc, e) => ({ ...acc, [e.state]: (acc[e.state] ?? 0) + 1 }), {});
  const sim = st?.sensor === "sim";

  return (
    <>
      <div className="flex items-center gap-2">
        {st && (
          <Badge>
            Sensor: {{ sim: "pessoa simulada", osc: "OSC / Kinect", webcam: "webcam", phone: "celular" }[st.sensor]}
          </Badge>
        )}
        <Button variant="default" size="sm" onClick={onOpenAi} title="Descreva a cena em texto e a IA monta">
          ✨ Criar cena com IA
        </Button>
      </div>

      <EffectsSection st={st} onState={setSt} onError={onError} />

      <span className="text-xs text-muted-foreground">Cenas prontas</span>
      <div className="flex flex-wrap gap-1.5" aria-label="Cenas prontas">
        {Object.entries(presets).map(([k, p]) => (
          <Button
            key={k}
            variant={st?.spec.title === p.title ? "primary" : "default"}
            size="sm"
            title={p.description}
            onClick={() => run(() => api.interactPreset(k))}
          >
            {p.title}
          </Button>
        ))}
      </div>

      {st && (
        <div className="flex flex-col gap-0.5 rounded-radius-sm bg-secondary px-2.5 py-2">
          <b>{st.spec.title}</b>
          <span className="text-xs text-muted-foreground">
            {st.entities.length} elementos
            {counts.move ? ` · ${counts.move} em movimento` : ""}
            {counts.shy || counts.frozen ? ` · ${(counts.shy ?? 0) + (counts.frozen ?? 0)} parados (olhados)` : ""}
          </span>
          {player && (
            <span className="text-xs text-muted-foreground">
              Pessoa: {!player.tracked ? "não detectada" : player.watching ? "olhando a parede" : "de costas"}
            </span>
          )}
          {st.sensor === "phone" && (
            <span className="text-xs text-muted-foreground">
              Celular-sensor: {st.phone?.connected ? `conectado (${Math.round(st.phone.fps)} fps)` : "desconectado — veja o botão Celular"}
            </span>
          )}
          {caught && <span className="font-bold text-destructive">Pegou! 👻</span>}
        </div>
      )}

      {sim && player && (
        <details open>
          <summary className="text-xs text-muted-foreground">Pessoa simulada (teste sem sensor)</summary>
          <div className="mt-1.5 flex gap-1.5">
            <Button variant={st?.scripted ? "primary" : "default"} size="sm" onClick={() => run(api.interactAuto)}>
              Automático
            </Button>
            <Button variant="default" size="sm" onClick={() => run(() => api.interactPlayer({ yaw_deg: 0, tracked: true }))}>
              Olhar a parede
            </Button>
            <Button variant="default" size="sm" onClick={() => run(() => api.interactPlayer({ yaw_deg: 180, tracked: true }))}>
              Virar de costas
            </Button>
          </div>
          <label className="mt-1.5 flex flex-col gap-1 text-xs text-muted-foreground">
            <span className="flex justify-between gap-2">
              Posição na parede <span>{Math.round(player.x * 100)}%</span>
            </span>
            <Slider min={0} max={1} step={0.01} value={[player.x]} aria-label="Posição na parede"
              onValueChange={([v]) => run(() => api.interactPlayer({ x: v }))} />
          </label>
          <label className="mt-1.5 flex flex-col gap-1 text-xs text-muted-foreground">
            <span className="flex justify-between gap-2">
              Rotação da cabeça <span>{Math.round(player.yaw_deg)}°</span>
            </span>
            <Slider min={-180} max={180} step={1} value={[Math.round(player.yaw_deg)]} aria-label="Rotação da cabeça"
              onValueChange={([v]) => run(() => api.interactPlayer({ yaw_deg: v }))} />
          </label>
        </details>
      )}

      <div className="flex items-center gap-2">
        <label className="flex items-center gap-2 text-sm text-foreground">
          <Checkbox checked={!!st?.debug} onCheckedChange={(v) => run(() => api.interactDebug(v === true))} aria-label="Mostrar olhar" />
          Mostrar olhar
        </label>
        <Button variant="default" size="sm" onClick={() => run(() => api.interactPause(!st?.paused))}>
          {st?.paused ? "Continuar" : "Pausar"}
        </Button>
        <Button variant="default" size="sm" onClick={() => run(api.interactReset)}>
          Reiniciar
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Para ver na parede, escolha a fonte <b>Cena interativa</b> numa superfície. Para o TouchDesigner, rode o mestre com{" "}
        <code>--osc-out 127.0.0.1:7000</code>.
      </p>
    </>
  );
}
