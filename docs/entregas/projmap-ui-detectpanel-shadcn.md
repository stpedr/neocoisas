# ProjMap UI — Fase 3 (1/4): DetectPanel migrado para shadcn/ui

## Resumo
Primeiro dos 4 painéis do editor previstos na Fase 3 do plano de migração.
`DetectPanel.tsx` (detecção automática de superfícies) migrado de HTML/CSS
cru para `Card`, `Button`, `Checkbox` e `Slider` do shadcn/ui, com TDD.

## Motivação
Validar o padrão de migração num painel pequeno e autocontido antes de
encarar `SurfacePanel`/`EffectsSection`/`InteractPanel` — maiores e com mais
estado. Também completa os primitivos de base (`Button`, `Card`, `Checkbox`)
que faltavam desde a Fase 2 (só tínhamos `Slider`).

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/ui/app/components/ui/button.tsx` (novo) | `Button` (cva): variantes `default`/`primary`/`destructive`/`outline`/`ghost`; tamanhos `default`/`sm`/`block` |
| `projmap/ui/app/components/ui/card.tsx` (novo) | `Card`, `CardHeader`, `CardTitle` |
| `projmap/ui/app/components/ui/checkbox.tsx` (novo) | `Checkbox` (Radix) |
| `projmap/ui/app/globals.css` | `--color-border-strong` adicionado ao `@theme inline` (faltava) |
| `projmap/ui/app/components/DetectPanel.tsx` | `.card`/`.btn`/checkbox nativo/`<input range>` → primitivos shadcn |
| `projmap/ui/app/components/DetectPanel.test.tsx` (novo, **TDD**) | 7 testes escritos antes do refactor: sem foto desabilita o botão, detectar chama a API e devolve candidatos, zero candidatos avisa (não é erro), checkbox reflete `selected` e chama `onToggle`, "Criar N" habilita só com seleção, "Limpar" só aparece com candidatos |

## Como funciona
Mesmo padrão da Fase 2: nenhum valor novo, os componentes só trocam de
motor. `api.detect` é mockado com `vi.mock` (módulo real via
`importActual`, só a função `detect` vira `vi.fn()`) — os outros
componentes que forem migrar algo que fala com a API seguem esse padrão.

## Como validar
```bash
cd projmap/ui
npm run test   # 30 passed (14 geometry + 9 ColorControls + 7 DetectPanel)
npm run build   # OK — 142 kB First Load JS em "/" (era 138 kB)
```
Backend não foi tocado: `pytest -q` continua 464 verdes.

## Critério de aceite
- [x] `Button`/`Card`/`Checkbox` criados, consumindo os tokens já mapeados
- [x] `DetectPanel` migrado, teste escrito antes (TDD)
- [x] `npm run build` OK
- [x] Nenhuma outra tela tocada

## Pendências / próximos
Faltam 3 painéis da Fase 3: `SurfacePanel`, `EffectsSection`,
`InteractPanel` (`Select`/`Tabs`) — o card do Kanban fica em `review` até
os 4 estarem prontos.
