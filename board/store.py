"""Persistência do quadro Kanban em JSON.

Guarda os cartões em `output/board.json`. Na primeira leitura de um board vazio,
semeia automaticamente com o planejamento de sprints (`board.seed`), para o
quadro nunca aparecer em branco.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import COLUMN_IDS, COLUMNS, Card
from .seed import SEED_CARDS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BoardStore:
    """Coleção persistente de `Card` com operações de quadro."""

    def __init__(self, path: str | Path = "output/board.json", auto_seed: bool = True):
        self.path = Path(path)
        self._cards: list[Card] = []
        self._load()
        if auto_seed and not self._cards:
            self.seed()

    # ------------------------------------------------------------------ IO ---
    def _load(self) -> None:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._cards = [Card.from_dict(c) for c in data.get("cards", [])]
        else:
            self._cards = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"cards": [c.to_dict() for c in self._cards]}
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------- consultas -
    def all(self) -> list[Card]:
        return sorted(self._cards, key=lambda c: (c.column, c.order))

    def get(self, card_id: str) -> Card:
        for card in self._cards:
            if card.id == card_id:
                return card
        raise KeyError(f"Cartão '{card_id}' não encontrado.")

    def as_payload(self) -> dict:
        """Formato que o frontend consome: colunas + cartões."""
        return {
            "columns": COLUMNS,
            "cards": [c.to_dict() for c in self.all()],
        }

    # --------------------------------------------------------------- mutações -
    def _next_order(self, column: str) -> float:
        orders = [c.order for c in self._cards if c.column == column]
        return (max(orders) + 1.0) if orders else 0.0

    def add(
        self,
        title: str,
        description: str = "",
        column: str = "backlog",
        sprint: str = "",
        labels: list[str] | None = None,
    ) -> Card:
        if column not in COLUMN_IDS:
            raise ValueError(f"Coluna inválida: '{column}'.")
        card = Card(
            title=title,
            description=description,
            column=column,
            sprint=sprint,
            labels=labels or [],
            order=self._next_order(column),
        )
        self._cards.append(card)
        self._save()
        return card

    def update(self, card_id: str, **fields) -> Card:
        card = self.get(card_id)
        if "column" in fields and fields["column"] not in COLUMN_IDS:
            raise ValueError(f"Coluna inválida: '{fields['column']}'.")
        for key in ("title", "description", "column", "sprint", "labels", "order"):
            if key in fields and fields[key] is not None:
                setattr(card, key, fields[key])
        card.updated_at = _now_iso()
        self._save()
        return card

    def move(self, card_id: str, column: str, order: float | None = None) -> Card:
        if column not in COLUMN_IDS:
            raise ValueError(f"Coluna inválida: '{column}'.")
        card = self.get(card_id)
        card.column = column
        card.order = self._next_order(column) if order is None else order
        card.updated_at = _now_iso()
        self._save()
        return card

    def delete(self, card_id: str) -> None:
        self.get(card_id)  # valida existência
        self._cards = [c for c in self._cards if c.id != card_id]
        self._save()

    def seed(self, force: bool = False) -> list[Card]:
        """(Re)popula o board com o planejamento de sprints.

        Sem `force`, só semeia se o board estiver vazio. Com `force`, substitui
        tudo pelo plano padrão.
        """
        if self._cards and not force:
            return self.all()
        self._cards = []
        per_column: dict[str, float] = {}
        for item in SEED_CARDS:
            column = item.get("column", "backlog")
            order = per_column.get(column, 0.0)
            per_column[column] = order + 1.0
            self._cards.append(
                Card(
                    title=item["title"],
                    description=item.get("description", ""),
                    column=column,
                    sprint=item.get("sprint", ""),
                    labels=list(item.get("labels", [])),
                    order=order,
                )
            )
        self._save()
        return self.all()
