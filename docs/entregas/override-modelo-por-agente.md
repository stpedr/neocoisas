# Entrega: Override de modelo por agente

> Sprint 9 · Troca de modelos — **fecha a Sprint 9**.

## Resumo

Permite atribuir um **modelo próprio a cada agente** de texto (crítico, roteirista,
ideias, editor, títulos, tradutor, analista, nicho), sobrepondo o modelo global —
ex.: crítico com um modelo mais forte, ideias com um mais rápido.

## Motivação

O provider/modelo de texto era único para todos os agentes. Tarefas diferentes se
beneficiam de modelos diferentes (custo/qualidade/latência). Este card fecha a
Sprint 9 de troca de modelos.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `agents/llm/factory.py` | `get_text_client(config, agent=...)` aplica override de modelo por agente (`agent_model_override`). |
| `agents/*.py` (8 agentes) | Passam o próprio nome ao `get_text_client`. |
| `settings.py` | `set_agent_model()` + aplicação da chave `agents` no `os.environ` (`ANE_AGENT_MODEL_<AGENTE>`). |
| `registry.py` | `agent_models()` + seção `agents` no `describe()` (modelo efetivo + flag override). |
| `server.py` | `PUT /api/models/agent`. |
| `web/.../ModelsView.tsx` | Seção “Override de modelo por agente” (select por agente, “(global)” = padrão). |
| `config.example.json` | `agent_models: {}`. |
| `tests/test_registry.py`, `tests/test_settings.py` | Override por env, efetivo e persistência. |

## Como funciona

- **Resolução**: `get_text_client(config, agent)` resolve o provider global e, se
  houver override para o agente (`ANE_AGENT_MODEL_<AGENTE>` ou
  `config['agent_models'][agent]`), sobrescreve `client.model`.
- **Persistência/UI**: `PUT /api/models/agent {agent, model}` grava sob a chave
  `agents` do `model_settings.json` e aplica no `os.environ` (vale na hora +
  reaplica no startup). `model` vazio remove o override (volta ao global).
- **Registry**: `/api/models` traz `agents: {agente: {model, override}}`.

## Como validar

```bash
pytest -q tests/test_registry.py tests/test_settings.py
curl -X PUT http://localhost:8000/api/models/agent \
  -H 'Content-Type: application/json' -d '{"agent":"critic","model":"llama3:70b"}'
curl -s http://localhost:8000/api/models    # agents.critic.override == true
```

## Critério de aceite

- [x] Modelo por agente sobrepondo o global.
- [x] Configurável por config/env e pela UI; persistido e reaplicado.
- [x] Visível no registry (`agents`). 138 testes verdes.

## Pendências / próximos

- Sprint 9 **concluída**. Provers de texto `openai`/`anthropic` podem entrar no
  mesmo registry quando desejado.
