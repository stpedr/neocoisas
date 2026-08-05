# Entrega: Mídia 100% local e gratuita (imagem SD + movimento)

> Resposta ao "dá pra gerar imagem/vídeo local sem pagar?" — **sim**.

## Resumo

Adiciona geração de **imagem local grátis** via **Stable Diffusion** (AUTOMATIC1111
na GPU do usuário, como o Ollama) e **movimento Ken Burns** (zoom/pan) nas imagens
— transformando slides em "vídeo" **sem modelo de vídeo pago** e sem chave.

## Motivação

As opções de imagem/vídeo eram placeholder (grátis, mas estático) ou Gemini
Imagen/Veo (pago/quota). Faltava o meio-termo: **qualidade real, local e grátis**.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `agents/media/providers.py` | `a1111_image()` — chama a API do AUTOMATIC1111 (`/sdapi/v1/txt2img`) e salva a imagem. |
| `agents/media/factory.py` | Provider de imagem `a1111`. |
| `agents/video_pipeline.py` | `motion` (Ken Burns via `zoompan`) no caminho de imagem; `_subtitle_clause` extraído; `_audio_duration` (ffprobe). |
| `render.py` | Liga `motion` (config/env `ANE_MOTION`, padrão on; não se aplica a vídeo por cena). |
| `docker-compose.yml` | `A1111_URL`, `ANE_MOTION` + `extra_hosts` (host.docker.internal). |
| `config.example.json`, `.env.example` | `motion`, `image_provider=a1111`, `A1111_URL`. |
| `tests/` | Seleção do provider `a1111` + Ken Burns (zoompan). |

## Como usar (imagem local grátis)

1. Rode o **AUTOMATIC1111** com a API ligada (na sua GPU):
   ```bash
   ./webui.sh --api    # ou webui-user.bat com --api (Windows)
   ```
2. No `.env`: `ANE_IMAGE_PROVIDER=a1111` (e `A1111_URL` se não for o padrão).
3. `docker compose up -d` → a API alcança o SD no host via `host.docker.internal`.

Vídeo grátis local = imagem SD + **Ken Burns** (movimento) + narração **Piper** +
legendas. Text-to-video generativo local (ComfyUI + AnimateDiff/LTX-Video) é
possível, mas exige bastante GPU — fica como opção futura no mesmo padrão de factory.

## Como validar

```bash
pytest -q tests/test_video_pipeline.py tests/test_media_factory.py
# render com Ken Burns (sem SD): já usa zoompan nas imagens placeholder
```

## Critério de aceite

- [x] Imagem local grátis (Stable Diffusion via A1111).
- [x] Movimento Ken Burns nas imagens (vídeo "vivo" sem modelo pago).
- [x] Tudo local/offline, sem chave. 145 testes verdes.

## Pendências / próximos

- Provider **ComfyUI** (imagem e/ou text-to-video local via AnimateDiff/LTX).
- Expor `A1111`/motion na aba ⚙️ Modelos.
