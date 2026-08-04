# Entrega: Descoberta de modelos disponíveis

> Sprint 9 · Troca de modelos — prioridade baixa (alimenta a UI/registry).

## Resumo

Descobre ao vivo os modelos **realmente instalados** no Ollama (via `/api/tags`) e
os combina com os modelos conhecidos dos demais provedores, expondo em
`GET /api/models/available`. É o que a UI vai usar para listar as opções reais.

## Motivação

O registry lista providers e modelos *conhecidos* (estáticos). Para a UI oferecer
o que de fato está disponível, precisamos consultar o Ollama do usuário — que pode
ter qualquer conjunto de modelos baixados.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `registry.py` | `_ollama_tags(config)` (consulta resiliente ao `/api/tags`) e `available_models(config)`. |
| `server.py` | `GET /api/models/available`. |
| `tests/test_registry.py` | Descoberta (mock) + fallback quando o Ollama está fora. |

## Como funciona

- **Ollama**: `GET {base}/api/tags` → nomes dos modelos instalados. `base` vem de
  `ANE_OLLAMA_BASE_URL`/`ollama_base_url`. **Resiliente**: se o Ollama estiver
  fora, cai nos modelos conhecidos (`KNOWN_MODELS`) — nunca quebra a resposta.
- **Demais provedores** (gemini de texto/imagem/vídeo): lista estática conhecida.
- `/api/models` (estrutura, sem rede) + `/api/models/available` (ao vivo) se
  complementam para a UI.

## Como validar

```bash
pytest -q tests/test_registry.py
curl -s http://localhost:8000/api/models/available   # modelos instalados no Ollama
```

## Critério de aceite

- [x] Lista modelos instalados no Ollama ao vivo.
- [x] Fallback seguro quando o Ollama está indisponível.
- [x] Combinado com os modelos conhecidos dos outros provedores. 131 testes verdes.

## Pendências / próximos

- **Painel de troca de modelos (UI)** consumindo `/api/models` + `/api/models/available`.
- **Override de modelo por agente**.
