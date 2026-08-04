"""Publisher para Instagram Reels (Graph API) — pré-configurado, requer credenciais.

Assinatura: `fn(idea) -> str`. Valida render e credenciais; o upload em si usa a
Meta Graph API (publicação em 2 passos: criar container do Reel a partir de uma
URL de vídeo hospedada e depois publicar). Requer o vídeo acessível por URL
pública — ponto a integrar conforme sua hospedagem.

Variáveis: IG_USER_ID, IG_ACCESS_TOKEN.
"""

from __future__ import annotations

import os
from pathlib import Path


def instagram_publisher(idea) -> str:
    if not idea.video_path or not Path(idea.video_path).exists():
        raise RuntimeError("Renderize o vídeo antes de publicar (video_path ausente).")
    faltando = [v for v in ("IG_USER_ID", "IG_ACCESS_TOKEN") if not os.environ.get(v)]
    if faltando:
        raise RuntimeError(
            "Credenciais do Instagram ausentes: " + ", ".join(faltando) + "."
        )
    # A Graph API publica Reels a partir de uma URL pública do vídeo:
    #   POST /{IG_USER_ID}/media  (media_type=REELS, video_url=...)
    #   POST /{IG_USER_ID}/media_publish (creation_id=...)
    raise NotImplementedError(
        "Publicação no Instagram pré-configurada: falta expor o vídeo por URL "
        "pública e completar a chamada da Graph API (ver publishers/instagram.py)."
    )
