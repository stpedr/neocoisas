"use client";

// Gaveta "Interação": presets de cena, pessoa simulada e estado ao vivo.
// Descrever a cena com IA (LLM) fica num botão à parte (AiDialog): só usa a IA
// quem pedir. O visual aparece em superfícies com a fonte "Cena interativa"
// (ou no TouchDesigner, via OSC).

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { InteractState } from "../lib/types";
import EffectsSection from "./EffectsSection";

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
      <div className="row">
        {st && (
          <span className="pill">
            Sensor: {{ sim: "pessoa simulada", osc: "OSC / Kinect", webcam: "webcam", phone: "celular" }[st.sensor]}
          </span>
        )}
        <button className="btn btn-small" onClick={onOpenAi} title="Descreva a cena em texto e a IA monta">✨ Criar cena com IA</button>
      </div>

      <EffectsSection st={st} onState={setSt} onError={onError} />

      <span className="dim small">Cenas prontas</span>
      <div className="upload-row" aria-label="Cenas prontas">
        {Object.entries(presets).map(([k, p]) => (
          <button key={k} className={`btn btn-small ${st?.spec.title === p.title ? "btn-accent" : ""}`} title={p.description}
                  onClick={() => run(() => api.interactPreset(k))}>
            {p.title}
          </button>
        ))}
      </div>

      {st && (
        <div className="status-box">
          <b>{st.spec.title}</b>
          <span className="dim small">
            {st.entities.length} elementos
            {counts.move ? ` · ${counts.move} em movimento` : ""}
            {counts.shy || counts.frozen ? ` · ${(counts.shy ?? 0) + (counts.frozen ?? 0)} parados (olhados)` : ""}
          </span>
          {player && (
            <span className="dim small">
              Pessoa: {!player.tracked ? "não detectada" : player.watching ? "olhando a parede" : "de costas"}
            </span>
          )}
          {st.sensor === "phone" && (
            <span className="dim small">
              Celular-sensor: {st.phone?.connected ? `conectado (${Math.round(st.phone.fps)} fps)` : "desconectado — veja o botão Celular"}
            </span>
          )}
          {caught && <span className="caught">Pegou! 👻</span>}
        </div>
      )}

      {sim && player && (
        <details open>
          <summary className="dim small">Pessoa simulada (teste sem sensor)</summary>
          <div className="row">
            <button className={`btn btn-small ${st?.scripted ? "btn-accent" : ""}`} onClick={() => run(api.interactAuto)}>
              Automático
            </button>
            <button className="btn btn-small" onClick={() => run(() => api.interactPlayer({ yaw_deg: 0, tracked: true }))}>
              Olhar a parede
            </button>
            <button className="btn btn-small" onClick={() => run(() => api.interactPlayer({ yaw_deg: 180, tracked: true }))}>
              Virar de costas
            </button>
          </div>
          <label className="slider">
            Posição na parede <span className="dim">{Math.round(player.x * 100)}%</span>
            <input type="range" min={0} max={1} step={0.01} value={player.x}
              onChange={(e) => run(() => api.interactPlayer({ x: Number(e.target.value) }))} />
          </label>
          <label className="slider">
            Rotação da cabeça <span className="dim">{Math.round(player.yaw_deg)}°</span>
            <input type="range" min={-180} max={180} step={1} value={Math.round(player.yaw_deg)}
              onChange={(e) => run(() => api.interactPlayer({ yaw_deg: Number(e.target.value) }))} />
          </label>
        </details>
      )}

      <div className="row">
        <label className="toggle">
          <input type="checkbox" checked={!!st?.debug} onChange={(e) => run(() => api.interactDebug(e.target.checked))} />
          Mostrar olhar
        </label>
        <button className="btn btn-small" onClick={() => run(() => api.interactPause(!st?.paused))}>
          {st?.paused ? "Continuar" : "Pausar"}
        </button>
        <button className="btn btn-small" onClick={() => run(api.interactReset)}>
          Reiniciar
        </button>
      </div>
      <p className="dim small">
        Para ver na parede, escolha a fonte <b>Cena interativa</b> numa superfície. Para o TouchDesigner, rode o mestre com{" "}
        <code>--osc-out 127.0.0.1:7000</code>.
      </p>
    </>
  );
}
