# ProjMap UI — Fase 2: Tailwind + shadcn/ui, tokens e primeiro componente piloto

## Resumo
Terceira fase do plano de migração: `projmap/ui/` ganha Tailwind CSS (v4) e
o primeiro primitivo shadcn/ui (`Slider`, Radix), consumindo os tokens já
mapeados em `docs/planejamento/design-system-projmap-ui.md`. `ColorControls.tsx`
é o componente piloto — migrado de `<input type="range">` cru para o `Slider`.

## Motivação
Validar o pipeline inteiro (Tailwind v4 + PostCSS + tokens + Radix + build
estático) com o menor risco possível, antes de tocar nos painéis maiores do
editor (Fase 3) ou no `Editor.tsx` (Fase 6, o de maior risco). `ColorControls`
foi escolhido por ser pequeno, autocontido, e já ter funções puras
(`isNeutral`, `cssFilter`) que servem de rede de segurança no refactor.

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/ui/postcss.config.mjs` (novo) | `@tailwindcss/postcss` (Tailwind v4, instalado como `tailwindcss@4`) |
| `projmap/ui/app/globals.css` | `@import "tailwindcss"`; tokens shadcn (`--background`, `--primary`, `--destructive`...) como **aliases** dos tokens atuais (`var(--bg)`, `var(--accent)`...) — nenhum valor duplicado; `@theme inline` expõe tudo como utilitário Tailwind (`bg-background`, `text-foreground`...) |
| `projmap/ui/app/lib/utils.ts` (novo) | `cn()` (clsx + tailwind-merge), padrão shadcn |
| `projmap/ui/app/components/ui/slider.tsx` (novo) | `Slider` (Radix `react-slider`), bindado a `--primary`/`--secondary`/`--ring` |
| `projmap/ui/app/components/ColorControls.tsx` | `<input type="range">` → `<Slider>`; `onChange(event)` → `onValueChange([v])`; resto do comportamento (duplo clique reseta, modo `compact`) preservado |
| `projmap/ui/app/components/ColorControls.test.tsx` (novo, **TDD**) | 9 testes escritos **antes** do refactor — rodei contra o `<input>` original pra confirmar red, depois troquei pro `Slider` até dar green |
| `projmap/ui/vitest.setup.mts` | 2 polyfills de jsdom descobertos rodando os testes: `ResizeObserver` (Radix `useSize`) e Pointer Capture API (`setPointerCapture`/`hasPointerCapture`); `afterEach(() => cleanup())` explícito — RTL só faz auto-cleanup se achar um `afterEach` global, e `test.globals` não está ligado no `vitest.config.mts` |

## Como funciona
Tailwind v4 não usa mais `tailwind.config.ts` com `theme.extend.colors` —
os tokens são declarados em CSS (`@theme inline`) e viram classes
automaticamente. Para não duplicar valores, os novos tokens shadcn
**referenciam** as variáveis já existentes (`--primary: var(--accent);`), que
já reagem ao `@media (prefers-color-scheme: light)` — então o claro/escuro
já funciona pros componentes novos sem nenhum código extra. O token `--accent`
do shadcn (destaque/hover sutil) tem nome próprio (`--accent-ui`) pra não
colidir com o `--accent` de marca do app (mapeado pra `--primary`) — a mesma
distinção já registrada no doc de design system.

## Como validar
```bash
cd projmap/ui
npm run test        # 23 passed (14 de geometry.ts + 9 de ColorControls)
npm run test:e2e    # 1 passed
npm run build        # export estático OK
```
Bundle da rota `/` foi de 119 kB para 138 kB de First Load JS (Radix Slider +
CSS do Tailwind) — vale acompanhar essa métrica nas próximas fases, igual o
plano já previa pro Three.js (Fase 9).

Backend não foi tocado: `pytest -q` (raiz, venv do ProjMap) continua 464 verdes.

## Critério de aceite
- [x] `npm run build` sem erro, Tailwind v4 compilando
- [x] Teste escrito antes do refactor (TDD real, não só "tem teste")
- [x] Nenhuma outra tela tocada além de `ColorControls.tsx`
- [x] Tokens shadcn são aliases dos tokens atuais, não valores duplicados
- [x] `pytest -q` do backend continua 100% verde

## Pendências / próximos
- Fase 3: `SurfacePanel`, `EffectsSection`, `InteractPanel`, `DetectPanel` →
  `Select`/`Tabs` do shadcn, um por vez.
- Verificação visual ao vivo (não só DOM/testes) depende do mestre
  (`python -m projmap.master`) rodando — fora do alcance desta sessão
  (sandbox sem GPU/display).
