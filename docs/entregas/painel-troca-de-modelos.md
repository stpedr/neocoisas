# Entrega: Painel de troca de modelos (UI)

> Sprint 9 · Troca de modelos — prioridade média. Fecha a Sprint 9 (exceto override por agente).

## Resumo

Aba **⚙️ Modelos** no frontend para escolher **provider + modelo por capacidade**
(texto/imagem/voz/vídeo/publicação) sem editar `.env`/config. A troca vale na
hora e é persistida; opções que exigem chave ausente aparecem sinalizadas.

## Motivação

O registry (`/api/models`) e a descoberta (`/api/models/available`) já expunham o
mapa de modelos, mas não havia como **trocar** pela interface — e, no Docker, os
envs do compose sempre estavam setados, o que impediria uma troca via config.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `settings.py` (novo) | Persiste a seleção (`output/model_settings.json`) e **aplica no `os.environ`** do processo (vale na hora + reaplica no startup). |
| `server.py` | `PUT /api/models/select` (valida via registry, aplica) + `apply_saved()` no lifespan. |
| `web/app/components/ModelsView.tsx` (novo) | Aba com selects de provider/modelo por capacidade + aviso de chave faltante. |
| `web/app/page.tsx`, `web/app/lib/api.ts` | Nova aba ⚙️ Modelos + `getModels`/`getAvailableModels`/`selectModel`. |
| `tests/test_settings.py` (novo) | Persistência + aplicação no ambiente. |

## Como funciona

- A UI carrega `/api/models` (estrutura + seleção atual + `configured`) e
  `/api/models/available` (modelos reais do Ollama + conhecidos).
- Ao trocar, faz `PUT /api/models/select {capability, provider, model}`.
- O backend **valida** (registry) e o `settings` grava o JSON e faz
  `os.environ[...] = ...` mapeando capacidade→env (ex.: `text/gemini` →
  `ANE_TEXT_PROVIDER=gemini` + `GEMINI_TEXT_MODEL`). Os factories leem `os.environ`,
  então a próxima geração/render já usa a nova escolha.
- No **startup**, `apply_saved()` reaplica a última seleção.

## Como validar

```bash
pytest -q tests/test_settings.py
# ao vivo:
curl -X PUT http://localhost:8000/api/models/select \
  -H 'Content-Type: application/json' \
  -d '{"capability":"text","provider":"ollama","model":"llama3"}'
# e conferir em GET /api/models (current) — ou pela aba ⚙️ Modelos
```

## Critério de aceite

- [x] Trocar provider+modelo por capacidade pela UI.
- [x] Troca aplicada em runtime e persistida (sobrevive a restart).
- [x] Validação da seleção (registry) e aviso de chave faltante. 134 testes verdes.

## Pendências / próximos

- **Override de modelo por agente** (último card da Sprint 9).
- Provers de texto `openai`/`anthropic` (entram no mesmo registry/UI).
