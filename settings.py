"""Seleção de modelos em runtime (persistida) para a UI de troca de modelos.

Os factories resolvem provider/modelo por variáveis de ambiente. Este módulo
guarda a escolha do usuário em JSON e a **aplica no ambiente do processo**
(`os.environ`), de modo que a troca pela UI passe a valer imediatamente e
sobreviva a reinícios (reaplicada no startup).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SETTINGS_PATH = os.environ.get("ANE_MODEL_SETTINGS", "output/model_settings.json")

# capacidade -> variável de ambiente do provider
PROVIDER_ENV = {
    "text": "ANE_TEXT_PROVIDER",
    "image": "ANE_IMAGE_PROVIDER",
    "voice": "ANE_VOICE_PROVIDER",
    "video": "ANE_VIDEO_PROVIDER",
    "publisher": "ANE_PUBLISHER",
}

# (capacidade, provider) -> variável de ambiente do modelo
MODEL_ENV = {
    ("text", "ollama"): "ANE_OLLAMA_MODEL",
    ("text", "gemini"): "GEMINI_TEXT_MODEL",
    ("image", "gemini"): "GEMINI_IMAGE_MODEL",
    ("video", "gemini"): "GEMINI_VIDEO_MODEL",
    ("voice", "elevenlabs"): "ELEVENLABS_VOICE_ID",
}


def load(path: str | None = None) -> dict:
    p = Path(path or SETTINGS_PATH)
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save(data: dict, path: str | None = None) -> None:
    p = Path(path or SETTINGS_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def apply_to_env(data: dict) -> None:
    """Aplica as seleções no os.environ (provider e, se houver, modelo)."""
    for cap, sel in data.items():
        provider = sel.get("provider")
        env_p = PROVIDER_ENV.get(cap)
        if env_p and provider:
            os.environ[env_p] = provider
        env_m = MODEL_ENV.get((cap, provider))
        if env_m and sel.get("model"):
            os.environ[env_m] = sel["model"]


def set_selection(capability: str, provider: str, model: str | None = None,
                  path: str | None = None) -> dict:
    data = load(path)
    data[capability] = {"provider": provider, "model": model}
    save(data, path)
    apply_to_env({capability: data[capability]})
    return data


def apply_saved(path: str | None = None) -> dict:
    """Reaplica a seleção salva (chamado no startup da API)."""
    data = load(path)
    apply_to_env(data)
    return data
