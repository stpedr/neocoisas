# Entrega: Dashboard em SVG + branding/favicon/header

> Sprint 10 · Design & UX — cards de **baixa prioridade** (fecham a Sprint 10).

## Resumo

Troca as barras de `<div>` do dashboard por um **gráfico SVG** real (views por
vídeo) com ícones nos KPIs, e adiciona **identidade**: favicon, header **fixo**
com **indicador de status da API** e tagline.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `web/app/components/DashboardView.tsx` | `renderBarChart` (SVG responsivo, cores por token) no lugar das divs; ícones nos KPIs. |
| `web/app/icon.svg` (novo) | Favicon (App Router auto-serve): quadrado com gradiente + play. |
| `web/app/page.tsx` | Header **sticky**, **status da API** (ping /health a cada 15s, bolinha verde/vermelha) e tagline. |
| `web/app/globals.css` | `.topbar` sticky + borda, `.status-dot`, tagline. |

## Como funciona

- **Gráfico SVG**: barras horizontais por vídeo (até 12), largura proporcional às
  views, rótulo truncado e valor ao lado; usa `var(--accent-2)` (segue o tema).
- **Favicon**: `app/icon.svg` é reconhecido automaticamente pelo Next.
- **Status da API**: `page.tsx` faz `api.health()` periódico e mostra 🟢/🔴 no
  cabeçalho, que agora fica fixo no topo ao rolar.

## Como validar

```bash
cd web && npm run build
# app: aba Dashboard mostra o gráfico SVG; ícone da aba do navegador (favicon);
# header fixo com bolinha de status (verde = API online).
```

## Critério de aceite

- [x] Dashboard com gráfico SVG (não divs) + ícones nos KPIs.
- [x] Favicon e branding.
- [x] Header fixo com status da API. Build OK.

## Resultado

**Sprint 10 · Design & UX concluída (9/9).**
