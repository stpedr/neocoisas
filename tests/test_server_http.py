"""Testes de integração HTTP da API (FastAPI TestClient) — sem Ollama."""

import pytest
from fastapi.testclient import TestClient

import server
from agents.video_pipeline import Scene
from review.models import Idea
from review.queue import ReviewQueue


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "QUEUE_PATH", str(tmp_path / "q.json"))
    monkeypatch.setattr(server, "BOARD_PATH", str(tmp_path / "b.json"))
    monkeypatch.delenv("ANE_API_KEY", raising=False)
    with TestClient(server.app) as c:
        yield c


def _add_idea(title="ideia"):
    q = ReviewQueue(server.QUEUE_PATH)
    return q.add(Idea(prompt="p", title=title, scenes=[Scene("n", "v", 3.0)]))


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_board_seed_e_crud(client):
    r = client.get("/api/board")
    assert r.status_code == 200
    body = r.json()
    assert body["cards"] and body["columns"]

    # cria
    r = client.post("/api/board/cards", json={"title": "Nova", "column": "todo"})
    assert r.status_code == 200
    cid = r.json()["id"]
    # move
    r = client.patch(f"/api/board/cards/{cid}", json={"column": "done"})
    assert r.json()["column"] == "done"
    # apaga
    assert client.delete(f"/api/board/cards/{cid}").status_code == 200


def test_ideas_fluxo(client):
    idea = _add_idea()
    assert client.get("/api/ideas").json()["counts"]["pending"] == 1
    r = client.post(f"/api/ideas/{idea.id}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    r = client.post(f"/api/ideas/{idea.id}/reject")
    assert r.json()["status"] == "rejected"


def test_idea_inexistente_404(client):
    assert client.post("/api/ideas/xxx/approve").status_code == 404


def test_job_inexistente_404(client):
    assert client.get("/api/jobs/xxx").status_code == 404


def test_metrics(client):
    idea = _add_idea()
    r = client.post(f"/api/ideas/{idea.id}/metrics", json={"views": 10})
    assert r.status_code == 200 and r.json()["metrics"]["views"] == 10


def test_auth_bloqueia_sem_chave(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "QUEUE_PATH", str(tmp_path / "q.json"))
    monkeypatch.setattr(server, "BOARD_PATH", str(tmp_path / "b.json"))
    monkeypatch.setenv("ANE_API_KEY", "segredo")
    with TestClient(server.app) as c:
        assert c.get("/api/health").status_code == 200          # público
        assert c.get("/api/board").status_code == 401           # sem chave
        r = c.get("/api/board", headers={"X-API-Key": "segredo"})
        assert r.status_code == 200                              # com chave
