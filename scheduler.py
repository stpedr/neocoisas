"""Agendamento local de postagens.

Em intervalos definidos, pega ideias **aprovadas**, renderiza o vídeo (se ainda
não houver) e publica via `publisher` configurado. Sem publisher/token, opera em
modo **simulado** (marca como postada, sem publicar de fato) — assim o fluxo
roda localmente; configure o token depois para virar publicação real.

Config persistida em `output/schedule.json`. Roda dentro do processo da API com
APScheduler (thread em background).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from review.queue import ReviewQueue

SCHEDULE_PATH = os.environ.get("ANE_SCHEDULE", "output/schedule.json")
QUEUE_PATH = os.environ.get("ANE_QUEUE", "output/review_queue.json")
CONFIG_PATH = os.environ.get("ANE_CONFIG", "config.json")

_DEFAULTS = {
    "enabled": False,
    "every_minutes": 60,
    "max_per_run": 1,
    "render_before": True,
    "simulate": True,          # sem publisher, marca como postada (não publica)
    "last_run": None,
    "last_result": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScheduleStore:
    """Config do agendamento, persistida em JSON."""

    def __init__(self, path: str | Path = SCHEDULE_PATH):
        self.path = Path(path)

    def get(self) -> dict:
        data = dict(_DEFAULTS)
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                data.update(json.load(f))
        return data

    def update(self, **fields) -> dict:
        data = self.get()
        for key in ("enabled", "every_minutes", "max_per_run", "render_before",
                    "simulate", "last_run", "last_result"):
            if key in fields and fields[key] is not None:
                data[key] = fields[key]
        # Sanidade
        data["every_minutes"] = max(1, int(data["every_minutes"]))
        data["max_per_run"] = max(1, int(data["max_per_run"]))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return data


def _load_config() -> dict:
    path = Path(CONFIG_PATH)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def run_scheduled_posts(
    queue: ReviewQueue,
    *,
    config: dict | None = None,
    publisher=None,
    renderer=None,
    max_per_run: int = 1,
    render_before: bool = True,
    simulate: bool = True,
) -> dict:
    """Processa até `max_per_run` ideias aprovadas. Núcleo testável (injetável)."""
    config = config or {}
    detalhes: list[dict] = []
    posted = simulated = errors = 0

    for idea in queue.approved()[:max_per_run]:
        if render_before and not idea.video_path and renderer is not None:
            try:
                path = renderer(idea, config)
                queue.attach_video(idea.id, str(path))
                idea = queue.get(idea.id)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                idea.note = f"Falha ao renderizar: {exc}"
                queue._save()
                detalhes.append({"id": idea.id, "status": "render_error", "info": str(exc)})
                continue

        if publisher is not None:
            try:
                url = publisher(idea)
                idea.note = f"Postado: {url}" if url else "Postado."
                queue.mark_posted(idea.id)
                posted += 1
                detalhes.append({"id": idea.id, "status": "posted", "info": url})
            except Exception as exc:  # noqa: BLE001
                errors += 1
                idea.note = f"Falha ao postar: {exc}"
                queue._save()
                detalhes.append({"id": idea.id, "status": "post_error", "info": str(exc)})
        elif simulate:
            idea.note = "Postagem simulada (sem publisher configurado)."
            queue.mark_posted(idea.id)
            simulated += 1
            detalhes.append({"id": idea.id, "status": "simulated", "info": None})
        else:
            detalhes.append({"id": idea.id, "status": "skipped", "info": "sem publisher"})

    return {
        "processed": len(detalhes),
        "posted": posted,
        "simulated": simulated,
        "errors": errors,
        "details": detalhes,
    }


def run_tick() -> dict:
    """Executa uma rodada real (usada pelo scheduler e pelo endpoint run-now)."""
    from publishers import get_publisher
    from render import render_idea

    store = ScheduleStore()
    cfg = store.get()
    app_config = _load_config()
    queue = ReviewQueue(QUEUE_PATH)

    resumo = run_scheduled_posts(
        queue,
        config=app_config,
        publisher=get_publisher(app_config),
        renderer=render_idea,
        max_per_run=cfg["max_per_run"],
        render_before=cfg["render_before"],
        simulate=cfg["simulate"],
    )
    store.update(last_run=_now_iso(), last_result=json.dumps(resumo, ensure_ascii=False))
    return resumo


class SchedulerManager:
    """Gerencia o job periódico do APScheduler dentro do processo da API."""

    def __init__(self):
        self._sched = None

    def start(self) -> None:
        if self._sched is None:
            from apscheduler.schedulers.background import BackgroundScheduler

            self._sched = BackgroundScheduler(daemon=True)
            self._sched.start()
        self.reconfigure()

    def shutdown(self) -> None:
        if self._sched is not None:
            self._sched.shutdown(wait=False)
            self._sched = None

    def reconfigure(self) -> None:
        """(Re)cria o job conforme a config atual."""
        if self._sched is None:
            return
        from apscheduler.triggers.interval import IntervalTrigger

        try:
            self._sched.remove_job("auto_post")
        except Exception:  # noqa: BLE001 - job pode não existir
            pass
        cfg = ScheduleStore().get()
        if cfg["enabled"]:
            self._sched.add_job(
                run_tick,
                IntervalTrigger(minutes=cfg["every_minutes"]),
                id="auto_post",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

    def next_run(self) -> str | None:
        if self._sched is None:
            return None
        job = self._sched.get_job("auto_post")
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None


# Singleton usado pela API.
manager = SchedulerManager()
