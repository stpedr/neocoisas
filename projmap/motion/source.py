"""Fonte ``motion``: o quadro mais novo que o navegador mandou para a sessão.

Antes do primeiro quadro (navegador abrindo, motion carregando o Three.js do
CDN) a superfície fica preta — apagada, não "quebrada".
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..core.project import SourceSpec
from .hub import DEFAULT_SIZE, MotionHub, MotionSession, hub


class MotionSource:
    def __init__(self, sess: MotionSession, owner: MotionHub):
        self._sess = sess
        self._hub = owner
        self._closed = False

    @property
    def session(self) -> MotionSession:
        return self._sess

    @property
    def size(self) -> tuple[int, int]:
        return self._sess.size

    @property
    def duration(self) -> Optional[float]:
        return None

    def frame_at(self, t: float) -> tuple[int, np.ndarray]:
        return self._hub.latest(self._sess)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._hub.release(self._sess)


def open_motion(spec: SourceSpec, owner: Optional[MotionHub] = None) -> MotionSource:
    if not spec.media:
        raise ValueError("fonte 'motion' precisa de mídia")
    h = owner or hub()
    sess = h.open_session(spec.media, DEFAULT_SIZE, dict(spec.params), spec.mode, spec.device)
    return MotionSource(sess, h)
