"""Gerador de ideias a partir de um prompt livre.

Dado um prompt do criador (ex: "curiosidades sobre o espaço para crianças"),
faz um brainstorm de N conceitos de vídeo curto e, para cada um, escreve o
roteiro cena-a-cena (reutilizando o `ScriptWriterAgent`). O resultado é uma
lista de `Idea` pronta para entrar na fila de revisão (modo Tinder) ou para o
fluxo automático (prompta-e-posta).

A função `build_idea_concepts` (normalização dos conceitos vindos do modelo) é
pura e coberta por testes; a geração em si depende do Ollama local.
"""

from __future__ import annotations

import json

from review.models import Idea

from .llm import OllamaError, get_text_client
from .script_writer import ScriptWriterAgent

__all__ = ["IdeaGenerator", "build_idea_concepts", "OllamaError"]


def build_idea_concepts(raw_concepts: list) -> list[dict]:
    """Normaliza os conceitos vindos do modelo em dicts {title, angle}.

    Tolera nomes de campo alternativos e itens que sejam apenas strings.
    Conceitos sem título aproveitável são descartados.
    """
    concepts: list[dict] = []
    for item in raw_concepts:
        if isinstance(item, str):
            title = item.strip()
            angle = ""
        elif isinstance(item, dict):
            title = (
                item.get("title")
                or item.get("titulo")
                or item.get("idea")
                or item.get("ideia")
                or item.get("hook")
                or item.get("gancho")
                or item.get("topic")
                or ""
            ).strip()
            angle = (
                item.get("angle")
                or item.get("angulo")
                or item.get("description")
                or item.get("descricao")
                or item.get("resumo")
                or ""
            ).strip()
        else:
            continue
        if not title:
            continue
        concepts.append({"title": title, "angle": angle})
    return concepts


class IdeaGenerator:
    """Transforma um prompt em uma lista de `Idea` com roteiro."""

    def __init__(self, config_path: str = "config.json"):
        self.client = get_text_client(config_path, agent="idea")
        self.config = self.client.config
        self.script_writer = ScriptWriterAgent(config_path)

    @staticmethod
    def _brainstorm_prompt(prompt: str, count: int) -> str:
        return f"""
        Você é um diretor de conteúdo de vídeos curtos virais.
        Ideia/tema do criador: '{prompt}'.
        Proponha exatamente {count} conceitos DIFERENTES de vídeo curto.
        Retorne APENAS um JSON válido: uma LISTA de objetos, cada um com:
          - "title": um gancho/título curto e chamativo (em português);
          - "angle": uma frase explicando o ângulo/abordagem do vídeo.
        Não inclua texto fora do JSON.
        """

    def brainstorm(self, prompt: str, count: int = 5) -> list[dict]:
        """Gera `count` conceitos (title/angle) a partir do prompt."""
        raw = self.client.generate(self._brainstorm_prompt(prompt, count))
        try:
            data = self.client.extract_json(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "O modelo não retornou um JSON de conceitos válido.\n"
                f"Saída bruta:\n{raw}"
            ) from exc
        if isinstance(data, dict):
            data = data.get("ideas") or data.get("concepts") or data.get("conceitos") or []
        if not isinstance(data, list):
            raise ValueError(
                f"Esperava uma lista de conceitos, recebi {type(data).__name__}."
            )
        concepts = build_idea_concepts(data)
        if not concepts:
            raise ValueError("Nenhum conceito aproveitável foi gerado.")
        return concepts

    def generate(
        self,
        prompt: str,
        count: int = 5,
        num_scenes: int = 5,
        mode: str = "manual",
    ) -> list[Idea]:
        """Brainstorm + roteiro por conceito → lista de `Idea`.

        Conceitos cujo roteiro falhar são registrados com `note` e roteiro
        vazio, em vez de derrubar a geração inteira.
        """
        concepts = self.brainstorm(prompt, count)
        ideas: list[Idea] = []
        for concept in concepts:
            topic = concept["title"]
            if concept["angle"]:
                topic = f"{concept['title']} — {concept['angle']}"
            try:
                scenes = self.script_writer.write_script(topic, num_scenes)
                note = ""
            except (OllamaError, ValueError) as exc:
                scenes = []
                note = f"Falha ao gerar roteiro: {exc}"
            ideas.append(
                Idea(
                    prompt=prompt,
                    title=concept["title"],
                    scenes=scenes,
                    mode=mode,
                    note=note,
                )
            )
        return ideas
