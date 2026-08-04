"""Testes da fila de revisão (ReviewQueue) — persistência e estados."""

import pytest

from agents.video_pipeline import Scene
from review.models import Idea, IdeaStatus
from review.queue import ReviewQueue


def _idea(title="t"):
    return Idea(prompt="p", title=title, scenes=[Scene("n", "v", 3.0)])


def test_add_e_pending(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    q.add(_idea("a"))
    q.add(_idea("b"))
    assert len(q.pending()) == 2
    assert q.counts()["pending"] == 2


def test_approve_move_para_approved(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    idea = q.add(_idea())
    q.approve(idea.id)
    assert q.get(idea.id).status == IdeaStatus.APPROVED
    assert q.get(idea.id).decided_at is not None
    assert len(q.pending()) == 0
    assert len(q.approved()) == 1


def test_reject(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    idea = q.add(_idea())
    q.reject(idea.id)
    assert q.get(idea.id).status == IdeaStatus.REJECTED
    assert q.counts()["rejected"] == 1


def test_mark_posted_de_aprovada(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    idea = q.add(_idea())
    q.approve(idea.id)
    q.mark_posted(idea.id)
    assert q.get(idea.id).status == IdeaStatus.POSTED


def test_mark_posted_de_rejeitada_falha(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    idea = q.add(_idea())
    q.reject(idea.id)
    with pytest.raises(ValueError):
        q.mark_posted(idea.id)


def test_persistencia_reabre_do_disco(tmp_path):
    path = tmp_path / "q.json"
    q1 = ReviewQueue(path)
    idea = q1.add(_idea("persistida"))
    q1.approve(idea.id)

    q2 = ReviewQueue(path)  # nova instância lê o mesmo arquivo
    assert len(q2.all()) == 1
    reloaded = q2.get(idea.id)
    assert reloaded.title == "persistida"
    assert reloaded.status == IdeaStatus.APPROVED
    assert reloaded.scenes[0].narration == "n"


def test_get_inexistente_levanta_keyerror(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    with pytest.raises(KeyError):
        q.get("nao-existe")


def test_attach_video(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    idea = q.add(_idea())
    q.attach_video(idea.id, "output/x.mp4")
    assert q.get(idea.id).video_path == "output/x.mp4"


def test_clear_decided_mantem_pendentes_e_aprovadas(tmp_path):
    q = ReviewQueue(tmp_path / "q.json")
    pend = q.add(_idea("pend"))
    apr = q.add(_idea("apr"))
    rej = q.add(_idea("rej"))
    post = q.add(_idea("post"))
    q.approve(apr.id)
    q.reject(rej.id)
    q.approve(post.id)
    q.mark_posted(post.id)

    removed = q.clear_decided()
    assert removed == 2  # rejeitada + postada
    restantes = {i.id for i in q.all()}
    assert restantes == {pend.id, apr.id}
