"""Publisher para TikTok (Content Posting API) — pré-configurado, requer credenciais.

Assinatura: `fn(idea) -> str`. Valida render e credenciais; o upload usa a
Content Posting API (inicializa o upload, envia o arquivo e publica). Dentro das
regras da plataforma — sem automação de evasão.

Variáveis: TIKTOK_ACCESS_TOKEN.
"""

from __future__ import annotations

import os
from pathlib import Path


def tiktok_publisher(idea) -> str:
    if not idea.video_path or not Path(idea.video_path).exists():
        raise RuntimeError("Renderize o vídeo antes de publicar (video_path ausente).")
    if not os.environ.get("TIKTOK_ACCESS_TOKEN"):
        raise RuntimeError("Credencial do TikTok ausente: TIKTOK_ACCESS_TOKEN.")
    # Content Posting API:
    #   POST /v2/post/publish/video/init/  (source_info do arquivo)
    #   upload do arquivo na upload_url retornada
    #   status/publish conforme o fluxo da API
    raise NotImplementedError(
        "Publicação no TikTok pré-configurada: falta completar o fluxo da "
        "Content Posting API (ver publishers/tiktok.py)."
    )
