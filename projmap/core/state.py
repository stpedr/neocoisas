"""Estado vivo do projeto, compartilhado entre a API do mestre e o renderer.

Na F1 mestre e nó rodam no mesmo processo: a API (thread do uvicorn) altera o
projeto e o renderer (thread principal, laço do pyglet) lê. A sincronização é
por **revisão**: cada mudança incrementa ``revision`` e o renderer, a cada
frame, só compara um inteiro — barato — e reconstrói o que mudou quando a
revisão avança. Na F2 o mesmo contrato vira mensagem ``apply_config{rev}``.
"""

from __future__ import annotations

import threading
from typing import Callable

from .project import Project
from .store import ProjectStore


class ProjectState:
    def __init__(self, store: ProjectStore, project: Project | None = None):
        self.store = store
        self._project = project if project is not None else store.load()
        self._revision = 0
        self._lock = threading.Lock()

    @property
    def revision(self) -> int:
        return self._revision

    def snapshot(self) -> tuple[int, Project]:
        """Cópia consistente (revisão + projeto). O projeto é tratado como imutável."""
        with self._lock:
            return self._revision, self._project

    def replace(self, project: Project, persist: bool = True) -> int:
        with self._lock:
            if persist:
                self.store.save(project)
            self._project = project
            self._revision += 1
            return self._revision

    def update(self, fn: Callable[[Project], Project], persist: bool = True) -> int:
        """Aplica ``fn`` a uma cópia profunda e publica o resultado (validado)."""
        with self._lock:
            draft = self._project.model_copy(deep=True)
            new = fn(draft)
            new = Project.model_validate(new.model_dump())  # revalida referências
            if persist:
                self.store.save(new)
            self._project = new
            self._revision += 1
            return self._revision
