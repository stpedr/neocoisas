# Workflows do ComfyUI

Coloque aqui os workflows do ComfyUI **em formato API**, que o provider usa para
gerar **imagem** e **text-to-video** localmente (grátis, na sua GPU).

Esta pasta é montada no container em `/app/comfyui` (somente leitura).

## Como exportar um workflow (formato API)

1. Monte o workflow no ComfyUI (com os modelos que você tem instalados).
2. No campo de **texto do prompt positivo**, escreva exatamente `%prompt%` —
   o provider substitui isso pelo prompt de cada cena.
3. Ative *Settings → Enable Dev mode Options* e use **"Save (API Format)"**.
4. Salve os arquivos aqui:
   - `image_api.json` — workflow de imagem (ex.: SDXL/Flux)
   - `video_api.json` — workflow de text-to-video (ex.: AnimateDiff, LTX-Video,
     CogVideoX) — a saída deve ser um vídeo (nó VideoCombine/VHS).

## Ativar

No `.env`:

```
ANE_IMAGE_PROVIDER=comfyui        # imagem via ComfyUI
ANE_VIDEO_PROVIDER=comfyui        # text-to-video via ComfyUI (opcional; pesado)
COMFYUI_URL=http://host.docker.internal:8188
COMFYUI_IMAGE_WORKFLOW=/app/comfyui/image_api.json
COMFYUI_VIDEO_WORKFLOW=/app/comfyui/video_api.json
```

Depois `docker compose up -d`. O ComfyUI precisa estar rodando na sua máquina
(`python main.py` na pasta do ComfyUI). O container o alcança via
`host.docker.internal`.

> Observação: text-to-video local exige bastante GPU/VRAM. Para algo leve e
> grátis, use imagem (ComfyUI/A1111) + o movimento **Ken Burns** já embutido.
