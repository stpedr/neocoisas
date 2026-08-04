"""Agente crítico (quality gate).

Avalia o potencial de uma ideia (0–10) com o LLM local e devolve nota + motivo.
Usado como portão de qualidade: ideias abaixo de um limiar são auto-rejeitadas
antes de chegarem à revisão manual, reduzindo o trabalho do criador.

`parse_critique` é pura (sem Ollama) e coberta por testes.
"""

from __future__ import annotations

import json

from .ollama_client import OllamaClient, OllamaError

__all__ = ["ScriptCriticAgent", "parse_critique", "OllamaError"]


def parse_critique(data: dict) -> dict:
    """Normaliza a resposta do crítico em {'score': float(0-10), 'reason': str}."""
    raw_score = (
        data.get("score")
        if data.get("score") is not None
        else data.get("nota", data.get("rating"))
    )
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(10.0, score))
    reason = (
        data.get("reason")
        or data.get("motivo")
        or data.get("justificativa")
        or ""
    )
    return {"score": round(score, 1), "reason": str(reason).strip()}


class ScriptCriticAgent:
    """Dá uma nota de potencial viral a uma ideia usando o LLM local."""

    def __init__(self, config_path: str = "config.json"):
        self.client = OllamaClient(config_path)
        self.config = self.client.config

    @staticmethod
    def _prompt(title: str, narrations: list[str]) -> str:
        roteiro = "\n".join(f"- {n}" for n in narrations if n)
        return f"""
        Você é um analista de conteúdo viral para vídeos curtos.
        Avalie a ideia abaixo quanto ao potencial de engajamento/retenção.
        Título: '{title}'
        Roteiro:
        {roteiro}
        Retorne APENAS um JSON: {{"score": número de 0 a 10, "reason": "1 frase"}}.
        Seja criterioso: notas altas só para ganchos fortes e ritmo bom.
        """

    def score_idea(self, title: str, scenes) -> dict:
        """Avalia (title, scenes) e devolve {'score', 'reason'}."""
        narrations = [getattr(s, "narration", "") for s in scenes]
        raw = self.client.generate(self._prompt(title, narrations))
        try:
            data = self.client.extract_json(raw)
        except json.JSONDecodeError:
            return {"score": 0.0, "reason": "Crítico não retornou JSON válido."}
        if not isinstance(data, dict):
            return {"score": 0.0, "reason": "Resposta do crítico em formato inesperado."}
        return parse_critique(data)
