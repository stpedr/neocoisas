# Entrega: Design — Kanban visual, player de vídeo, tema e a11y

> Sprint 10 · Design & UX — cards de **prioridade média** (+ conclusão do tema/a11y).

## Resumo

Melhorias visuais: **Kanban** com prioridade colorida e chips; **player de vídeo**
maior com poster (thumbnail) e **modal** de reprodução; **alternador de tema**
claro/escuro persistente; e conclusão das bases de **acessibilidade**.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `web/app/globals.css` | Bordas por prioridade no card (`prio-alta/media/baixa`), chips coloridos, `.vthumb`, `.modal*`, `.theme-toggle`. |
| `KanbanView.tsx` | Cor por prioridade + chip de prioridade; labels sem o `prioridade:` cru. |
| `IdeasView.tsx` | Preview vira thumbnail (poster) 9:16 que abre **modal** com player; usa `thumbnail_path`. |
| `page.tsx` | Botão **☀️/🌙** de tema (persistido em localStorage, aplica `data-theme`). |
| `lib/api.ts` | `thumbnailUrl(id)`; tipo `Idea` completo (thumbnail/variants/metrics/score). |

## Como funciona

- **Kanban visual**: a prioridade (`prioridade:*` nos labels) vira uma borda
  esquerda colorida (alta=vermelho, média=âmbar, baixa=azul) + um chip destacado.
- **Player**: cada aprovada com vídeo mostra uma miniatura 9:16 (com poster da
  thumbnail, se houver); clicar abre um modal com o player em tamanho cheio.
- **Tema**: o botão alterna claro/escuro, grava em `localStorage` e seta
  `data-theme` no `<html>` (que sobrepõe o `prefers-color-scheme`).

## Como validar

```bash
cd web && npm run build
# app: Kanban com cores por prioridade; aba Ideias → aprovada → clicar na
# miniatura abre o player em modal; botão de tema no topo alterna claro/escuro.
```

## Critério de aceite

- [x] Kanban com cores/labels por prioridade e contadores por coluna.
- [x] Player maior com poster + modal.
- [x] Alternador de tema persistente.
- [x] a11y: roles de aba, foco visível, aria-labels (toggle/modal/close). Build OK.

## Pendências / próximos (Sprint 10)

- Dashboard com gráficos SVG · Branding/favicon/header · extração de componentes React base.
