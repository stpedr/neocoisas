"use client";

import { useCallback, useEffect, useState } from "react";
import { Analysis, api, MetricsSummary } from "../lib/api";
import { useToast } from "./Toast";

function renderBarChart(
  ideas: MetricsSummary["ideas"],
  maxViews: number,
) {
  const rows = ideas.slice(0, 12);
  const rowH = 34, barH = 18, labelW = 150, valW = 64, pad = 8;
  const W = 720, chartW = W - labelW - valW;
  const H = rows.length * rowH + pad * 2;
  const trunc = (s: string) => (s.length > 22 ? s.slice(0, 21) + "…" : s);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Views por vídeo">
      {rows.map((i, idx) => {
        const v = Number(i.metrics.views || 0);
        const y = pad + idx * rowH;
        const bw = Math.max(2, (v / maxViews) * chartW);
        return (
          <g key={i.id}>
            <text x={0} y={y + barH - 3} fontSize="13" fill="var(--text-dim)">{trunc(i.title)}</text>
            <rect x={labelW} y={y} width={chartW} height={barH} rx={5} fill="var(--bg-elev-2)" />
            <rect x={labelW} y={y} width={bw} height={barH} rx={5} fill="var(--accent-2)" />
            <text x={labelW + bw + 6} y={y + barH - 3} fontSize="12" fill="var(--text)">
              {v.toLocaleString()}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

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
        <div className="stat"><div className="num">⏳ {c.pending ?? 0}</div><div className="lbl">Pendentes</div></div>
        <div className="stat"><div className="num">✅ {c.approved ?? 0}</div><div className="lbl">Aprovadas</div></div>
        <div className="stat"><div className="num">🚀 {c.posted ?? 0}</div><div className="lbl">Postadas</div></div>
        <div className="stat"><div className="num">✕ {c.rejected ?? 0}</div><div className="lbl">Rejeitadas</div></div>
      </div>

      {/* Totais de desempenho */}
      <div className="stats">
        <div className="stat"><div className="num">🎬 {data.totals.com_metricas}</div><div className="lbl">Com métricas</div></div>
        <div className="stat"><div className="num">👁 {data.totals.views.toLocaleString()}</div><div className="lbl">Views totais</div></div>
        <div className="stat"><div className="num">❤ {data.totals.likes.toLocaleString()}</div><div className="lbl">Likes totais</div></div>
      </div>

      {/* Desempenho por vídeo (gráfico SVG) */}
      <div className="section-title">Desempenho por vídeo</div>
      {data.ideas.length === 0 ? (
        <p className="muted">
          Sem métricas ainda. Registre com <code>POST /api/ideas/&#123;id&#125;/metrics</code>
          {" "}(a coleta automática por plataforma é um card futuro).
        </p>
      ) : (
        <div className="panel">{renderBarChart(data.ideas, maxViews)}</div>
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
