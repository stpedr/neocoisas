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
import subprocess
from pathlib import Path

import requests

_TIMEOUT = 120


def piper_voice(narration: str, dest: Path) -> Path:
    """Narração via Piper (TTS local, offline). Voz PT-BR, sem chave/API.

    Requer o binário `piper` no PATH e um modelo de voz (.onnx) — ambos incluídos
    na imagem Docker. O caminho do modelo vem de `PIPER_MODEL`.
    """
    model = os.environ.get("PIPER_MODEL", "/app/voices/pt_BR-faber-medium.onnx")
    if not Path(model).exists():
        raise RuntimeError(
            f"Modelo Piper não encontrado em '{model}'. Defina PIPER_MODEL ou use "
            "a imagem Docker (que já baixa a voz PT-BR)."
        )
    dest = Path(dest)
    wav = dest.with_suffix(".wav")
    try:
        proc = subprocess.run(
            ["piper", "--model", model, "--output_file", str(wav)],
            input=(narration or " "),
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Binário 'piper' não encontrado. Instale com `pip install piper-tts`."
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError(f"Piper falhou: {proc.stderr[:200]}")
    # Converte o WAV do Piper para o mp3 esperado pelo pipeline.
    subprocess.run(["ffmpeg", "-y", "-i", str(wav), str(dest)], check=True, capture_output=True)
    wav.unlink(missing_ok=True)
    return dest


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


def a1111_image(visual_prompt: str, dest: Path) -> Path:
    """Imagem via Stable Diffusion local (API do AUTOMATIC1111). Grátis/offline.

    Requer o AUTOMATIC1111 rodando com `--api` na máquina (como o Ollama). A URL
    vem de `A1111_URL` (padrão `http://host.docker.internal:7860`, que alcança o
    host a partir do container).
    """
    import base64

    base = os.environ.get("A1111_URL", "http://host.docker.internal:7860").rstrip("/")
    payload = {
        "prompt": visual_prompt,
        "negative_prompt": os.environ.get("A1111_NEGATIVE", "text, watermark, logo, blurry"),
        "width": int(os.environ.get("A1111_WIDTH", "768")),
        "height": int(os.environ.get("A1111_HEIGHT", "1344")),  # ~9:16
        "steps": int(os.environ.get("A1111_STEPS", "22")),
        "cfg_scale": float(os.environ.get("A1111_CFG", "7")),
        "sampler_name": os.environ.get("A1111_SAMPLER", "DPM++ 2M Karras"),
    }
    try:
        r = requests.post(f"{base}/sdapi/v1/txt2img", json=payload, timeout=600)
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"Não foi possível falar com o Stable Diffusion em {base}. "
            "Rode o AUTOMATIC1111 com --api (ou ajuste A1111_URL)."
        ) from exc
    if r.status_code != 200:
        raise RuntimeError(f"AUTOMATIC1111 falhou ({r.status_code}): {r.text[:200]}")
    images = r.json().get("images") or []
    if not images:
        raise RuntimeError("AUTOMATIC1111 não retornou imagem.")
    dest = Path(dest)
    dest.write_bytes(base64.b64decode(images[0].split(",", 1)[-1]))
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
    # API atual: generate_content com um modelo de imagem (o generate_images/Imagen
    # foi descontinuado para novos usuários).
    model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    resp = client.models.generate_content(
        model=model,
        contents=f"{visual_prompt}. Vertical 9:16, sem texto.",
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    dest = Path(dest)
    for cand in (resp.candidates or []):
        for part in (getattr(cand.content, "parts", None) or []):
            data = getattr(getattr(part, "inline_data", None), "data", None)
            if data:
                dest.write_bytes(data)
                return dest
    raise RuntimeError("Gemini não retornou imagem (modalidade IMAGE).")


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
    model = os.environ.get("GEMINI_VIDEO_MODEL", "veo-3.1-fast-generate-preview")
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
