# ProjMap UI — Fase 3 (4/4): EffectsSection, InteractPanel e SurfacePanel migrados

## Resumo
Fecha a Fase 3 do plano de migração: os 3 painéis restantes do editor
(`EffectsSection`, `InteractPanel`, `SurfacePanel` — `DetectPanel` já tinha
sido feito numa entrega anterior) migrados para shadcn/ui, com TDD em cada
um. Completa os primitivos que faltavam: `Badge`, `Input`, `Select`.

## Motivação
Terminar a base de componentes do editor antes de entrar nas peças com
animação (`LayersPanel`/`MediaGallery`, Fase 4) e no `Editor.tsx` (Fase 6,
maior risco). `SurfacePanel` em particular escreve na superfície a cada
tecla/arraste — é o painel mais sensível a regressão de comportamento.

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/ui/app/components/ui/badge.tsx` (novo) | `Badge` (cva): `default`/`success`/`warning`/`destructive` |
| `projmap/ui/app/components/ui/input.tsx` (novo) | `Input` — texto/número |
| `projmap/ui/app/components/ui/select.tsx` (novo) | `Select` (Radix): `Trigger`/`Content`/`Item`/`Value` |
| `projmap/ui/app/components/EffectsSection.tsx` | `.btn`/`<input range/checkbox>` → `Button`/`Slider`/`Checkbox`; helpers locais `Field`/`Toggle` pra não repetir o padrão em cada efeito |
| `projmap/ui/app/components/InteractPanel.tsx` | `.pill`/`.status-box`/sliders/checkbox → `Badge`/`Slider`/`Checkbox`/`Button` |
| `projmap/ui/app/components/SurfacePanel.tsx` | `<select>` (Fonte/Ajuste/Mistura) → `Select`; sliders/checkbox/inputs → `Slider`/`Checkbox`/`Input`; botão excluir → `Button variant="destructive"` |
| `*.test.tsx` (3 novos, **TDD**) | 9 (EffectsSection) + 7 (InteractPanel) + 10 (SurfacePanel) = 26 testes, todos escritos antes do refactor |
| `projmap/ui/vitest.setup.mts` | +1 polyfill: `scrollIntoView` (Radix Select chama ao abrir, pra rolar até o item selecionado) |

## Como funciona
Mesmo padrão das fases anteriores — primitivos, não valores novos. Três
achados reais ao longo do caminho (não supostos, pegos rodando os testes):

1. **`<input type="range">` nativo não responde a `ArrowRight` no jsdom**
   (comportamento de *stepping* por teclado é implementado pelo motor de
   renderização nativo do browser, que o jsdom não simula) — em 3 dos 4
   componentes, essa era a ÚNICA parte que falhava contra o código antigo.
   Migrar pro `Slider` (que implementa o keydown em JS puro) fecha essa
   lacuna de verdade, não é só estético.
2. **`Element.prototype.scrollIntoView` não existe no jsdom** — Radix Select
   chama ao abrir o dropdown. Polyfill no mesmo padrão dos anteriores
   (`ResizeObserver`, Pointer Capture).
3. **Campo controlado sem estado real "luta" contra a digitação em teste**
   (`SurfacePanel.test.tsx`, campo Nome): sem um wrapper que de fato aplica
   o reducer de volta no `surface`, "limpar + digitar" produz um valor
   diferente do esperado a cada keystroke, porque o React força o campo de
   volta pro valor antigo do prop entre uma tecla e outra. Corrigido com um
   harness local que replica o que `page.tsx` faz de verdade.

`SurfacePanel` também revelou uma regra de negócio que meu primeiro teste
entendeu errado: o aviso "Nenhum arquivo deste tipo no projeto ainda" só
aparece quando a superfície **não tem mídia nenhuma** (`!s.source.media`) —
trocar de um tipo com mídia pra outro tipo vazio não mostra o aviso, porque
a mídia antiga continua valendo até o operador escolher algo novo. Esse
comportamento foi preservado como estava; só o teste estava errado.

## Como validar
```bash
cd projmap/ui
npm run test        # 56 passed (14+9+7+9+7+10)
npm run test:e2e    # 1 passed
npm run build        # OK — 166 kB em "/" (era 142 kB, Select do Radix pesa)
```
Backend não foi tocado: `pytest -q` continua 464 verdes.

## Critério de aceite
- [x] `Badge`/`Input`/`Select` criados
- [x] EffectsSection, InteractPanel, SurfacePanel migrados, teste antes do refactor
- [x] Nenhuma regressão de comportamento (26 testes cobrindo os fluxos de escrita no projeto)
- [x] `npm run build` OK
- [x] `pytest -q` do backend continua 100% verde

## Pendências / próximos
Fase 3 completa. Próxima: Fase 4 — `LayersPanel` (Framer Motion no reorder)
e `MediaGallery` (`Dialog` do shadcn).
