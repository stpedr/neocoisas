"""Gerenciador simples de jobs em background (threads, em memória).

Para tarefas demoradas (geração de ideias, render) sem travar a requisição:
`submit(fn)` devolve um id; `get(id)` acompanha status/result. Estado em memória
(reinício da API zera os jobs) — suficiente para uso local.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def submit(self, fn) -> str:
        job_id = uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": "pending",
                "result": None,
                "error": None,
                "created_at": _now(),
                "finished_at": None,
            }

        def _run():
            with self._lock:
                self._jobs[job_id]["status"] = "running"
            try:
                result = fn()
                with self._lock:
                    self._jobs[job_id].update(
                        status="done", result=result, finished_at=_now()
                    )
            except Exception as exc:  # noqa: BLE001 - registra o erro no job
                with self._lock:
                    self._jobs[job_id].update(
                        status="error", error=str(exc), finished_at=_now()
                    )

        threading.Thread(target=_run, daemon=True).start()
        return job_id

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None


jobs = JobManager()
