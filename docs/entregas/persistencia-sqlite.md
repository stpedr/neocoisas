# Entrega: Persistência em SQLite

> Sprint 7 · Robustez — prioridade alta.

## Resumo

Migra a **fila de ideias** e o **quadro Kanban** de arquivos JSON para **SQLite**
(com WAL), eliminando o risco de corrupção sob concorrência. A interface pública
é idêntica (nenhum agente/endpoint mudou de assinatura) e um JSON legado no mesmo
caminho é **migrado automaticamente** na primeira abertura.

## Motivação

Os stores gravavam o documento inteiro em JSON a cada mutação — sujeito a
corrupção/perda de update sob escrita concorrente. SQLite dá transações atômicas
e leitura/escrita concorrente segura.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `review/queue.py` | Reescrito sobre SQLite (tabela `ideas`); persistência por operação; WAL; migração de JSON legado. Novo `update(idea)` público. |
| `board/store.py` | Persistência SQLite (tabela `cards`); migração de JSON legado; `_load/_save` transacionais. |
| `engine.py`, `scheduler.py`, `server.py` | Trocam mutação+`_save()` por `queue.update(idea)` (as `Idea` agora vêm destacadas do banco). |
| `tests/test_review_queue.py`, `tests/test_board_store.py` | Teste de migração JSON→SQLite. |

## Como funciona

- **Esquema**: `ideas(id, status, created_at, data)` e `cards(id, data)`, com o
  objeto completo serializado em `data` (JSON) — preserva todos os campos.
- **Concorrência**: `PRAGMA journal_mode=WAL`; a fila persiste por operação
  (upsert), o board em transação (DELETE+INSERT atômico).
- **Migração**: se o arquivo no caminho começa com `{` (JSON legado), importa os
  registros e recria como SQLite **no mesmo caminho** — transparente para o
  volume Docker existente.
- **`update(idea)`**: como o SQLite devolve objetos destacados, quem muta uma
  `Idea` fora dos setters persiste com `queue.update(idea)` (antes era `_save()`).

## Como validar

```bash
pytest -q tests/test_review_queue.py tests/test_board_store.py
# migração real: ao subir a API, output/review_queue.json e board.json viram SQLite
```

## Critério de aceite

- [x] Fila e board em SQLite (WAL).
- [x] Interface pública inalterada — 141 testes verdes.
- [x] Escrita concorrente sem corrupção (transações atômicas).
- [x] Migração automática do JSON existente (testada).

## Pendências / próximos

- (Opcional) migrar também `schedule.json`/`model_settings.json` (hoje pequenos e
  com escrita atômica).
