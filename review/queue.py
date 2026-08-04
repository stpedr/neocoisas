"""Fila de revisão de ideias, persistida em JSON.

Guarda as ideias geradas e seus estados. É a fonte de verdade tanto do modo
manual ("Tinder": aprovar/rejeitar) quanto do automático (prompta-e-posta).

Persistência simples em um arquivo JSON (por padrão em `output/`, que está no
`.gitignore`). Cada mutação salva no disco, para o painel e a CLI enxergarem o
mesmo estado.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Idea, IdeaStatus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewQueue:
    """Coleção persistente de `Idea` com operações de aprovação."""

    def __init__(self, path: str | Path = "output/review_queue.json"):
        self.path = Path(path)
        self._ideas: list[Idea] = []
        self._load()

    # ------------------------------------------------------------------ IO ---
    def _load(self) -> None:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._ideas = [Idea.from_dict(d) for d in data.get("ideas", [])]
        else:
            self._ideas = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ideas": [idea.to_dict() for idea in self._ideas]}
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------- consultas -
    def all(self) -> list[Idea]:
        return list(self._ideas)

    def get(self, idea_id: str) -> Idea:
        for idea in self._ideas:
            if idea.id == idea_id:
                return idea
        raise KeyError(f"Ideia '{idea_id}' não encontrada na fila.")

    def by_status(self, status: str) -> list[Idea]:
        return [i for i in self._ideas if i.status == status]

    def pending(self) -> list[Idea]:
        """Ideias aguardando decisão, mais antigas primeiro (ordem da fila)."""
        return sorted(self.by_status(IdeaStatus.PENDING), key=lambda i: i.created_at)

    def approved(self) -> list[Idea]:
        """Ideias aprovadas e ainda não postadas (prontas para publicar)."""
        return self.by_status(IdeaStatus.APPROVED)

    def counts(self) -> dict:
        """Contagem por estado — útil para o cabeçalho do painel."""
        return {status: len(self.by_status(status)) for status in sorted(IdeaStatus.ALL)}

    # --------------------------------------------------------------- mutações -
    def add(self, idea: Idea) -> Idea:
        self._ideas.append(idea)
        self._save()
        return idea

    def add_many(self, ideas: list[Idea]) -> list[Idea]:
        self._ideas.extend(ideas)
        self._save()
        return ideas

    def _set_status(self, idea_id: str, status: str) -> Idea:
        idea = self.get(idea_id)
        idea.status = status
        idea.decided_at = _now_iso()
        self._save()
        return idea

    def approve(self, idea_id: str) -> Idea:
        return self._set_status(idea_id, IdeaStatus.APPROVED)

    def reject(self, idea_id: str) -> Idea:
        return self._set_status(idea_id, IdeaStatus.REJECTED)

    def mark_posted(self, idea_id: str) -> Idea:
        idea = self.get(idea_id)
        if idea.status not in (IdeaStatus.APPROVED, IdeaStatus.PENDING):
            raise ValueError(
                f"Só é possível postar ideias aprovadas/pendentes; "
                f"'{idea_id}' está '{idea.status}'."
            )
        return self._set_status(idea_id, IdeaStatus.POSTED)

    def attach_video(self, idea_id: str, video_path: str) -> Idea:
        idea = self.get(idea_id)
        idea.video_path = video_path
        self._save()
        return idea

    def attach_thumbnail(self, idea_id: str, thumbnail_path: str) -> Idea:
        idea = self.get(idea_id)
        idea.thumbnail_path = thumbnail_path
        self._save()
        return idea

    def add_variant(self, idea_id: str, lang: str, video_path: str) -> Idea:
        idea = self.get(idea_id)
        idea.video_variants[lang] = video_path
        self._save()
        return idea

    def set_metrics(self, idea_id: str, metrics: dict) -> Idea:
        idea = self.get(idea_id)
        idea.metrics.update(metrics)
        self._save()
        return idea

    def clear_decided(self) -> int:
        """Remove ideias já resolvidas (rejeitadas/postadas). Devolve quantas saíram."""
        before = len(self._ideas)
        self._ideas = [
            i for i in self._ideas
            if i.status in (IdeaStatus.PENDING, IdeaStatus.APPROVED)
        ]
        self._save()
        return before - len(self._ideas)
