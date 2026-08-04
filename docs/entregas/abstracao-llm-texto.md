# Entrega: Abstração de provedor de LLM (texto)

> Sprint 9 · Troca de modelos — card de **prioridade alta** (alicerce).

## Resumo

Generaliza o padrão de *factory por capacidade* (já usado em `agents/media` e
`publishers`) para o **LLM de texto**. Agora todos os agentes obtêm o cliente de
texto por `get_text_client(config)`, e o provedor é selecionável por config/env —
com `ollama` como padrão e `gemini` (texto) disponível.

## Motivação

O `OllamaClient` estava **fixo** e instanciado diretamente por 8 agentes, com um
modelo único e global. Isso impedia trocar de provedor de texto ou usar modelos
diferentes. Esta é a base para o registry de modelos, o override por agente e a UI
de troca (demais cards da Sprint 9).

## O que mudou

| Arquivo | Mudança |
|---|---|
| `agents/llm/__init__.py` (novo) | Exporta `get_text_client`, `resolve_provider`, `OllamaError`/`LLMError`. |
| `agents/llm/factory.py` (novo) | Registry `{ollama, gemini}` + seleção por `ANE_TEXT_PROVIDER`/`text_provider`. |
| `agents/llm/gemini_text.py` (novo) | `GeminiTextClient` — mesmo contrato do OllamaClient (Gemini API, opt-in por `GEMINI_API_KEY`). |
| `agents/{niche_creator,script_writer,idea_generator,critic,titler,translator,analyst,editor}.py` | Passam a usar `get_text_client(config)` em vez de `OllamaClient(...)`. |
| `config.example.json`, `.env.example`, `docker-compose.yml` | `text_provider` / `ANE_TEXT_PROVIDER` + `gemini_text_model`. |
| `tests/test_llm_factory.py` (novo) | Resolução de provider, seleção e erro sem chave. |

## Como funciona

**Contrato do cliente de texto** (o que os agentes usam):
`generate(prompt) -> str`, `extract_json(raw)`, `.model`, `.config`.

```
get_text_client(config) → resolve_provider (env > config, padrão "ollama")
                         → OllamaClient | GeminiTextClient
```

Trocar de provedor de texto = mudar `ANE_TEXT_PROVIDER`/`text_provider` (e a chave
correspondente). Nenhum agente muda — todos passam pela factory. `GeminiTextClient`
reusa o `extract_json` tolerante do OllamaClient, garantindo mesmo parsing.

## Como validar

```bash
pytest -q tests/test_llm_factory.py          # seleção de provider (offline)
pytest -q                                     # suíte completa (122)
# ao vivo: com ANE_TEXT_PROVIDER=ollama (padrão) o /generate segue igual
```

## Critério de aceite

- [x] `get_text_client(config)` espelhando `agents/media`.
- [x] `OllamaClient` é o provider `ollama` (padrão, comportamento inalterado).
- [x] Todos os agentes passam pela factory (sem instanciar OllamaClient direto).
- [x] Trocar provider por config/env sem mexer nos agentes.
- [x] Sem ciclo de import; 122 testes verdes.

## Pendências / próximos (Sprint 9)

- **Registry unificado de modelos** (`GET /api/models`).
- **Override de modelo por agente**.
- **Descoberta de modelos** (Ollama `/api/tags` + provedores).
- **Painel de troca de modelos (UI)**.
- Provers `openai`/`anthropic` de texto (entram no mesmo registry).
