"""Publisher para o YouTube (Data API v3) — pré-configurado, requer credenciais.

Assinatura de um publisher: `fn(idea) -> str` (devolve a URL/ID do post).

O upload real usa a YouTube Data API v3 com OAuth. Este módulo já valida o
pré-requisito (vídeo renderizado) e as credenciais; a chamada de upload em si é
o único ponto a completar com a lib oficial `google-api-python-client` (deixada
fora das dependências até você optar por ela).
"""

from __future__ import annotations

import os
from pathlib import Path


def youtube_publisher(idea) -> str:
    """Publica o vídeo da `idea` no YouTube. Requer render + credenciais OAuth."""
    if not idea.video_path or not Path(idea.video_path).exists():
        raise RuntimeError(
            "Renderize o vídeo antes de publicar (video_path ausente). "
            "Use POST /api/ideas/{id}/render."
        )

    faltando = [
        var
        for var in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
        if not os.environ.get(var)
    ]
    if faltando:
        raise RuntimeError(
            "Credenciais do YouTube ausentes: " + ", ".join(faltando) + ". "
            "Configure-as (OAuth) para habilitar a publicação."
        )

    # --- Ponto a completar -------------------------------------------------
    # Com as credenciais presentes, faça o upload via YouTube Data API v3:
    #   from googleapiclient.discovery import build
    #   from google.oauth2.credentials import Credentials
    #   creds = Credentials(None, refresh_token=..., client_id=..., client_secret=...,
    #                       token_uri="https://oauth2.googleapis.com/token")
    #   youtube = build("youtube", "v3", credentials=creds)
    #   ... videos().insert(part="snippet,status", body={...},
    #                       media_body=MediaFileUpload(idea.video_path)) ...
    #   return f"https://youtu.be/{response['id']}"
    raise NotImplementedError(
        "Upload ao YouTube pré-configurado, mas a chamada final precisa ser "
        "completada com google-api-python-client (ver comentário em publishers/youtube.py)."
    )
