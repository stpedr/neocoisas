"""Testes do quadro Kanban (BoardStore) — semeadura e mutações."""

import pytest

from board.models import COLUMN_IDS
from board.seed import SEED_CARDS
from board.store import BoardStore


def test_auto_seed_popula_board_vazio(tmp_path):
    b = BoardStore(tmp_path / "b.json")
    assert len(b.all()) == len(SEED_CARDS)


def test_sem_auto_seed_fica_vazio(tmp_path):
    b = BoardStore(tmp_path / "b.json", auto_seed=False)
    assert b.all() == []


def test_as_payload_tem_colunas_e_cards(tmp_path):
    b = BoardStore(tmp_path / "b.json")
    payload = b.as_payload()
    assert {c["id"] for c in payload["columns"]} == set(COLUMN_IDS)
    assert len(payload["cards"]) == len(SEED_CARDS)


def test_add_card(tmp_path):
    b = BoardStore(tmp_path / "b.json", auto_seed=False)
    card = b.add("Nova", description="desc", column="todo", labels=["x"])
    assert card.column == "todo"
    assert card.labels == ["x"]
    assert len(b.all()) == 1


def test_add_coluna_invalida_levanta(tmp_path):
    b = BoardStore(tmp_path / "b.json", auto_seed=False)
    with pytest.raises(ValueError):
        b.add("X", column="inexistente")


def test_move_card(tmp_path):
    b = BoardStore(tmp_path / "b.json", auto_seed=False)
    card = b.add("X", column="backlog")
    b.move(card.id, "done")
    assert b.get(card.id).column == "done"


def test_move_coluna_invalida_levanta(tmp_path):
    b = BoardStore(tmp_path / "b.json", auto_seed=False)
    card = b.add("X")
    with pytest.raises(ValueError):
        b.move(card.id, "nope")


def test_update_campos(tmp_path):
    b = BoardStore(tmp_path / "b.json", auto_seed=False)
    card = b.add("X")
    b.update(card.id, title="Novo", sprint="Sprint 9")
    assert b.get(card.id).title == "Novo"
    assert b.get(card.id).sprint == "Sprint 9"


def test_delete(tmp_path):
    b = BoardStore(tmp_path / "b.json", auto_seed=False)
    card = b.add("X")
    b.delete(card.id)
    assert b.all() == []
    with pytest.raises(KeyError):
        b.get(card.id)


def test_persistencia(tmp_path):
    path = tmp_path / "b.json"
    b1 = BoardStore(path, auto_seed=False)
    b1.add("Persistido", column="review")
    b2 = BoardStore(path, auto_seed=False)
    assert len(b2.all()) == 1
    assert b2.all()[0].column == "review"


def test_migra_json_legado_para_sqlite(tmp_path):
    import json

    path = tmp_path / "b.json"
    path.write_text(
        json.dumps({"cards": [{"id": "c1", "title": "Legado", "column": "todo"}]}),
        encoding="utf-8",
    )
    b = BoardStore(path, auto_seed=False)  # migra e não semeia
    assert len(b.all()) == 1
    assert b.get("c1").title == "Legado"
    assert path.open("rb").read(1) != b"{"


def test_seed_force_substitui(tmp_path):
    b = BoardStore(tmp_path / "b.json", auto_seed=False)
    b.add("Manual")
    b.seed(force=True)
    titulos = {c.title for c in b.all()}
    assert "Manual" not in titulos
    assert len(b.all()) == len(SEED_CARDS)
