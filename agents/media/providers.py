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
