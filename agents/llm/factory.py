"""Seleção do provedor de LLM de texto.

Provider vem de `ANE_TEXT_PROVIDER` (env) ou `text_provider` (config.json),
padrão `ollama`. Novos provedores (gemini/openai/anthropic) entram no registry.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..ollama_client import OllamaClient
from .gemini_text import GeminiTextClient

_PROVIDERS = {
    "ollama": OllamaClient,
    "gemini": GeminiTextClient,
}


def _read_config(config_path: str) -> dict:
    path = Path(config_path)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def resolve_provider(config_path: str = "config.json") -> str:
    """Nome do provider de texto ativo (env tem prioridade sobre a config)."""
    return os.environ.get("ANE_TEXT_PROVIDER") or _read_config(config_path).get(
        "text_provider", "ollama"
    )


def get_text_client(config_path: str = "config.json"):
    """Devolve o cliente de texto do provider configurado."""
    name = resolve_provider(config_path)
    if name not in _PROVIDERS:
        opcoes = ", ".join(sorted(_PROVIDERS))
        raise ValueError(f"Provedor de texto inválido: '{name}'. Opções: {opcoes}.")
    return _PROVIDERS[name](config_path)
