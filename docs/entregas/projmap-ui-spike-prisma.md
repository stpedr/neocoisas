# ProjMap UI — Fase 0: spike de viabilidade do Prisma (`prisma-client-py`)

## Resumo
Primeira fase do plano de migração do frontend do ProjMap (Tailwind +
shadcn/ui + Framer Motion + Three.js + PWA + Prisma + TDD): validar, antes
de desenhar o schema real, se `prisma-client-py` + SQLite funciona nativo no
Windows, sem Docker. Funciona — registrado como decisão **D9** em
`docs/projmap/PLANO.md`.

## Motivação
Prisma ORM foi pedido para o catálogo/biblioteca/presets do ProjMap, mas o
client oficial do Prisma é Node/TS e o backend do ProjMap é Python
(FastAPI). `prisma-client-py` é a ponte, mas é um pacote comunitário — valia
a pena confirmar antes de comprometer o schema definitivo (Fase 8).

## O que mudou
Nada em produção — é um spike descartável. Mudou só a documentação:

| Arquivo | Mudança |
|---|---|
| `docs/projmap/PLANO.md` | Nova linha **D9** na tabela de decisões + nota de revisão parcial de D6 (PWA funciona pro editor/remote; sensor continua limitado pela câmera) |
| `docs/entregas/projmap-ui-spike-prisma.md` | Este arquivo |

## Como funciona
Instalado `prisma` (pacote `prisma-client-py`, traz `nodeenv`/`tomlkit`) na
`.venv-projmap`. Schema mínimo (1 model, `datasource sqlite`) em
`projmap/master/db/schema.prisma` (removido depois do spike — é descartável,
o schema real vem na Fase 8). Rodado:

```bash
export PATH="$PWD/.venv-projmap/Scripts:$PATH"   # necessário: o CLI do Prisma é Node e spawna prisma-client-py.exe por PATH
python -m prisma generate --schema=projmap/master/db/schema.prisma
python -m prisma db push --schema=projmap/master/db/schema.prisma
```

Client assíncrono gerado criou e leu um registro real
(`db.spikeping.create(...)` + `find_unique(...)`) contra um arquivo SQLite
criado na hora, sem Docker, sem servidor externo.

**Achados:**
- O CLI do Prisma (Node) precisa do `Scripts/` da venv no `PATH` pra achar o
  executável `prisma-client-py.exe` gerado pelo pip — sem isso, falha com
  `spawn prisma-client-py ENOENT`. Fácil de documentar (ativar a venv
  normalmente já resolve; só falha quando se chama o `python.exe` pelo
  caminho absoluto sem ativar).
- O binário do query engine (Rust) foi cacheado em
  `~/.cache/prisma-python/binaries/5.17.0/` — baixado uma vez, reusado nas
  chamadas seguintes. Precisa de internet na primeira vez.
- `enum` do Prisma **não é suportado** com `provider = "sqlite"` — campos
  tipo `status` vão precisar ser `String` + validação Pydantic no schema
  real da Fase 8.
- Não precisou instalar Node separado: usou o Node já presente no sistema
  (v22) via os console scripts da venv.

## Como validar
```bash
cd projmap/master/db          # (recriar o schema.prisma mínimo se quiser repetir)
export PATH="$PWD/../../../.venv-projmap/Scripts:$PATH"
python -m prisma generate --schema=schema.prisma
python -m prisma db push --schema=schema.prisma
```
`pytest -q` não muda (nenhum código de produção foi tocado): continua 452
verdes.

## Critério de aceite
- [x] `prisma generate` funciona nativo no Windows, sem Docker
- [x] `prisma db push` cria o SQLite sem servidor externo
- [x] Client assíncrono gerado escreve e lê um registro real
- [x] Decisão registrada em `docs/projmap/PLANO.md` (D9)
- [x] Nenhum código de produção alterado; artefatos do spike removidos

## Pendências / próximos
- Fase 1 do plano (infraestrutura de testes do frontend: Vitest + Playwright,
  TDD) é a próxima.
- O schema real (`Show`, biblioteca, presets, histórico) só entra na Fase 8,
  depois de Tailwind/shadcn/Framer Motion/PWA.
