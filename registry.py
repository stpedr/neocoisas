"""Registry unificado de modelos/provedores.

Ponto único que descreve cada **capacidade** (texto, imagem, voz, vídeo,
publicação): quais providers existem (lidos dos próprios factories, então fica
sempre em sincronia), quais modelos conhecidos, o que cada um exige (variáveis de
ambiente) e qual está **ativo** agora. Alimenta o endpoint `GET /api/models` e a
futura UI de troca de modelos.
"""

from __future__ import annotations

import os

import requests

from agents.llm.factory import _PROVIDERS as _TEXT_PROVIDERS
from agents.media.factory import (
    _IMAGE_PROVIDERS,
    _VIDEO_PROVIDERS,
    _VOICE_PROVIDERS,
)
from publishers.factory import _PUBLISHERS

# Providers por capacidade — derivados dos factories (fonte da verdade real).
CAP_PROVIDERS: dict[str, list[str]] = {
    "text": sorted(_TEXT_PROVIDERS),
    "image": sorted(_IMAGE_PROVIDERS),
    "voice": sorted(_VOICE_PROVIDERS),
    "video": ["none"] + sorted(_VIDEO_PROVIDERS),
    "publisher": ["none"] + sorted(_PUBLISHERS),
}

# Variáveis de ambiente exigidas por provider (para o provider "funcionar").
REQUIRES: dict[str, list[str]] = {
    "gemini": ["GEMINI_API_KEY"],
    "stability": ["STABILITY_API_KEY"],
    "elevenlabs": ["ELEVENLABS_API_KEY"],
    "youtube": ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"],
    "instagram": ["IG_USER_ID", "IG_ACCESS_TOKEN"],
    "tiktok": ["TIKTOK_ACCESS_TOKEN"],
}

# Modelos conhecidos por (capacidade, provider) — sugestões para a UI.
KNOWN_MODELS: dict[str, dict[str, list[str]]] = {
    "text": {"ollama": ["llama3"], "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]},
    "image": {
        "gemini": ["gemini-2.5-flash-image"],
        "stability": ["core"],
    },
    "video": {"gemini": ["veo-3.1-fast-generate-preview", "veo-3.1-generate-preview"]},
}


# Agentes que usam LLM de texto (podem ter modelo próprio).
AGENTS = ["idea", "script", "carousel", "critic", "editor", "titler", "translator",
          "analyst", "niche"]


def _env_or_cfg(env: str, cfg: dict, key: str, default: str) -> str:
    return os.environ.get(env) or cfg.get(key, default)


def agent_models(config: dict | None = None) -> dict:
    """Modelo efetivo por agente: override (env/config) ou o modelo de texto global."""
    from agents.llm.factory import agent_model_override

    config = config or {}
    global_model = current("text", config)["model"]
    result = {}
    for agent in AGENTS:
        result[agent] = {
            "model": agent_model_override(agent, config) or global_model,
            "override": bool(agent_model_override(agent, config)),
        }
    return result


def current(cap: str, config: dict) -> dict:
    """Provider + modelo ativos para uma capacidade (env tem prioridade)."""
    c = config or {}
    if cap == "text":
        provider = os.environ.get("ANE_TEXT_PROVIDER") or c.get("text_provider", "ollama")
        if provider == "gemini":
            model = _env_or_cfg("GEMINI_TEXT_MODEL", c, "gemini_text_model", "gemini-2.5-flash")
        else:
            model = _env_or_cfg("ANE_OLLAMA_MODEL", c, "ollama_model", "llama3")
    elif cap == "image":
        provider = os.environ.get("ANE_IMAGE_PROVIDER") or c.get("image_provider", "placeholder")
        model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image") if provider == "gemini" else None
    elif cap == "voice":
        provider = os.environ.get("ANE_VOICE_PROVIDER") or c.get("voice_provider", "placeholder")
        model = os.environ.get("ELEVENLABS_VOICE_ID") if provider == "elevenlabs" else None
    elif cap == "video":
        provider = os.environ.get("ANE_VIDEO_PROVIDER") or c.get("video_provider", "none")
        model = os.environ.get("GEMINI_VIDEO_MODEL", "veo-3.1-fast-generate-preview") if provider == "gemini" else None
    elif cap == "publisher":
        provider = os.environ.get("ANE_PUBLISHER") or c.get("publisher", "none")
        model = None
    else:
        raise ValueError(f"Capacidade desconhecida: '{cap}'.")
    return {"provider": provider, "model": model}


def _configured(provider: str) -> bool:
    """True se todas as variáveis exigidas pelo provider estão setadas."""
    return all(os.environ.get(v) for v in REQUIRES.get(provider, []))


def validate(cap: str, provider: str) -> bool:
    """Valida se `provider` é válido para a capacidade `cap`."""
    if cap not in CAP_PROVIDERS:
        raise ValueError(f"Capacidade desconhecida: '{cap}'.")
    return provider in CAP_PROVIDERS[cap]


def _ollama_tags(config: dict) -> list[str]:
    """Modelos instalados no Ollama (via /api/tags). Resiliente: [] se falhar."""
    base = os.environ.get("ANE_OLLAMA_BASE_URL") or config.get(
        "ollama_base_url", "http://localhost:11434"
    )
    try:
        r = requests.get(base.rstrip("/") + "/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:  # noqa: BLE001 - Ollama pode estar fora do ar
        return []


def available_models(config: dict | None = None) -> dict:
    """Modelos disponíveis por capacidade/provider para popular a UI.

    Para `ollama` consulta ao vivo (/api/tags), com fallback nos modelos
    conhecidos; para os demais usa a lista estática conhecida.
    """
    config = config or {}
    ollama = _ollama_tags(config) or KNOWN_MODELS["text"]["ollama"]
    return {
        "text": {"ollama": ollama, "gemini": KNOWN_MODELS["text"]["gemini"]},
        "image": KNOWN_MODELS.get("image", {}),
        "video": KNOWN_MODELS.get("video", {}),
    }


def describe(config: dict | None = None) -> dict:
    """Descritor completo para o /api/models e a UI."""
    config = config or {}
    caps = {}
    for cap, providers in CAP_PROVIDERS.items():
        caps[cap] = {
            "providers": providers,
            "current": current(cap, config),
            "requires": {p: REQUIRES.get(p, []) for p in providers},
            "configured": {p: _configured(p) for p in providers},
            "models": KNOWN_MODELS.get(cap, {}),
        }
    return {"capabilities": caps, "agents": agent_models(config)}
