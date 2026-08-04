"""Orquestração de alto nível: prompt → ideias → (revisão | postagem).

Dois modos:

- **manual** ("Tinder"): as ideias entram na fila como `pending`; o criador
  aprova/rejeita uma a uma no painel. As aprovadas ficam prontas para postar.
- **auto** ("prompta-e-posta"): as ideias já entram como `approved` e, se um
  `publisher` for fornecido, são postadas na hora.

Sobre publicação: nenhuma postagem automática em massa/evasão de detecção é
feita aqui (ver HANDOFF.md, seção de escopo). O `publisher` é um gancho que
você conecta às **APIs oficiais** das plataformas, dentro das regras de cada
rede. Sem um `publisher` conectado, o modo auto apenas deixa as ideias
aprovadas e prontas.
"""

from __future__ import annotations

from typing import Callable

from review.models import Idea, IdeaStatus
from review.queue import ReviewQueue

# Um publisher recebe uma Idea e a publica, devolvendo uma URL/identificador
# do post (ou levantando exceção em caso de falha).
Publisher = Callable[[Idea], str]


def generate_and_enqueue(
    prompt: str,
    queue: ReviewQueue,
    generator,
    count: int = 5,
    num_scenes: int = 5,
    mode: str = "manual",
    scorer=None,
    min_score: float = 0.0,
) -> list[Idea]:
    """Gera ideias para o prompt e as coloca na fila conforme o modo.

    `generator` é qualquer objeto com `.generate(prompt, count, num_scenes, mode)`
    (tipicamente `agents.idea_generator.IdeaGenerator`), injetado para permitir
    testes sem Ollama.

    `scorer` (opcional) é um callable `scorer(idea) -> {"score", "reason"}`
    (agente crítico). Ideias com nota abaixo de `min_score` entram como
    **rejeitadas** (quality gate), independentemente do modo.
    """
    if mode not in ("manual", "auto"):
        raise ValueError(f"Modo inválido: '{mode}'. Use 'manual' ou 'auto'.")

    ideas = generator.generate(prompt, count=count, num_scenes=num_scenes, mode=mode)

    for idea in ideas:
        idea.mode = mode
        reprovada = False
        if scorer is not None:
            try:
                resultado = scorer(idea)
                idea.score = resultado.get("score")
                if resultado.get("reason"):
                    idea.note = resultado["reason"]
                reprovada = (idea.score or 0) < min_score
            except Exception as exc:  # noqa: BLE001 - falha do crítico não derruba o lote
                idea.note = f"Crítico falhou: {exc}"

        if reprovada:
            idea.status = IdeaStatus.REJECTED
        elif mode == "auto":
            # Sem revisão manual: já entra aprovada (pronta para postar).
            idea.status = IdeaStatus.APPROVED
        else:
            idea.status = IdeaStatus.PENDING

    queue.add_many(ideas)
    return ideas


def post_approved(
    queue: ReviewQueue,
    publisher: Publisher | None = None,
) -> list[Idea]:
    """Publica as ideias aprovadas usando o `publisher` e as marca como postadas.

    Sem `publisher`, não posta nada e devolve lista vazia (as ideias seguem
    aprovadas e prontas). Falhas de publicação de uma ideia não interrompem as
    demais — a mensagem fica registrada em `idea.note`.
    """
    if publisher is None:
        return []

    posted: list[Idea] = []
    for idea in queue.approved():
        try:
            result = publisher(idea)
            idea.note = f"Postado: {result}" if result else "Postado."
            queue.mark_posted(idea.id)
            posted.append(idea)
        except Exception as exc:  # noqa: BLE001 - falha de rede/API não deve abortar o lote
            idea.note = f"Falha ao postar: {exc}"
            queue._save()  # persiste a nota mesmo sem mudar o status
    return posted


def run_prompt(
    prompt: str,
    queue: ReviewQueue,
    generator,
    mode: str = "manual",
    count: int = 5,
    num_scenes: int = 5,
    publisher: Publisher | None = None,
) -> dict:
    """Fluxo completo de um prompt. Devolve um resumo do que aconteceu."""
    ideas = generate_and_enqueue(
        prompt, queue, generator, count=count, num_scenes=num_scenes, mode=mode
    )
    posted: list[Idea] = []
    if mode == "auto":
        posted = post_approved(queue, publisher)
    return {
        "mode": mode,
        "generated": len(ideas),
        "posted": len(posted),
        "idea_ids": [i.id for i in ideas],
    }
