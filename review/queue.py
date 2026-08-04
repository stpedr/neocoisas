"""Fila de revisão de ideias, persistida em SQLite.

Guarda as ideias geradas e seus estados. É a fonte de verdade tanto do modo
manual ("Tinder": aprovar/rejeitar) quanto do automático (prompta-e-posta).

Persistência em SQLite (por padrão em `output/`, no `.gitignore`), com WAL para
suportar leitura/escrita concorrente sem corrupção. Um arquivo JSON legado no
mesmo caminho é **migrado automaticamente** na primeira abertura. A interface
pública é idêntica à versão anterior.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Idea, IdeaStatus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewQueue:
    """Coleção persistente de `Idea` com operações de aprovação (SQLite)."""

    def __init__(self, path: str | Path = "output/review_queue.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_json()
        self._init_db()

    # ------------------------------------------------------------------ IO ---
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS ideas ("
                "id TEXT PRIMARY KEY, status TEXT, created_at TEXT, data TEXT)"
            )
            conn.commit()
        finally:
            conn.close()

    def _migrate_legacy_json(self) -> None:
        """Se o arquivo for JSON legado, importa para SQLite no mesmo caminho."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        with self.path.open("rb") as f:
            head = f.read(1)
        if head != b"{":  # já é SQLite (header binário) — nada a fazer
            return
        data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        ideas = data.get("ideas", [])
        self.path.unlink()  # remove o JSON para o SQLite recriar no mesmo caminho
        self._init_db()
        if ideas:
            conn = self._conn()
            try:
                conn.executemany(
                    "INSERT OR REPLACE INTO ideas VALUES (?,?,?,?)",
                    [
                        (d["id"], d.get("status"), d.get("created_at"),
                         json.dumps(d, ensure_ascii=False))
                        for d in ideas
                    ],
                )
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _to_idea(row: sqlite3.Row) -> Idea:
        return Idea.from_dict(json.loads(row["data"]))

    def _put(self, idea: Idea) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO ideas VALUES (?,?,?,?)",
                (idea.id, idea.status, idea.created_at,
                 json.dumps(idea.to_dict(), ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------- consultas -
    def all(self) -> list[Idea]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT data FROM ideas ORDER BY rowid").fetchall()
        finally:
            conn.close()
        return [self._to_idea(r) for r in rows]

    def get(self, idea_id: str) -> Idea:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT data FROM ideas WHERE id = ?", (idea_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise KeyError(f"Ideia '{idea_id}' não encontrada na fila.")
        return self._to_idea(row)

    def by_status(self, status: str) -> list[Idea]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT data FROM ideas WHERE status = ? ORDER BY rowid", (status,)
            ).fetchall()
        finally:
            conn.close()
        return [self._to_idea(r) for r in rows]

    def pending(self) -> list[Idea]:
        return sorted(self.by_status(IdeaStatus.PENDING), key=lambda i: i.created_at)

    def approved(self) -> list[Idea]:
        return self.by_status(IdeaStatus.APPROVED)

    def counts(self) -> dict:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM ideas GROUP BY status"
            ).fetchall()
        finally:
            conn.close()
        contagem = {r["status"]: r["n"] for r in rows}
        return {status: contagem.get(status, 0) for status in sorted(IdeaStatus.ALL)}

    # --------------------------------------------------------------- mutações -
    def add(self, idea: Idea) -> Idea:
        self._put(idea)
        return idea

    def update(self, idea: Idea) -> Idea:
        """Persiste um objeto `Idea` mutado (upsert por id)."""
        self._put(idea)
        return idea

    def add_many(self, ideas: list[Idea]) -> list[Idea]:
        for idea in ideas:
            self._put(idea)
        return ideas

    def _set_status(self, idea_id: str, status: str) -> Idea:
        idea = self.get(idea_id)
        idea.status = status
        idea.decided_at = _now_iso()
        self._put(idea)
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
        self._put(idea)
        return idea

    def attach_thumbnail(self, idea_id: str, thumbnail_path: str) -> Idea:
        idea = self.get(idea_id)
        idea.thumbnail_path = thumbnail_path
        self._put(idea)
        return idea

    def add_variant(self, idea_id: str, lang: str, video_path: str) -> Idea:
        idea = self.get(idea_id)
        idea.video_variants[lang] = video_path
        self._put(idea)
        return idea

    def set_metrics(self, idea_id: str, metrics: dict) -> Idea:
        idea = self.get(idea_id)
        idea.metrics.update(metrics)
        self._put(idea)
        return idea

    def clear_decided(self) -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM ideas WHERE status IN (?, ?)",
                (IdeaStatus.REJECTED, IdeaStatus.POSTED),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    # Compat.: quem chamava _save() (persistência já é por operação).
    def _save(self) -> None:  # pragma: no cover - no-op mantido por compatibilidade
        pass
