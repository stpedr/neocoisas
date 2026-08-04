"""Provedores reais de mídia (opt-in via chaves de API).

Cada função tem a mesma assinatura dos hooks do `VideoPipeline`
(`fn(texto, dest: Path) -> Path`) e lê as credenciais de variáveis de ambiente.
Se a chave não estiver configurada, levantam `RuntimeError` com instruções —
nada é chamado sem a sua chave.

Estes são pontos de extensão pré-configurados: revise o endpoint/modelo conforme
o seu provedor antes de usar em produção.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests

_TIMEOUT = 120


def stability_image(visual_prompt: str, dest: Path) -> Path:
    """Gera imagem via Stability AI (Stable Image). Requer STABILITY_API_KEY."""
    key = os.environ.get("STABILITY_API_KEY")
    if not key:
        raise RuntimeError(
            "Configure a variável STABILITY_API_KEY para usar o provedor de "
            "imagem 'stability'."
        )
    dest = Path(dest)
    resp = requests.post(
        "https://api.stability.ai/v2beta/stable-image/generate/core",
        headers={"authorization": f"Bearer {key}", "accept": "image/*"},
        files={"none": ""},
        data={"prompt": visual_prompt, "aspect_ratio": "9:16", "output_format": "png"},
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Stability AI falhou ({resp.status_code}): {resp.text[:200]}")
    dest.write_bytes(resp.content)
    return dest


def gemini_image(visual_prompt: str, dest: Path) -> Path:
    """Gera imagem via Gemini API (Imagen). Requer GEMINI_API_KEY."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "Configure a variável GEMINI_API_KEY para usar o provedor de "
            "imagem 'gemini'."
        )
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - dependência opcional
        raise RuntimeError(
            "Dependência ausente. Instale com `pip install google-genai`."
        ) from exc

    client = genai.Client(api_key=key)
    model = os.environ.get("GEMINI_IMAGE_MODEL", "imagen-3.0-generate-002")
    resp = client.models.generate_images(
        model=model,
        prompt=visual_prompt,
        config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="9:16"),
    )
    if not getattr(resp, "generated_images", None):
        raise RuntimeError("Gemini não retornou imagem.")
    image = resp.generated_images[0].image
    dest = Path(dest)
    data = getattr(image, "image_bytes", None)
    if data:
        dest.write_bytes(data)
    else:  # o SDK também expõe .save()
        image.save(str(dest))
    return dest


def gemini_video(visual_prompt: str, dest: Path) -> Path:
    """Gera um clipe de vídeo via Gemini API (Veo). Requer GEMINI_API_KEY.

    A geração é uma operação de longa duração; fazemos polling até concluir.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "Configure a variável GEMINI_API_KEY para usar o provedor de "
            "vídeo 'gemini'."
        )
    try:
        import time

        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - dependência opcional
        raise RuntimeError(
            "Dependência ausente. Instale com `pip install google-genai`."
        ) from exc

    client = genai.Client(api_key=key)
    model = os.environ.get("GEMINI_VIDEO_MODEL", "veo-2.0-generate-001")
    operation = client.models.generate_videos(
        model=model,
        prompt=visual_prompt,
        config=types.GenerateVideosConfig(aspect_ratio="9:16", number_of_videos=1),
    )
    # Polling da operação (Veo leva de dezenas de segundos a minutos).
    while not operation.done:
        time.sleep(10)
        operation = client.operations.get(operation)

    videos = getattr(operation.response, "generated_videos", None)
    if not videos:
        raise RuntimeError("Veo não retornou vídeo.")
    generated = videos[0]
    dest = Path(dest)
    client.files.download(file=generated.video)
    generated.video.save(str(dest))
    return dest


def elevenlabs_voice(narration: str, dest: Path) -> Path:
    """Gera narração via ElevenLabs. Requer ELEVENLABS_API_KEY."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError(
            "Configure a variável ELEVENLABS_API_KEY para usar o provedor de "
            "voz 'elevenlabs'."
        )
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    dest = Path(dest)
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": key, "accept": "audio/mpeg"},
        json={"text": narration, "model_id": "eleven_multilingual_v2"},
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs falhou ({resp.status_code}): {resp.text[:200]}")
    dest.write_bytes(resp.content)
    return dest
