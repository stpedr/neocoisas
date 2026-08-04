"""Agente analista (feedback loop).

Recebe o desempenho de vídeos já postados (métricas) e devolve insights +
recomendações de estratégia — para realimentar o nicho, favorecendo o que
performa. `parse_analysis` é pura; a análise usa o LLM local.

A coleta automática de métricas depende das APIs das plataformas (futuro); por
ora as métricas entram manualmente (endpoint /api/ideas/{id}/metrics).
"""

from __future__ import annotations

import json

from .llm import OllamaError, get_text_client

__all__ = ["AnalystAgent", "parse_analysis", "OllamaError"]


def parse_analysis(data: dict) -> dict:
    """Normaliza em {'insights': str, 'recommendations': [str, ...]}."""
    if not isinstance(data, dict):
        return {"insights": "", "recommendations": []}
    insights = str(data.get("insights") or data.get("resumo") or "").strip()
    recs = data.get("recommendations") or data.get("recomendacoes") or []
    if isinstance(recs, str):
        recs = [recs]
    recs = [str(r).strip() for r in recs if str(r).strip()]
    return {"insights": insights, "recommendations": recs}


class AnalystAgent:
    def __init__(self, config_path: str = "config.json"):
        self.client = get_text_client(config_path)

    def analyze(self, performances: list[dict]) -> dict:
        """`performances`: lista de {title, metrics}. Devolve insights + recs."""
        if not performances:
            return {"insights": "Sem dados de desempenho ainda.", "recommendations": []}
        linhas = [
            f"- {p.get('title', '?')}: {json.dumps(p.get('metrics', {}), ensure_ascii=False)}"
            for p in performances
        ]
        prompt = f"""
        Você é um analista de crescimento de canais de vídeo curto.
        Desempenho dos últimos vídeos:
        {chr(10).join(linhas)}
        Analise padrões (o que performou melhor e por quê) e recomende ajustes
        de estratégia de conteúdo.
        Retorne APENAS um JSON: {{"insights": "texto", "recommendations": ["...", "..."]}}.
        """
        raw = self.client.generate(prompt)
        try:
            data = self.client.extract_json(raw)
        except json.JSONDecodeError:
            return {"insights": raw[:500], "recommendations": []}
        return parse_analysis(data)
