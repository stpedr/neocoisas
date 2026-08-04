"""Provedores de LLM de texto (factory selecionável por config/env).

Mesmo padrão de `agents/media`: um contrato de cliente de texto
(`generate(prompt)->str`, `extract_json(raw)`, `.model`, `.config`) e uma factory
que escolhe o provider. Padrão: `ollama` (OllamaClient).
"""

from ..ollama_client import OllamaError
from .factory import get_text_client, resolve_provider

# Erro comum de LLM (compat. com quem importa OllamaError dos agentes).
LLMError = OllamaError

__all__ = ["get_text_client", "resolve_provider", "OllamaError", "LLMError"]
