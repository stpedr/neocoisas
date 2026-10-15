# Design system do ProjMap UI — auditoria + base para a migração

> Insumo para o plano de migração do frontend do ProjMap (`projmap/ui/`) para
> Tailwind + shadcn/ui + Framer Motion + Three.js + PWA. Não é uma entrega —
> é o levantamento que alimenta esse plano.

## Resumo da auditoria

| | |
|---|---|
| Componentes revisados | 13 (`app/components/`) + 3 páginas (`page.tsx`, `remote/page.tsx`, `sensor/page.tsx`) |
| Linhas de TSX | ~4.300 |
| Tokens de cor hoje | **13**, centralizados em `app/globals.css` (`:root` + `@media (prefers-color-scheme: light)`) — boa notícia: já existe disciplina de tokens, não é CSS solto por componente |
| Framework de estilo | CSS puro com classes utilitárias próprias (`.btn`, `.card`, `.panel`…) — **sem Tailwind** |
| Componentes de UI prontos (Radix/shadcn) | nenhum — tudo é HTML nativo estilizado à mão |
| Testes de frontend | nenhum (`vitest`/`jest`/Playwright ausentes) |
| Hardcoded fora dos tokens | 20 ocorrências, **todas em `Editor.tsx`** — são cores de pintura do `<canvas>` (alças de canto, contorno de superfície), não CSS; só dá pra resolver lendo `getComputedStyle` em tempo de render (já é feito para `--canvas-bg`, falta para o resto) |

**Veredito geral:** a base é mais saudável do que o normal pra migrar — os
tokens já existem e são usados de forma consistente. O trabalho real é
**trocar o motor** (CSS puro → Tailwind + shadcn) sem perder o que os tokens
já capturam, não "inventar" um design system do zero.

## Tokens atuais → mapeamento para shadcn/Tailwind

shadcn usa uma convenção fixa de CSS vars (consumida por `tailwind.config` via
`hsl(var(--x))`). Mapeamento 1:1 proposto:

| Token atual (`globals.css`) | Valor (escuro) | Valor (claro) | Var shadcn |
|---|---|---|---|
| `--bg` | `#0b0f17` | `#f6f8fc` | `--background` |
| `--text` | `#e8eef6` | `#0f172a` | `--foreground` |
| `--bg-elev` | `#141a24` | `#ffffff` | `--card` (+ `--popover`) |
| `--text` (sobre `--bg-elev`) | — | — | `--card-foreground` / `--popover-foreground` |
| `--accent` / `--accent-2` (gradiente) | `#7c5cff` → `#4f8cff` | idem | `--primary` (sólido = `--accent`; o gradiente vira um util Tailwind à parte, shadcn não modela gradiente) |
| `--bg-elev-2` | `#1b2331` | `#f0f3f9` | `--secondary` / `--muted` |
| `--text-dim` | `#94a3b8` | `#64748b` | `--muted-foreground` |
| `--red` / `--red-soft` | `#f87171` / 14% | idem | `--destructive` / `--destructive` com opacidade (Tailwind `/10`) |
| `--border` / `--border-strong` | `#263041` / `#33415a` | `#e2e8f0` / `#cbd5e1` | `--border` (shadcn só tem um nível — os dois níveis atuais viram `border` vs `border` com `hover:border-strong` custom) |
| `--focus` | `0 0 0 3px rgba(124,92,255,.45)` | idem | `--ring` |
| `--radius` / `--radius-sm` | `14px` / `10px` | idem | `--radius` (shadcn deriva `sm`/`md`/`lg` de um valor só — manter os dois como `--radius` e `--radius-sm` customizados é mais fiel ao visual atual que forçar na escala padrão) |
| `--green` | `#34d399` | idem | token custom `--success` (shadcn não tem "success" por padrão — extensão comum, mantém) |
| `--amber` | `#fbbf24` | idem | token custom `--warning` |
| `--canvas-bg` | `#05070b` | `#1e293b` | fica fora do sistema shadcn (é cor de pintura do canvas, não de UI) — resolver via `getComputedStyle` como já é feito |
| Paleta de superfícies (`COLORS` em `Editor.tsx`, 8 cores) | `#7c5cff #34d399 #4f8cff #fbbf24 #f87171 #22d3ee #e879f9 #a3e635` | mesma | promover a um token nomeado (`--surface-palette`, lista) em vez de array hardcoded no componente — é visual, não estrutural, mas hoje só existe em um arquivo TS |

