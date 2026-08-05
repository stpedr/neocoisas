"use client";

import { useCallback, useEffect, useState } from "react";
import { Analysis, api, MetricsSummary } from "../lib/api";
import { useToast } from "./Toast";

export default function DashboardView() {
  const [data, setData] = useState<MetricsSummary | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const toast = useToast();
  const setError = (m: string) => toast(m, "error");

  const load = useCallback(async () => {
    try {
      setData(await api.getMetricsSummary());
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function analyze() {
    setAnalyzing(true);
    setError("");
    try {
      setAnalysis(await api.analyze());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAnalyzing(false);
    }
  }

  if (!data) return <p className="muted">Carregando métricas…</p>;

  const c = data.counts;
  const maxViews = Math.max(1, ...data.ideas.map((i) => Number(i.metrics.views || 0)));

  return (
    <div>

      {/* KPIs da esteira */}
      <div className="stats">
        <div className="stat"><div className="num">{c.pending ?? 0}</div><div className="lbl">Pendentes</div></div>
        <div className="stat"><div className="num">{c.approved ?? 0}</div><div className="lbl">Aprovadas</div></div>
        <div className="stat"><div className="num">{c.posted ?? 0}</div><div className="lbl">Postadas</div></div>
        <div className="stat"><div className="num">{c.rejected ?? 0}</div><div className="lbl">Rejeitadas</div></div>
      </div>

      {/* Totais de desempenho */}
      <div className="stats">
        <div className="stat"><div className="num">{data.totals.com_metricas}</div><div className="lbl">Com métricas</div></div>
        <div className="stat"><div className="num">{data.totals.views.toLocaleString()}</div><div className="lbl">Views totais</div></div>
        <div className="stat"><div className="num">{data.totals.likes.toLocaleString()}</div><div className="lbl">Likes totais</div></div>
      </div>

      {/* Desempenho por vídeo */}
      <div className="section-title">Desempenho por vídeo</div>
      {data.ideas.length === 0 ? (
        <p className="muted">
          Sem métricas ainda. Registre com <code>POST /api/ideas/&#123;id&#125;/metrics</code>
          {" "}(a coleta automática por plataforma é um card futuro).
        </p>
      ) : (
        <div className="panel">
          {data.ideas.map((i) => {
            const v = Number(i.metrics.views || 0);
            return (
              <div key={i.id} style={{ marginBottom: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span>{i.title}</span>
                  <span className="muted">
                    {v.toLocaleString()} views · {Number(i.metrics.likes || 0).toLocaleString()} likes
                  </span>
                </div>
                <div className="progress" style={{ marginTop: 4 }}>
                  <span style={{ width: `${(v / maxViews) * 100}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Insights do analista */}
      <div className="section-title">Insights do analista</div>
      <button className="btn btn-primary" onClick={analyze} disabled={analyzing}>
        {analyzing && <span className="spinner" />}
        {analyzing ? "Analisando…" : "🧠 Analisar desempenho"}
      </button>
      {analysis && (
        <div className="panel" style={{ marginTop: 12 }}>
          <p>{analysis.insights || "—"}</p>
          {analysis.recommendations.length > 0 && (
            <ul>
              {analysis.recommendations.map((r, idx) => (
                <li key={idx} className="muted">{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
