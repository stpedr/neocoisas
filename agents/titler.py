"""Agente de títulos (A/B) — gera variações de título chamativas para um tópico.

`parse_titles` é pura e testável; a geração usa o LLM local.
"""

from __future__ import annotations

import json

from .llm import OllamaError, get_text_client

__all__ = ["TitlerAgent", "parse_titles", "OllamaError"]


def parse_titles(data) -> list[str]:
    """Normaliza a resposta em uma lista de títulos (strings)."""
    if isinstance(data, dict):
        data = data.get("titles") or data.get("titulos") or []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            v = item.get("title") or item.get("titulo") or ""
            if v.strip():
                out.append(v.strip())
    return out


class TitlerAgent:
    """Sugere títulos alternativos (A/B) para um tópico usando o LLM local."""

    def __init__(self, config_path: str = "config.json"):
        self.client = get_text_client(config_path, agent="titler")

    def suggest_titles(self, topic: str, n: int = 3, retries: int = 2) -> list[str]:
        prompt = f"""
        Você escreve títulos virais para vídeos curtos.
        Tópico: '{topic}'.
        Gere {n} títulos DIFERENTES, curtos e com forte gancho (em português).
        Retorne APENAS um JSON: uma lista de strings. Sem texto fora do JSON.
        """
        # O modelo local é não-determinístico; tenta de novo se vier vazio.
        for _ in range(max(1, retries)):
            raw = self.client.generate(prompt)
            try:
                titulos = parse_titles(self.client.extract_json(raw))
            except json.JSONDecodeError:
                titulos = []
            if titulos:
                return titulos[:n]
        return []
