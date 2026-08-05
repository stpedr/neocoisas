# Entrega: Feedback — toasts, skeletons e estados de loading

> Sprint 10 · Design & UX — card de **prioridade alta**.

## Resumo

Substitui os alertas inline por um sistema de **toasts** global, adiciona
**skeletons** de carregamento e padroniza os estados de loading nas 5 abas.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `web/app/components/Toast.tsx` (novo) | `ToastProvider` + `useToast()` (fila com auto-dismiss, `aria-live`) e componente `Skeleton`. |
| `web/app/page.tsx` | App envolvido em `ToastProvider`. |
| `IdeasView`/`KanbanView`/`ScheduleView`/`ModelsView`/`DashboardView` | Erros/sucessos agora viram **toast** (fim dos `<div class="alert">` inline); Kanban ganha **skeleton** enquanto carrega. |

## Como funciona

- `useToast()(msg, "error" | "ok" | "info")` empilha um toast no canto inferior
  direito, com `aria-live="polite"` e sumiço automático (~4,5s).
- Os `catch` das views chamam o toast (via shim `setError`/`setOk`), sem poluir o
  layout com alertas fixos.
- `Skeleton` (shimmer via CSS) cobre o carregamento do Kanban; as demais abas
  usam texto de loading consistente.

## Como validar

```bash
cd web && npm run build
# no app: uma ação com erro (ex.: gerar sem Ollama) mostra um toast; o Kanban
# exibe skeletons ao abrir.
```

## Critério de aceite

- [x] Toasts globais para erro/sucesso (a11y `aria-live`).
- [x] Alerts inline removidos das views.
- [x] Skeleton de carregamento (Kanban) + loading consistente. Build OK.

## Pendências / próximos (Sprint 10)

- Alternador de tema (botão), player de vídeo + thumbnail, Kanban visual,
  dashboard com gráficos SVG, branding/favicon/header.