**Decisão proposta:** manter os **dois tokens de borda** (`--border` /
`--border-strong`) e **dois de raio** (`--radius` / `--radius-sm`) como
extensões sobre a base shadcn — eles já carregam uma distinção visual real
(hover state, cards vs. botões pequenos) que a convenção padrão do shadcn não
cobre, e achatar os dois pra um só muda a aparência atual sem necessidade.

## Inventário de componentes → equivalente shadcn/ui

| Componente atual | O que faz | Primitivo shadcn/ui | Nota de migração |
|---|---|---|---|
| `.btn` / `.btn-accent` / `.btn-danger` / `.btn-small` (classes, não componente) | Botão com 4 variantes informais | `Button` (variants: `default`, `destructive`, `outline`, `ghost`; sizes: `sm`,`default`) | 1:1 direto — é exatamente o que o `Button` do shadcn modela |
| `.segmented` | Toggle de modo (Foto/Projetor, etc.) | `Tabs` (visual "segmented", não conteúdo em abas) ou `ToggleGroup` (Radix) | `ToggleGroup` é a escolha certa — é exclusivo, não navegação |
| `card` genérico (`.card`, `.card-head`) | Container de seção no painel (Superfície, Camadas, Interativo…) | `Card` + `CardHeader` + `CardContent` | 1:1 |
| `LayersPanel.tsx` (229 linhas) — lista de camadas com ▲▼, reordenar | Lista reordenável | `Card` + lista própria; reorder fica com **dnd-kit** (shadcn não cobre drag-and-drop) | Framer Motion entra aqui: `layout` animations na reordenação (ver seção Motion) |
| `SurfacePanel.tsx` (241 linhas) | Formulário da superfície selecionada (fonte, ajuste, opacidade…) | `Select`, `Slider`, `Tabs` | Maior refactor de formulário — bom candidato a ser o primeiro a migrar (ver plano) |
| `MediaGallery.tsx` / `ImageCard.tsx` / `LibraryCard.tsx` / `SuggestAll.tsx` | Galeria modal com grid/strip de mídia, busca, sugestões | `Dialog` (modal) + `Command` (busca) + grid custom | O modal (`.gallery-backdrop`) vira `Dialog`; grid de cards fica custom (shadcn não tem "media grid") |
| `DetectPanel.tsx` | Lista de regiões detectadas (toggle marcar/desmarcar) + sensibilidade | `Slider` + `Checkbox`/`Toggle` em lista | 1:1 |
| `ColorControls.tsx` | Sliders de brilho/gama/contraste/saturação/temperatura + presets | `Slider` + `ToggleGroup` (presets) | 1:1 |
| `InteractPanel.tsx` (228 linhas) | Texto→cena (NLP), presets, sensor, debug | `Textarea` + `Select` + `Badge` (origem llm/fallback) | 1:1 |
| `EffectsSection.tsx` | Seleção de efeito do visual_frames + ajustes | `Select` + `Slider` | 1:1 |
| `RemoteCard.tsx` + QR | Card "Remote no celular" com QR | `Card` + `Dialog` (mostrar QR em destaque) | 1:1 |
| `.toast` (`.toast-ok`/`.toast-err`) | Feedback de salvar/erro | `Sonner` (toast do shadcn, já substitui `react-hot-toast`) | 1:1, ganha fila/stacking de graça |
| `remote/page.tsx` (460 linhas) — blackout, dimmer, looks | Painel de controle mobile-first | `Button` (blackout = `destructive` grande), `Slider` (dimmer), grid de `Card` (looks) | Candidato forte a ganhar Framer Motion (feedback tátil do blackout) |
| `sensor/page.tsx` (290 linhas) | Página do sensor-celular (câmera + status) | majoritariamente custom (vídeo/canvas) + `Badge` de status | Baixa prioridade de redesenho — é uma tela de operação, não de uso recorrente |

