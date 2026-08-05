# Entrega: Fundação de design (tokens, tema, responsivo, a11y)

> Sprint 10 · Design & UX — primeira leva (fundação), a partir do levantamento.

## Resumo

Reescreve o `globals.css` como um **design system** coeso (tokens de cor,
tipografia, espaçamento, raio, sombra), adiciona **tema claro** (via
`prefers-color-scheme` + `data-theme`), **responsividade mobile** e as bases de
**acessibilidade** (foco visível, roles de abas). Sem quebrar componentes — os
nomes de classe foram preservados.

## Motivação

O design era funcional porém básico: dark hardcoded, estilos inline espalhados,
sem escala tipográfica/espacial, pouco responsivo e sem foco a11y. Esta leva dá a
fundação que melhora o app inteiro de uma vez.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `web/app/globals.css` | Tokens (cores/tipografia/espaço/raio/sombra), **tema claro/escuro**, foco `:focus-visible`, abas roláveis, `@media` mobile (board/tabs/deck/stats), utilitários **toast** e **skeleton**, refinamento de todos os componentes. |
| `web/app/page.tsx` | Abas com `role="tablist"/tab"` + `aria-selected` e `tabpanel`; lista de abas fatorada. |

## Como funciona

- **Tokens**: paleta e escala em variáveis CSS; claro/escuro trocam só os tokens.
- **Tema claro**: segue o sistema (`prefers-color-scheme`) e aceita override por
  `:root[data-theme=...]` (base para o futuro alternador).
- **Responsivo**: container/tabs/deck/board/stats adaptam em ≤720px (alvo 375px).
- **a11y**: foco visível padronizado; abas com semântica de tablist.
- **Toast/Skeleton**: classes prontas para a próxima leva (feedback).

## Como validar

```bash
cd web && npm run build   # compila
# abrir http://localhost:3000 e alternar o tema do SO (claro/escuro)
```

## Critério de aceite

- [x] Design system em tokens (sem paleta hardcoded espalhada).
- [x] Tema claro e escuro.
- [x] Responsivo em telas pequenas.
- [x] Foco visível + semântica de abas. Build OK.

## Pendências / próximos (Sprint 10)

- Toasts/skeletons **ligados** nas views (substituir alerts inline).
- Alternador de tema (botão), player de vídeo, Kanban visual, dashboard SVG,
  branding/favicon/header, extração de componentes React base.
