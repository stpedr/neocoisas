"""Persistência do quadro Kanban em SQLite.

Guarda os cartões em SQLite (por padrão `output/board.json`, migrando um JSON
legado no mesmo caminho). Na primeira leitura de um board vazio, semeia
automaticamente com o planejamento de sprints (`board.seed`). A interface pública
é idêntica à versão em JSON.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import COLUMN_IDS, COLUMNS, Card
from .seed import SEED_CARDS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BoardStore:
    """Coleção persistente de `Card` com operações de quadro (SQLite)."""

    def __init__(self, path: str | Path = "output/board.json", auto_seed: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cards: list[Card] = []
        self._migrate_legacy_json()
        self._load()
        if auto_seed and not self._cards:
            self.seed()

    # ------------------------------------------------------------------ IO ---
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS cards (id TEXT PRIMARY KEY, data TEXT)")
        return conn

    def _migrate_legacy_json(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        with self.path.open("rb") as f:
            head = f.read(1)
        if head != b"{":  # já é SQLite
            return
        data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        cards = data.get("cards", [])
        self.path.unlink()
        conn = self._conn()
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO cards VALUES (?,?)",
                [(c["id"], json.dumps(c, ensure_ascii=False)) for c in cards],
            )
            conn.commit()
        finally:
            conn.close()

    def _load(self) -> None:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT data FROM cards").fetchall()
        finally:
            conn.close()
        self._cards = [Card.from_dict(json.loads(r["data"])) for r in rows]

    def _save(self) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM cards")
            conn.executemany(
                "INSERT INTO cards VALUES (?,?)",
                [(c.id, json.dumps(c.to_dict(), ensure_ascii=False)) for c in self._cards],
            )
            conn.commit()
        finally:
            conn.close()

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
