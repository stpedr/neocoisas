# ProjMap UI — Fase 4: Camadas e Galeria (Framer Motion + Dialog)

## Resumo
Conclui a Fase 4 do plano de migração do frontend do ProjMap (`projmap/ui/`):
- Novo primitivo `Dialog` (`@radix-ui/react-dialog` + `AnimatePresence`/`motion.div` do Framer Motion com suporte a `useReducedMotion`).
- `LayersPanel` migrado para `Card`/`Button`/`Checkbox`/`Input`/`Select`/`Slider` do shadcn/ui + animação `layout` do Framer Motion nos itens da lista ao reordenar com `▲`/`▼` (sem introduzir `dnd-kit`).
- `MediaGallery`, `SuggestAll`, `LibraryCard` e `ImageCard` migrados para `Dialog`, `Button`, `Input` e `Checkbox` do shadcn/ui.
- 11 novos testes unitários em Vitest escritos antes do refactor (TDD) + 1 novo teste E2E em Playwright cobrindo a reordenação de camadas e abertura/fechamento da galeria modal.

## Motivação
`LayersPanel` (F9, prévia ao vivo das camadas) e `MediaGallery` (modal com abas de projeto, biblioteca local e Google Drive) concentravam o último bloco de modais e listas reordenáveis do editor antes de atacar o `remote/page.tsx` (Fase 5) e o shell do `Editor.tsx` (Fase 6).

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/ui/app/components/ui/dialog.tsx` (novo) | Primitivo `Dialog` (Radix) com `AnimatePresence` + `motion.div` no overlay e no conteúdo, respeitando `prefers-reduced-motion` |
| `projmap/ui/app/components/LayersPanel.tsx` | `.card`/`.btn`/inputs/select/slider → `Card`/`Button`/`Checkbox`/`Input`/`Select`/`Slider`; itens da lista em `motion.li layout` |
| `projmap/ui/app/components/MediaGallery.tsx` | `.gallery-backdrop`/`.gallery` → `Dialog`/`DialogContent`/`DialogHeader`/`DialogTitle`; busca e ações com `Input` e `Button` |
| `projmap/ui/app/components/SuggestAll.tsx` | `.gallery-backdrop` → `Dialog`; checkboxes e CTA com `Checkbox` e `Button` |
| `projmap/ui/app/components/LibraryCard.tsx` | Botões e campo de caminho migrados para `Button` e `Input` |
| `projmap/ui/app/components/ImageCard.tsx` | Botão de zerar ajustes e toggles de orientação (modo padrão) migrados para `Button` |
| `projmap/ui/app/components/LayersPanel.test.tsx` (novo, **TDD**) | 6 testes cobrindo criação de camada (`+ Cartela`, `+ Da galeria`), reordenação `▲`/`▼`, visibilidade, edição de propriedades/retângulo e `Slider` de opacidade via teclado |
| `projmap/ui/app/components/MediaGallery.test.tsx` (novo, **TDD**) | 5 testes cobrindo abertura/fechamento (`Escape` e botão), filtros de tipo/busca, importação de `Minhas pastas`, sugestões por superfície e `SuggestAll` |
| `projmap/ui/e2e/editor.spec.ts` | +1 teste E2E validando reordenação visual de camadas com `▲`/`▼` e abertura/fechamento do `Dialog` da galeria |
| `projmap/ui/vitest.setup.mts` | +1 polyfill: `HTMLMediaElement.prototype.play` retornando `Promise.resolve()` no jsdom |

## Como funciona
Três achados reais durante o ciclo TDD:
1. **`HTMLMediaElement.prototype.play` no jsdom retorna `undefined` e emite erro `Not implemented`**: quando `LayersPanel` adiciona uma mídia de vídeo, `mediaAspect()` em `app/lib/preview.ts` cria um `<video>` e chama `v.play().catch(...)`, o que levantava `TypeError: Cannot read properties of undefined (reading 'catch')` em ambiente de teste. Polyfillado em `vitest.setup.mts`.
2. **`<input type="range">` nativo de opacidade em `LayersPanel` não respondia a `ArrowLeft` no jsdom**: mesmo achado da Fase 3; ao migrar para o `Slider` do Radix, o ajuste fino por teclado passou a funcionar e ser testado.
3. **Ordem de composição `AnimatePresence` + `DialogPortal` (Radix)**: colocar `AnimatePresence` como filho direto de `DialogPortal` gerava warning de `ref` no `Presence` interno do Radix (`Function components cannot be given refs`). Envolver `DialogPortal` por fora com `AnimatePresence` mantém `DialogOverlay` e `DialogPrimitive.Content` (ambos `forwardRef` com `asChild` para `motion.div`) como filhos diretos do portal, eliminando qualquer warning.

## Como validar
```bash
cd projmap/ui
npm run test        # 67 passed (8 arquivos de teste)
npm run test:e2e    # 2 passed
npm run build       # OK — First Load JS em "/" = 213 kB (era 166 kB antes de Framer Motion + Radix Dialog)
```

## Critério de aceite
- [x] `Dialog` criado em `app/components/ui/dialog.tsx` com suporte a `useReducedMotion`
- [x] `LayersPanel`, `MediaGallery`, `SuggestAll`, `LibraryCard` e `ImageCard` migrados com TDD antes do refactor
- [x] Reordenação de camadas mantém botões `▲`/`▼` com animação `layout` do Framer Motion (sem `dnd-kit`)
- [x] Teste E2E cobrindo `LayersPanel` e `MediaGallery`
- [x] `npm run test`, `npm run test:e2e` e `npm run build` verdes e sem warnings

## Pendências / próximos
Fase 4 completa. Próxima: Fase 5 — `remote/page.tsx` (shadcn + feedback de Framer Motion no blackout + Sonner nos toasts).
