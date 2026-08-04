"""Modelo do quadro Kanban: colunas e cartões.

O quadro reflete o planejamento em sprints para **finalizar e publicar** o
projeto. Cada `Card` é uma atividade que anda entre as colunas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

# Colunas do fluxo, na ordem de exibição (id, rótulo).
COLUMNS: list[dict] = [
    {"id": "backlog", "label": "Backlog"},
    {"id": "todo", "label": "A fazer"},
    {"id": "in_progress", "label": "Em andamento"},
    {"id": "review", "label": "Revisão"},
    {"id": "done", "label": "Concluído"},
]

COLUMN_IDS = frozenset(c["id"] for c in COLUMNS)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Card:
    """Uma atividade do quadro."""

    title: str
    description: str = ""
    column: str = "backlog"
    sprint: str = ""
    labels: list[str] = field(default_factory=list)
    order: float = 0.0
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "column": self.column,
            "sprint": self.sprint,
            "labels": list(self.labels),
            "order": self.order,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Card":
        return cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            column=data.get("column", "backlog"),
            sprint=data.get("sprint", ""),
            labels=list(data.get("labels", [])),
            order=float(data.get("order", 0.0)),
            id=data.get("id", uuid4().hex[:12]),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )
