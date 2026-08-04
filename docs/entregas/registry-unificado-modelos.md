# Entrega: Registry unificado de modelos

> Sprint 9 · Troca de modelos — prioridade média.

## Resumo

Adiciona um **descritor central** de todas as capacidades de modelo (texto,
imagem, voz, vídeo, publicação): providers disponíveis, modelos conhecidos,
variáveis exigidas, se estão configuradas e qual está **ativo** agora. Exposto em
`GET /api/models` — a base que a UI de troca de modelos vai consumir.

## Motivação

Cada capacidade já tinha seu factory, mas não havia um lugar único que dissesse
"o que existe, o que está ativo e o que falta configurar". O registry unifica isso
e mantém-se em sincronia lendo os providers direto dos factories.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `registry.py` (novo) | `CAP_PROVIDERS` (derivado dos factories), `REQUIRES`, `KNOWN_MODELS`; `current()`, `validate()`, `describe()`. |
| `server.py` | `GET /api/models` → `describe(config)`. |
| `tests/test_registry.py` (novo) | Capacidades, sincronia com factories, seleção atual (env/config), `configured`, `validate`. |

## Como funciona

- **Providers vêm dos factories** (`agents.llm`, `agents.media`, `publishers`) —
  se um provider novo é registrado lá, aparece aqui automaticamente.
- **`current(cap, config)`** resolve provider+modelo ativos (env > config > padrão),
  igual à lógica dos factories.
- **`configured`** indica, por provider, se as variáveis exigidas (`REQUIRES`)
  estão setadas — a UI mostra o que falta para habilitar cada opção.
- **`describe(config)`** monta o payload de `/api/models`.

Exemplo (resumido) de `GET /api/models`:
```json
{"capabilities": {
  "text": {"providers": ["gemini","ollama"],
            "current": {"provider":"ollama","model":"llama3"},
            "requires": {"gemini":["GEMINI_API_KEY"],"ollama":[]},
            "configured": {"gemini": false, "ollama": true},
            "models": {"ollama":["llama3"],"gemini":["gemini-1.5-flash","gemini-1.5-pro"]}}
}}
```

## Como validar

```bash
pytest -q tests/test_registry.py
curl -s http://localhost:8000/api/models    # descritor completo
```

## Critério de aceite

- [x] `/api/models` lista todas as capacidades com providers, modelos e seleção atual.
- [x] Providers em sincronia com os factories reais.
- [x] Indica requisitos e o que já está configurado.
- [x] `validate(cap, provider)` para checar seleções. 129 testes verdes.

## Pendências / próximos (Sprint 9)

- **Descoberta de modelos** (Ollama `/api/tags`) para enriquecer `models`.
- **Painel de troca de modelos (UI)** consumindo `/api/models`.
- **Override por agente** + endpoint de seleção (PUT) usando `validate`.
