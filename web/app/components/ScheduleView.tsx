"use client";

import { useCallback, useEffect, useState } from "react";
import { api, RunResult, Schedule } from "../lib/api";

export default function ScheduleView() {
  const [sched, setSched] = useState<Schedule | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [genRunning, setGenRunning] = useState(false);
  const [lastRun, setLastRun] = useState<RunResult | null>(null);
  const [genMsg, setGenMsg] = useState("");

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

  async function runAutogen() {
    setGenRunning(true);
    setError("");
    setGenMsg("");
    try {
      const r = await api.runAutogen();
      setGenMsg(`${r.generated} ideias geradas.`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGenRunning(false);
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

      <div className="panel" style={{ marginTop: 16 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 14,
          }}
        >
          <div>
            <strong>Geração automática de ideias</strong>
            <div className="muted">
              Cria ideias novas sozinho, por intervalo, a partir de um prompt fixo.
            </div>
          </div>
          <div className="mode-toggle">
            <button
              className={sched.autogen_enabled ? "on" : ""}
              onClick={() => save({ autogen_enabled: true })}
              disabled={saving}
            >
              Ativado
            </button>
            <button
              className={!sched.autogen_enabled ? "on" : ""}
              onClick={() => save({ autogen_enabled: false })}
              disabled={saving}
            >
              Desativado
            </button>
          </div>
        </div>

        <div className="field">
          <label>Prompt fixo</label>
          <input
            className="input"
            placeholder="Ex: curiosidades de ciência para crianças"
            value={sched.autogen_prompt}
            onChange={(e) =>
              setSched({ ...sched, autogen_prompt: e.target.value })
            }
            onBlur={(e) => save({ autogen_prompt: e.target.value })}
          />
        </div>
        <div className="row">
          <div className="field">
            <label>Intervalo (min)</label>
            <input
              className="input"
              type="number"
              min={1}
              max={1440}
              value={sched.autogen_every_minutes}
              onChange={(e) =>
                setSched({ ...sched, autogen_every_minutes: Number(e.target.value) })
              }
              onBlur={(e) =>
                save({ autogen_every_minutes: Number(e.target.value) })
              }
            />
          </div>
          <div className="field">
            <label>Ideias por rodada</label>
            <input
              className="input"
              type="number"
              min={1}
              max={12}
              value={sched.autogen_count}
              onChange={(e) =>
                setSched({ ...sched, autogen_count: Number(e.target.value) })
              }
              onBlur={(e) => save({ autogen_count: Number(e.target.value) })}
            />
          </div>
        </div>
        <div style={{ display: "flex", gap: 12, marginTop: 8, alignItems: "center" }}>
          <button
            className="btn"
            onClick={runAutogen}
            disabled={genRunning || !sched.autogen_prompt.trim()}
          >
            {genRunning && <span className="spinner" />}
            {genRunning ? "Gerando…" : "✨ Gerar agora"}
          </button>
          {genMsg && <span className="muted">{genMsg}</span>}
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
