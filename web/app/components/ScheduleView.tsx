"use client";

import { useCallback, useEffect, useState } from "react";
import { api, RunResult, Schedule } from "../lib/api";

export default function ScheduleView() {
  const [sched, setSched] = useState<Schedule | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<RunResult | null>(null);

  const load = useCallback(async () => {
    try {
      setSched(await api.getSchedule());
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save(patch: Partial<Schedule>) {
    setSaving(true);
    setError("");
    try {
      setSched(await api.updateSchedule(patch));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function runNow() {
    setRunning(true);
    setError("");
    try {
      setLastRun(await api.runSchedule());
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  if (!sched) {
    return <p className="muted">{error || "Carregando agendamento…"}</p>;
  }

  const fmt = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString() : "—";

  return (
    <div>
      {error && <div className="alert error">{error}</div>}

      <div className="panel">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 14,
          }}
        >
          <div>
            <strong>Agendamento de postagens</strong>
            <div className="muted">
              Publica as ideias aprovadas automaticamente. Sem token, roda em
              modo simulado (marca como postada).
            </div>
          </div>
          <div className="mode-toggle">
            <button
              className={sched.enabled ? "on" : ""}
              onClick={() => save({ enabled: true })}
              disabled={saving}
            >
              Ativado
            </button>
            <button
              className={!sched.enabled ? "on" : ""}
              onClick={() => save({ enabled: false })}
              disabled={saving}
            >
              Desativado
            </button>
          </div>
        </div>

        <div className="row">
          <div className="field">
            <label>Intervalo (minutos)</label>
            <input
              className="input"
              type="number"
              min={1}
              max={1440}
              value={sched.every_minutes}
              onChange={(e) =>
                setSched({ ...sched, every_minutes: Number(e.target.value) })
              }
              onBlur={(e) => save({ every_minutes: Number(e.target.value) })}
            />
          </div>
          <div className="field">
            <label>Máx. por rodada</label>
            <input
              className="input"
              type="number"
              min={1}
              max={20}
              value={sched.max_per_run}
              onChange={(e) =>
                setSched({ ...sched, max_per_run: Number(e.target.value) })
              }
              onBlur={(e) => save({ max_per_run: Number(e.target.value) })}
            />
          </div>
        </div>

        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 6 }}>
          <label className="muted" style={{ display: "flex", gap: 6 }}>
            <input
              type="checkbox"
              checked={sched.render_before}
              onChange={(e) => save({ render_before: e.target.checked })}
            />
            Renderizar antes de postar
          </label>
          <label className="muted" style={{ display: "flex", gap: 6 }}>
            <input
              type="checkbox"
              checked={sched.simulate}
              onChange={(e) => save({ simulate: e.target.checked })}
            />
            Simular sem publisher
          </label>
        </div>

        <div style={{ display: "flex", gap: 12, marginTop: 16, alignItems: "center" }}>
          <button className="btn btn-primary" onClick={runNow} disabled={running}>
            {running && <span className="spinner" />}
            {running ? "Executando…" : "▶ Rodar agora"}
          </button>
          <span className="muted">
            {sched.enabled
              ? `Próxima execução: ${fmt(sched.next_run)}`
              : "Agendador desativado"}
          </span>
        </div>
      </div>

      <div className="stats">
        <div className="stat">
          <div className="num">{sched.every_minutes}m</div>
          <div className="lbl">Intervalo</div>
        </div>
        <div className="stat">
          <div className="num">{sched.max_per_run}</div>
          <div className="lbl">Por rodada</div>
        </div>
        <div className="stat">
          <div className="num">{sched.enabled ? "ON" : "OFF"}</div>
          <div className="lbl">Estado</div>
        </div>
        <div className="stat">
          <div className="num" style={{ fontSize: 14 }}>{fmt(sched.last_run)}</div>
          <div className="lbl">Última execução</div>
        </div>
      </div>

      {lastRun && (
        <>
          <div className="section-title">Resultado da última rodada manual</div>
          <p className="muted">
            Processadas: {lastRun.processed} · Postadas: {lastRun.posted} ·
            Simuladas: {lastRun.simulated} · Erros: {lastRun.errors}
          </p>
        </>
      )}
    </div>
  );
}
