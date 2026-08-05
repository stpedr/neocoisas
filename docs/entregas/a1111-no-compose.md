# Entrega: Stable Diffusion (A1111) no docker-compose

> Sprint 2 · Geração de mídia — subir a imagem local junto com a stack.

## Resumo

Adiciona o **AUTOMATIC1111** como serviço opt-in no `docker-compose` (profile
`sd`, GPU NVIDIA, volumes de modelo/saída), para gerar **imagem local grátis** na
GPU — sem depender de instalação nativa e sem serviço pago.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `docker-compose.yml` | Serviço `a1111` (image `ghcr.io/neggles/sd-webui-docker`, `--api --listen`), profile `sd`, `deploy.devices nvidia`, volumes `a1111_data`/`a1111_out`. |
| `.env.example` | Como apontar `A1111_URL` (nativo `host.docker.internal:7860` vs compose `a1111:7860`). |
| Kanban | Cards "A1111 no docker-compose" e "Validar render com imagem real". |

## Como usar

```bash
# 1) .env: imagem real via SD do compose
ANE_IMAGE_PROVIDER=a1111
A1111_URL=http://a1111:7860

# 2) sobe a stack + o SD (precisa de GPU NVIDIA no Docker)
docker compose --profile sd up -d
```

Requisitos: **GPU NVIDIA** exposta ao Docker (runtime `nvidia`) e um **checkpoint**
de modelo no volume `a1111_data` (o A1111 baixa/uso conforme o que você colocar).
Sem GPU no Docker, rode o A1111 **nativo** no Windows e use
`A1111_URL=http://host.docker.internal:7860`.

## Critério de aceite

- [x] Serviço A1111 no compose (profile `sd`, GPU, volumes), `compose config` válido.
- [x] `A1111_URL` documentado (nativo vs compose).
- [ ] Render com imagem real validado (depende do modelo/boot do A1111).

## Pendências / próximos

- Validar o render com imagem real quando o A1111 subir e tiver um checkpoint.
- (Opcional) auto-download de um checkpoint padrão no volume.
