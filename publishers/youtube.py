"""Publisher para o YouTube (Data API v3).

Assinatura de um publisher: `fn(idea) -> str` (devolve a URL do vídeo publicado).

Faz o upload real via `google-api-python-client` usando credenciais OAuth
(refresh token). As credenciais vêm de variáveis de ambiente — configure-as no
`.env` (nunca no código/commit). Sem elas, levanta um erro claro.

Variáveis:
    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN  (obrigatórias)
    YOUTUBE_PRIVACY  (opcional: private | unlisted | public; padrão private)
    YOUTUBE_CATEGORY_ID  (opcional; padrão 22 = People & Blogs)
"""

from __future__ import annotations

import os
from pathlib import Path

_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _description(idea) -> str:
    linhas = [s.narration for s in idea.scenes if getattr(s, "narration", "").strip()]
    corpo = "\n".join(linhas)
    return f"{corpo}\n\n#shorts".strip()


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
            "Configure-as no .env (OAuth) para habilitar a publicação."
        )

    # Imports tardios: as libs do Google só são necessárias para publicar de fato,
    # então o módulo continua importável sem elas (testes/placeholder).
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:  # pragma: no cover - depende de dependência opcional
        raise RuntimeError(
            "Dependências do YouTube ausentes. Instale com "
            "`pip install google-api-python-client google-auth`."
        ) from exc

    creds = Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri=_TOKEN_URI,
    )
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "title": (idea.title or "Vídeo")[:100],
            "description": _description(idea)[:5000],
            "categoryId": os.environ.get("YOUTUBE_CATEGORY_ID", "22"),
        },
        "status": {
            "privacyStatus": os.environ.get("YOUTUBE_PRIVACY", "private"),
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(
        idea.video_path, chunksize=-1, resumable=True, mimetype="video/mp4"
    )
    response = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    ).execute()
    return f"https://youtu.be/{response['id']}"
