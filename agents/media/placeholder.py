"""Geradores placeholder de mídia usando apenas FFmpeg (sem serviço externo).

Servem para o pipeline de vídeo rodar ponta-a-ponta **out of the box**: geram
uma imagem de fundo colorida (derivada do prompt) e um áudio silencioso com a
duração estimada da narração. Troque por provedores reais (Stable Diffusion,
ElevenLabs, etc.) via config — ver `agents/media/factory.py`.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

# Duração estimada da narração (placeholder), em segundos.
_MIN_DURATION = 2.0
_MAX_DURATION = 10.0
_SECONDS_PER_WORD = 0.45
_DEFAULT_DURATION = 4.0


def _color_from_text(text: str) -> str:
    """Cor hex determinística a partir do texto (para o fundo do slide)."""
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return digest[:6]


def estimate_duration(text: str) -> float:
    """Estima a duração da fala pelo número de palavras."""
    words = len(text.split())
    if not words:
        return _DEFAULT_DURATION
    return max(_MIN_DURATION, min(_MAX_DURATION, words * _SECONDS_PER_WORD))


def placeholder_image(visual_prompt: str, dest: Path) -> Path:
    """Gera um PNG 1080×1920 de cor sólida derivada do prompt."""
    dest = Path(dest)
    color = _color_from_text(visual_prompt or "scene")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x{color}:s=1080x1920",
        "-frames:v", "1",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


def placeholder_voice(narration: str, dest: Path) -> Path:
    """Gera um MP3 silencioso com a duração estimada da narração."""
    dest = Path(dest)
    duration = estimate_duration(narration)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", f"{duration:.2f}",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest
