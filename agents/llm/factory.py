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


def agent_model_override(agent: str | None, config: dict | None = None) -> str | None:
    """Modelo específico de um agente (env > config['agent_models']), se houver."""
    if not agent:
        return None
    env = os.environ.get(f"ANE_AGENT_MODEL_{agent.upper()}")
    if env:
        return env
    return (config or {}).get("agent_models", {}).get(agent)


def get_text_client(config_path: str = "config.json", agent: str | None = None):
    """Devolve o cliente de texto do provider configurado.

    Se `agent` for informado e houver um override de modelo para ele
    (`ANE_AGENT_MODEL_<AGENTE>` ou `config['agent_models'][agent]`), o modelo do
    cliente é sobrescrito — permitindo modelo por agente sobre o padrão global.
    """
    name = resolve_provider(config_path)
    if name not in _PROVIDERS:
        opcoes = ", ".join(sorted(_PROVIDERS))
        raise ValueError(f"Provedor de texto inválido: '{name}'. Opções: {opcoes}.")
    client = _PROVIDERS[name](config_path)
    override = agent_model_override(agent, _read_config(config_path))
    if override:
        client.model = override
    return client
