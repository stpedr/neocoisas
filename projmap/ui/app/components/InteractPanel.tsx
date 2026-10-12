"use client";

// Card "Interativo": descreva a cena em texto (NLP), escolha presets, simule a
// pessoa (sem sensor) e acompanhe o estado ao vivo. O visual aparece em qualquer
// superfície com a fonte "Cena interativa" (ou no TouchDesigner, via OSC).

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { InteractState } from "../lib/types";
import EffectsSection from "./EffectsSection";

const EXAMPLES = [
  "5 fantasmas que param e cobrem o rosto quando eu olho, e vêm me buscar quando viro de costas",
  "vaga-lumes amarelos que vão para onde eu olho",
  "cardume de 20 peixes azuis que fogem de mim",
];

export default function InteractPanel({ onError }: { onError: (msg: string) => void }) {
  const [st, setSt] = useState<InteractState | null>(null);
  const [off, setOff] = useState(false);
  const [text, setText] = useState("");
  const [useLlm, setUseLlm] = useState(true);
  const [busy, setBusy] = useState(false);
  const [origin, setOrigin] = useState<{ source: string; notes: string[] } | null>(null);
  const [presets, setPresets] = useState<Record<string, { title: string; description: string }>>({});
  const lastCaught = useRef(0);
  const [caughtFlash, setCaughtFlash] = useState(false);

  // Estado ao vivo (2×/s). 404 = mestre rodando com --no-interact.
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const s = await api.interactState();
        if (!alive) return;
        setSt(s);
        setOff(false);
        const caught = s.events.filter((e) => e.name === "caught").at(-1);
        if (caught && caught.t !== lastCaught.current) {
          lastCaught.current = caught.t;
          setCaughtFlash(true);
          window.setTimeout(() => setCaughtFlash(false), 1200);
        }
      } catch (e) {
        if (alive && e instanceof ApiError && e.status === 404) setOff(true);
      }
    };
    void poll();
    api.interactPresets().then(setPresets).catch(() => {});
    const id = window.setInterval(poll, 500);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  const run = async (fn: () => Promise<InteractState>) => {
    try {
      setSt(await fn());
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao falar com o mestre");
    }
  };

  const generate = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const res = await api.interactGenerate(text, useLlm);
      setSt(res);
      setOrigin({ source: res.source ?? "?", notes: res.notes ?? [] });
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao gerar a cena");
    } finally {
      setBusy(false);
    }
  };

  if (off) {
    return (
      <section className="card">
        <h2>Interativo</h2>
        <p className="dim small">Camada interativa desligada (mestre iniciado com --no-interact).</p>
      </section>
    );
  }

  const player = st?.players[0];
  const counts = (st?.entities ?? []).reduce<Record<string, number>>((acc, e) => ({ ...acc, [e.state]: (acc[e.state] ?? 0) + 1 }), {});
  const sim = st?.sensor === "sim";

  return (
    <section className={`card ${caughtFlash ? "card-alert" : ""}`}>
      <div className="card-head">
        <h2>Interativo · IA + sensores</h2>
        {st && (
          <span className="pill">
            {{ sim: "pessoa simulada", osc: "OSC / Kinect", webcam: "webcam", phone: "celular" }[st.sensor]}
          </span>
        )}
      </div>

      <EffectsSection st={st} onState={setSt} onError={onError} />


      <label>
        Descreva a cena
        <textarea
          rows={3}
          value={text}
          placeholder={EXAMPLES[0]}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void generate();
          }}
        />
      </label>
      <div className="row">
        <label className="toggle">
          <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
          Usar IA (LLM)
        </label>
        <button className="btn btn-accent" disabled={busy || !text.trim()} onClick={generate}>
          {busy ? "Gerando…" : "Gerar cena"}
        </button>
      </div>
      {origin && (
        <p className="dim small">
          {origin.source === "llm" ? "✓ Interpretado pela IA." : "⚠ Montado por palavras-chave, sem IA."}
          {origin.notes.filter((n) => !n.includes("palavras-chave")).map((n) => (
            <span key={n}> {n}.</span>
          ))}
        </p>
      )}
      <div className="upload-row">
        {EXAMPLES.slice(1).map((ex) => (
          <button key={ex} className="btn btn-small" onClick={() => setText(ex)} title="usar este exemplo">
            {ex.split(" ").slice(0, 3).join(" ")}…
          </button>
        ))}
      </div>

      <div className="upload-row" aria-label="Presets">
        {Object.entries(presets).map(([k, p]) => (
          <button key={k} className="btn btn-small" title={p.description} onClick={() => run(() => api.interactPreset(k))}>
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
          {caughtFlash && <span className="caught">Pegou! 👻</span>}
        </div>
      )}

      {st?.sensor === "phone" ? (
        <p className="dim small">
          Celular-sensor: {st.phone?.connected ? `conectado (${Math.round(st.phone.fps)} fps)` : "desconectado"}.
        </p>
      ) : (
        <details>
          <summary className="dim small">Usar o celular como sensor (USB/ADB)</summary>
          <p className="dim small">
            Ligue a Depuração USB, conecte o cabo e rode o mestre com <code>--sensor phone --adb</code> (ou{" "}
            <code>python -m projmap.tools.adb</code>). A página <code>/sensor/</code> abre no celular; toque em
            &quot;Iniciar sensor&quot;.
          </p>
        </details>
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
    </section>
  );
}
