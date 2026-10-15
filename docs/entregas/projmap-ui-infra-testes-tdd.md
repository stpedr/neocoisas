# ProjMap UI — Fase 1: infraestrutura de testes (Vitest + Playwright) e TDD

## Resumo
Segunda fase do plano de migração do frontend do ProjMap: `projmap/ui/`
ganha testes de verdade — Vitest + React Testing Library para unidade,
Playwright para e2e. A partir de agora, todo componente novo ou migrado leva
teste escrito antes (TDD).

## Motivação
O frontend do ProjMap não tinha nenhum framework de teste. Antes de começar
a trocar CSS puro por Tailwind/shadcn (Fase 2+), era preciso ter uma rede de
segurança — principalmente porque `app/lib/geometry.ts` (homografia, validação
de quad) é lógica crítica que não pode regredir silenciosamente numa
refatoração de UI.

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/ui/vitest.config.mts` (novo) | Config do Vitest: ambiente `jsdom`, plugin React, alias `@/*` |
| `projmap/ui/vitest.setup.mts` (novo) | Carrega `@testing-library/jest-dom` |
| `projmap/ui/playwright.config.mts` (novo) | `webServer` sobe `npm run dev` (porta 3100) sozinho antes dos testes |
| `projmap/ui/app/lib/geometry.test.ts` (novo) | 14 testes: `applyH`, `mul3`/`invert3`, `rectQuad`, `validateQuad` (quad válido, poucos cantos, coordenada inválida, degenerado, côncavo, autointersectante), `pointInQuad`, `homography4` |
| `projmap/ui/e2e/editor.spec.ts` (novo) | Smoke test: shell do editor carrega (nome do projeto, saída do projetor, atalho Mídias) |
| `projmap/ui/package.json` | Scripts `test`, `test:watch`, `test:e2e`; `@types/node` subiu pra `^22.12.0` (exigido pelo Vitest 5/Vite 8 como peer) |
| `projmap/ui/.gitignore` | `test-results/`, `playwright-report/` etc. |

## Como funciona
`vitest run` cobre funções puras de `app/lib/` em `jsdom`, sem precisar do
Next buildado. `playwright test` sobe o `next dev` sozinho (via `webServer`
do config) e roda num Chromium real.

**Achado real, não suposição:** o editor **exige falar com o mestre
(FastAPI) assim que carrega** — sem ele, mostra "Não foi possível falar com
o mestre. Ele está rodando?" e nada mais renderiza. Isso só apareceu rodando
o smoke test contra o `next dev` puro (o plano original presumia que a UI
teria algum fallback, como o `InteractPanel` tem para `--no-interact`). O
smoke test mocka `GET /api/project` com `page.route()` para validar só o
shell da UI; testes que precisam da integração real (ex.: arrastar canto de
superfície, Fase 6) vão precisar subir o mestre de verdade.

## Como validar
```bash
cd projmap/ui
npm run test        # 14 passed
npm run test:e2e    # 1 passed (sobe o next dev sozinho)
npm run build        # export estático continua OK
```
Backend não foi tocado: `pytest -q` (raiz, venv do ProjMap) continua 464 verdes.

## Critério de aceite
- [x] `npm run test` verde
- [x] `npm run test:e2e` verde
- [x] `npm run build` continua OK (export estático intacto)
- [x] `pytest -q` do backend continua 100% verde
- [x] Convenção registrada: TDD a partir de agora (teste antes do componente/rota)

## Pendências / próximos
- Fase 2 do plano: Tailwind + shadcn/ui, tokens + primeiro componente piloto.
- Testes e2e que tocam a API real (ex.: salvar projeto) vão precisar subir o
  mestre de verdade como fixture — ainda não configurado.
