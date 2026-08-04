"""Testes do agendamento (ScheduleStore + run_scheduled_posts) — sem APScheduler."""

from agents.video_pipeline import Scene
from review.models import Idea, IdeaStatus
from review.queue import ReviewQueue
from scheduler import ScheduleStore, run_scheduled_posts


def _approved_queue(tmp_path, n=3):
    q = ReviewQueue(tmp_path / "q.json")
    for i in range(n):
        idea = q.add(Idea(prompt="p", title=f"i{i}", scenes=[Scene("n", "v", 3.0)]))
        q.approve(idea.id)
    return q


# ------------------------------------------------------------ ScheduleStore --
def test_store_defaults(tmp_path):
    s = ScheduleStore(tmp_path / "s.json").get()
    assert s["enabled"] is False
    assert s["every_minutes"] == 60
    assert s["simulate"] is True


def test_store_update_e_persiste(tmp_path):
    path = tmp_path / "s.json"
    ScheduleStore(path).update(enabled=True, every_minutes=15, max_per_run=3)
    reloaded = ScheduleStore(path).get()
    assert reloaded["enabled"] is True
    assert reloaded["every_minutes"] == 15
    assert reloaded["max_per_run"] == 3


def test_store_sanitiza_valores(tmp_path):
    s = ScheduleStore(tmp_path / "s.json").update(every_minutes=0, max_per_run=-5)
    assert s["every_minutes"] == 1
    assert s["max_per_run"] == 1


# ---------------------------------------------------- run_scheduled_posts ----
def test_simulado_marca_postado(tmp_path):
    q = _approved_queue(tmp_path, 3)
    res = run_scheduled_posts(q, publisher=None, simulate=True, max_per_run=2, render_before=False)
    assert res["simulated"] == 2
    assert res["processed"] == 2
    assert q.counts()["posted"] == 2
    assert q.counts()["approved"] == 1  # respeitou max_per_run


def test_sem_publisher_e_sem_simulate_pula(tmp_path):
    q = _approved_queue(tmp_path, 1)
    res = run_scheduled_posts(q, publisher=None, simulate=False, render_before=False)
    assert res["posted"] == 0 and res["simulated"] == 0
    assert q.counts()["approved"] == 1


def test_com_publisher_posta(tmp_path):
    q = _approved_queue(tmp_path, 2)
    chamadas = []
    res = run_scheduled_posts(
        q, publisher=lambda idea: chamadas.append(idea.id) or "http://x", max_per_run=5, render_before=False
    )
    assert res["posted"] == 2
    assert len(chamadas) == 2
    assert q.counts()["posted"] == 2


def test_render_before_anexa_video(tmp_path):
    q = _approved_queue(tmp_path, 1)

    def fake_render(idea, config):
        return tmp_path / f"{idea.id}.mp4"

    run_scheduled_posts(q, renderer=fake_render, render_before=True, simulate=True, max_per_run=1)
    idea = q.by_status(IdeaStatus.POSTED)[0]
    assert idea.video_path and idea.video_path.endswith(".mp4")


def test_render_falha_nao_posta(tmp_path):
    q = _approved_queue(tmp_path, 1)

    def bad_render(idea, config):
        raise RuntimeError("ffmpeg quebrou")

    res = run_scheduled_posts(q, renderer=bad_render, render_before=True, simulate=True)
    assert res["errors"] == 1
    assert res["posted"] == 0 and res["simulated"] == 0
    assert q.counts()["approved"] == 1  # segue aprovada
