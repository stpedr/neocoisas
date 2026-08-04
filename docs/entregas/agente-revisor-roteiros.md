# Entrega: Agente revisor/editor de roteiros (loop de melhoria)

> Sprint 6 · Automações — card de **prioridade alta** do backlog.

## Resumo

Adiciona um agente que **melhora roteiros fracos em vez de só rejeitá-los**. Ele
usa o agente crítico para dar nota e, quando abaixo do limiar, **reescreve o
roteiro a partir da crítica e re-avalia em loop** até atingir a nota mínima (ou
esgotar as iterações).

## Motivação

Até aqui o quality gate (agente crítico) só **descartava** ideias abaixo da nota.
Isso joga fora roteiros que precisavam apenas de um ajuste. O editor eleva a
**taxa de aproveitamento** das ideias geradas, mantendo a barra de qualidade.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `agents/editor.py` (novo) | `refine_loop` (núcleo **puro**) + `ScriptEditorAgent` (crítico + reescrita via LLM). |
| `engine.py` | `generate_and_enqueue` aceita `editor`; quando presente, refina antes de decidir aprovar/rejeitar (substitui o gate simples). |
| `server.py` | `POST /api/ideas/{id}/refine` (refino manual) + wiring por `editor_enabled` no `/generate`. |
| `config.example.json` | `editor_enabled` (bool) e `editor_max_iterations` (int). |
| `tests/test_editor.py`, `tests/test_engine.py` | Cobertura do loop e da integração. |

## Como funciona

```
score = crítico(roteiro)
enquanto score < min_score e iterações < máx:
    roteiro = reescreve(roteiro, feedback_da_crítica)
    score = crítico(roteiro)
→ {scenes, score, iterations, passed, history}
```

- **Núcleo puro** (`refine_loop`): recebe `score_fn` e `rewrite_fn` injetados —
  testável sem Ollama.
- **Integração no engine**: com `editor` ativo, a ideia refinada entra como
  pendente/aprovada se passou, ou rejeitada se nem após as iterações atingiu a
  nota. A nota e o nº de iterações ficam em `idea.score` / `idea.note`.
- **Config**: `editor_enabled=true` liga no fluxo de geração; `critic_min_score`
  é o alvo; `editor_max_iterations` limita o loop.

## Como validar

```bash
# offline (loop puro + integração)
pytest -q tests/test_editor.py tests/test_engine.py

# ao vivo (precisa do Ollama): refina uma ideia existente
curl -X POST http://localhost:8000/api/ideas/<ID>/refine
```

## Critério de aceite

- [x] Loop crítica→reescrita→re-avalia com teto de iterações.
- [x] Nota final e nº de iterações registrados na ideia.
- [x] Recupera ideias que seriam rejeitadas (teste cobre).
- [x] Núcleo puro coberto por testes (115 no total).

## Pendências / próximos

- Expor um botão "Refinar" no frontend (aba Ideias).
- Métrica de quantas ideias foram recuperadas pelo editor (liga com o dashboard).
