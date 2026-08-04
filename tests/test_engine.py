"""Testes do orquestrador (engine) com um gerador falso — sem Ollama."""

import pytest

from agents.video_pipeline import Scene
from engine import generate_and_enqueue, post_approved, run_prompt
from review.models import Idea, IdeaStatus
from review.queue import ReviewQueue


class FakeGenerator:
    """Gerador determinístico que não usa Ollama."""

    def __init__(self, n_scenes=2):
        self.n_scenes = n_scenes

    def generate(self, prompt, count=5, num_scenes=5, mode="manual"):
        return [
            Idea(
                prompt=prompt,
                title=f"Ideia {i}",
                scenes=[Scene("n", "v", 3.0) for _ in range(self.n_scenes)],
                mode=mode,
            )
            for i in range(count)
        ]


def test_modo_manual_entra_como_pending(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    ideas = generate_and_enqueue("prompt", q, FakeGenerator(), count=3, mode="manual")
    assert len(ideas) == 3
    assert all(i.status == IdeaStatus.PENDING for i in q.all())
    assert q.counts()["pending"] == 3


def test_modo_auto_entra_como_approved(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    generate_and_enqueue("prompt", q, FakeGenerator(), count=2, mode="auto")
    assert all(i.status == IdeaStatus.APPROVED for i in q.all())
    assert q.counts()["approved"] == 2


def test_modo_invalido_levanta(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    with pytest.raises(ValueError):
        generate_and_enqueue("p", q, FakeGenerator(), mode="xpto")


def test_post_approved_sem_publisher_nao_posta(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    generate_and_enqueue("p", q, FakeGenerator(), count=2, mode="auto")
    posted = post_approved(q, publisher=None)
    assert posted == []
    assert q.counts()["approved"] == 2
    assert q.counts()["posted"] == 0


def test_post_approved_com_publisher_marca_postado(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    generate_and_enqueue("p", q, FakeGenerator(), count=2, mode="auto")
    chamadas = []
    posted = post_approved(q, publisher=lambda idea: chamadas.append(idea.id) or "url")
    assert len(posted) == 2
    assert len(chamadas) == 2
    assert q.counts()["posted"] == 2
    assert q.counts()["approved"] == 0


def test_publisher_que_falha_nao_derruba_lote(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    generate_and_enqueue("p", q, FakeGenerator(), count=2, mode="auto")

    def publisher(idea):
        raise RuntimeError("API fora do ar")

    posted = post_approved(q, publisher=publisher)
    assert posted == []
    # Ideias seguem aprovadas, com a falha registrada na nota.
    assert q.counts()["approved"] == 2
    assert all("Falha ao postar" in i.note for i in q.approved())


def test_run_prompt_auto_com_publisher(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    resumo = run_prompt(
        "p", q, FakeGenerator(), mode="auto", count=2, publisher=lambda i: "ok"
    )
    assert resumo["generated"] == 2
    assert resumo["posted"] == 2
    assert resumo["mode"] == "auto"


def test_run_prompt_manual_nao_posta(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    resumo = run_prompt("p", q, FakeGenerator(), mode="manual", count=2)
    assert resumo["generated"] == 2
    assert resumo["posted"] == 0
