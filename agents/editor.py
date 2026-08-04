"""Agente revisor/editor de roteiros (loop de melhoria).

Em vez de apenas rejeitar um roteiro fraco (quality gate), este agente **reescreve**
o roteiro a partir da crítica e **re-avalia em loop** até atingir a nota mínima
(ou esgotar as iterações). Aumenta a taxa de aproveitamento das ideias.

`refine_loop` é puro (recebe `score_fn` e `rewrite_fn` injetados) e é coberto por
testes; o `ScriptEditorAgent` liga essas funções ao crítico + LLM local.
"""

from __future__ import annotations

import json

from .critic import ScriptCriticAgent
from .llm import OllamaError, get_text_client
from .script_writer import build_scenes
from .video_pipeline import Scene

__all__ = ["ScriptEditorAgent", "refine_loop", "OllamaError"]


def refine_loop(scenes, score_fn, rewrite_fn, min_score: float = 6.0, max_iterations: int = 2) -> dict:
    """Loop puro de melhoria.

    - `score_fn(scenes) -> {"score", "reason"}`
    - `rewrite_fn(scenes, feedback) -> list[Scene]` (ou vazio p/ manter)

    Devolve {scenes, score, iterations, passed, history}.
    """
    current = scenes
    result = score_fn(current)
    history = [{"iteration": 0, "score": result["score"], "reason": result.get("reason", "")}]

    iterations = 0
    while result["score"] < min_score and iterations < max_iterations:
        iterations += 1
        rewritten = rewrite_fn(current, result.get("reason", ""))
        if rewritten:
            current = rewritten
        result = score_fn(current)
        history.append(
            {"iteration": iterations, "score": result["score"], "reason": result.get("reason", "")}
        )

    return {
        "scenes": current,
        "score": result["score"],
        "iterations": iterations,
        "passed": result["score"] >= min_score,
        "history": history,
    }


class ScriptEditorAgent:
    """Revisa e reescreve roteiros usando o crítico + o LLM local."""

    def __init__(self, config_path: str = "config.json"):
        self.client = get_text_client(config_path, agent="editor")
        self.critic = ScriptCriticAgent(config_path)

    def _rewrite(self, title: str, scenes, feedback: str) -> list[Scene]:
        roteiro = "\n".join(
            f"{i+1}. narração: {s.narration} | visual: {s.visual_prompt}"
            for i, s in enumerate(scenes)
        )
        prompt = f"""
        Você é um editor de roteiros de vídeos curtos.
        Título: '{title}'.
        Roteiro atual:
        {roteiro}
        Crítica a resolver: {feedback}
        Reescreva o roteiro melhorando o gancho e o ritmo, mantendo o número de cenas.
        Retorne APENAS um JSON: uma LISTA de objetos com "narration" (pt),
        "visual_prompt" (en) e "duration_s" (número).
        """
        raw = self.client.generate(prompt)
        try:
            data = self.client.extract_json(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict):
            data = data.get("scenes") or data.get("cenas") or []
        return build_scenes(data) if isinstance(data, list) else []

    def refine(self, title: str, scenes, min_score: float = 6.0, max_iterations: int = 2) -> dict:
        """Executa o loop de melhoria para (title, scenes)."""
        return refine_loop(
            scenes,
            score_fn=lambda sc: self.critic.score_idea(title, sc),
            rewrite_fn=lambda sc, fb: self._rewrite(title, sc, fb),
            min_score=min_score,
            max_iterations=max_iterations,
        )