Não existe hoje nenhum componente que já seja "quase shadcn" — o ganho maior
vem de **`Button`, `Card`, `Slider`, `Select`, `Dialog`, `ToggleGroup`,
`Sonner`**, que cobrem a maior parte das 13 superfícies.

## Onde entra o Framer Motion

Pontos concretos, não genéricos:
1. **Reordenar camadas** (`LayersPanel`) — `layout` prop do Framer Motion nos itens da lista: a troca de posição anima em vez de "piscar".
2. **Abrir/fechar a galeria** (`MediaGallery`, hoje `.gallery-backdrop`) — `AnimatePresence` no backdrop + scale/opacity no modal.
3. **Blackout no remote** — transição de cor (vermelho ligando) com `animate` em vez de `background` instantâneo; é o controle mais crítico do show, merece feedback claro de que o toque registrou.
4. **Seleção de superfície/camada no editor** — destaque (contorno) com uma pequena animação de "pulso" ao selecionar.
5. **Toasts** — se não for pro `Sonner` do shadcn direto, entrada/saída com `AnimatePresence`.

Fora disso: **nada de animação decorativa**. O editor é uma ferramenta de
precisão (arrastar cantos em pixel); animação ali é ruído, não polish.

## Onde entra o Three.js

Um único ponto, opcional e isolado: **prévia 3D do mapeamento** — uma cena
simples (plano = parede, quads = superfícies projetadas, uma câmera livre)
pra conferir a disposição espacial sem depender só da foto 2D. Isso é
**novo**, não existe hoje (o editor é 100% 2D sobre a foto).

- Entra como um componente isolado (`Scene3DPreview`), montado só quando o
  usuário abre essa visão — **não** no caminho crítico do editor 2D, que
  continua Canvas2D puro (é mais simples e já funciona).
- Dado de entrada: os mesmos quads de `core/project.py` (via API), convertidos
  pra um plano 3D arbitrário — não precisa de posição real de câmera/parede,
  é uma visualização auxiliar, não um gêmeo digital preciso.
- Risco a vigiar: `@react-three/fiber` + `@react-three/drei` puxam peso de
  bundle; como o build é **export estático**, isso só afeta o tempo de
  download inicial do editor (roda local, mas ainda baixa pela rede local/HD).

## PWA — o que já existe e o que falta

- Já existe `public/manifest.webmanifest`, mas com `start_url: "/remote/"` —
  **só cobre o remote do celular**, não o editor.
- `theme_color`/`background_color` (`#0b0f17`) já batem com o token `--bg`
  escuro — nenhuma inconsistência aqui.
- **Falta:** service worker (hoje dá pra "Adicionar à tela inicial" mas não
  funciona offline nem tem cache de assets), ícones em tamanhos fixos (hoje só
  tem um SVG `any`, bom para a maioria mas iOS historicamente quer PNG), e
  decidir **se o editor também vira app instalável** ou só remote/sensor
  (que são as telas usadas "no local", enquanto o editor tende a ser usado no
  mesmo PC do mestre, onde instalar como app agrega menos).

## Perguntas abertas pro plano de migração

1. Editor também vira PWA, ou só remote + sensor (como hoje)?
2. A paleta de 8 cores das superfícies (`COLORS` em `Editor.tsx`) vira token
   configurável pelo usuário, ou fica fixa (como hoje)?
3. `dnd-kit` para reordenar camadas, ou manter os botões ▲▼ atuais só com
   Framer Motion no feedback visual (mais barato, zero nova dependência de
   D&D)?
