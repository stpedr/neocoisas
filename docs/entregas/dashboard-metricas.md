# Entrega: Dashboard de métricas real

> Sprint 8 · Métricas & Escala — prioridade média.

## Resumo

Aba **📊 Dashboard** no frontend com KPIs da esteira, totais de desempenho,
gráfico de views por vídeo e os **insights do agente analista** — consumindo a
API existente.

## Motivação

Faltava uma visão consolidada de desempenho. O dashboard reúne contagens
(pendentes/aprovadas/postadas/rejeitadas), métricas por vídeo e a análise de
feedback num único lugar.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `server.py` | `GET /api/metrics/summary` (contagens + totais + ideias com métricas). |
| `web/app/components/DashboardView.tsx` (novo) | Aba com KPIs, totais, barras de views por vídeo e botão "Analisar". |
| `web/app/page.tsx`, `web/app/lib/api.ts` | Nova aba 📊 Dashboard + `getMetricsSummary`/`analyze`. |
| `tests/test_server_http.py` | Teste do `/api/metrics/summary` (agrega 2 ideias). |

## Como funciona

- **`/api/metrics/summary`** (sem Ollama): agrega `queue.counts()`, soma de
  `views`/`likes` e a lista de ideias que têm `metrics`.
- **UI**: tiles de KPI + totais, barras proporcionais de views por vídeo, e um
  botão **Analisar** que chama `POST /api/analyze` (agente analista) para exibir
  insights + recomendações.
- Métricas hoje entram manualmente (`POST /api/ideas/{id}/metrics`); a **coleta
  automática** por plataforma é um card futuro que popula os mesmos dados.

## Como validar

```bash
pytest -q tests/test_server_http.py::test_metrics_summary
# ao vivo:
curl -X POST http://localhost:8000/api/ideas/<ID>/metrics -H 'Content-Type: application/json' -d '{"views":1200,"likes":90}'
curl -s http://localhost:8000/api/metrics/summary
# aba 📊 Dashboard no app
```

## Critério de aceite

- [x] KPIs da esteira + totais de views/likes.
- [x] Gráfico de desempenho por vídeo.
- [x] Insights do analista sob demanda. 139 testes verdes.

## Pendências / próximos

- **Coleta automática de métricas** (popula o dashboard com dados reais das plataformas).
