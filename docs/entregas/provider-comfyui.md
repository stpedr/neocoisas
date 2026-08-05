# Entrega: Provider ComfyUI (imagem + text-to-video local)

> Mídia local grátis — geração via workflows do usuário no ComfyUI.

## Resumo

Adiciona o **ComfyUI** como provider local para **imagem** e **text-to-video**,
usando *workflows* que você exporta do ComfyUI em **formato API** com o marcador
`%prompt%`. Roda na sua GPU, offline, sem custo.

## Motivação

Completa a trilha "tudo local e grátis": além do A1111 (imagem) e do Ken Burns,
o ComfyUI abre imagem avançada (SDXL/Flux) e **text-to-video** local
(AnimateDiff, LTX-Video, CogVideoX) — no mesmo padrão de factory por capacidade.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `agents/media/comfyui.py` (novo) | `comfyui_image`/`comfyui_video`; submissão `/prompt`, polling `/history`, download `/view`; `inject_prompt` e `find_output_files` puros. |
| `agents/media/factory.py` | Providers `comfyui` (imagem e vídeo). |
| `docker-compose.yml` | `COMFYUI_URL`/`COMFYUI_*_WORKFLOW`, bind-mount `./comfyui` e `extra_hosts`. |
| `.env.example`, `comfyui/README.md` | Config + guia de exportação do workflow. |
| `tests/` | `inject_prompt`, `find_output_files` e seleção dos providers. |

## Como funciona

1. Você exporta o workflow no ComfyUI ("Save (API Format)") com `%prompt%` no
   nó de texto e salva em `./comfyui/image_api.json` / `video_api.json`.
2. O provider injeta o prompt de cada cena, submete via API, aguarda a execução
   e baixa a saída (imagem, ou vídeo do nó VideoCombine/VHS — convertido p/ mp4
   se preciso).
3. Ativação por `.env`: `ANE_IMAGE_PROVIDER=comfyui` e/ou `ANE_VIDEO_PROVIDER=comfyui`.

## Como validar

```bash
pytest -q tests/test_comfyui.py tests/test_media_factory.py
# ao vivo: ComfyUI rodando + workflows em ./comfyui, então renderizar uma ideia
```

## Critério de aceite

- [x] Imagem e text-to-video locais via ComfyUI (sem chave/custo).
- [x] Workflow do usuário via `%prompt%` (formato API).
- [x] Saída de vídeo normalizada para mp4. 151 testes verdes.

## Pendências / próximos

- Expor seleção de workflow na aba ⚙️ Modelos.
- Templates de exemplo (dependem dos modelos instalados pelo usuário).
