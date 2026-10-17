"""Snapshot da saída real do projetor, sob demanda.

A API (thread do uvicorn) pede um quadro com :meth:`OutputTap.request`; a
janela (thread do GL) atende no próximo ``on_draw`` com :meth:`service`, lendo
o framebuffer já renderizado. Sem pedido pendente, o custo por frame é um
``Event.is_set()``. Serve para conferir de longe o que está na parede (MCP,
e2e) sem câmera apontada para ela.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)


class OutputTap:
    def __init__(self) -> None:
        self._want = threading.Event()
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._max_width = 960
        self._png: Optional[bytes] = None
        self.attached = False

    def request(self, max_width: int = 960, timeout: float = 3.0) -> Optional[bytes]:
        """PNG do próximo quadro (RGB, largura ≤ ``max_width``); ``None`` se a janela não respondeu."""
        if not self.attached:
            return None
        with self._lock:
            self._max_width = max(16, int(max_width))
            self._png = None
            self._done.clear()
            self._want.set()
        if not self._done.wait(timeout):
            return None
        with self._lock:
            return self._png

    def service(self, read_rgb: Callable[[], np.ndarray]) -> None:
        """Chamado pela janela depois de renderizar; ``read_rgb`` devolve ``(h, w, 3)`` com linha 0 = topo."""
        if not self._want.is_set():
            return
        self._want.clear()
        png: Optional[bytes] = None
        try:
            rgb = read_rgb()
            h, w = rgb.shape[:2]
            with self._lock:
                max_w = self._max_width
            if w > max_w:
                rgb = cv2.resize(rgb, (max_w, max(1, round(h * max_w / w))), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            png = buf.tobytes() if ok else None
        except Exception as exc:  # noqa: BLE001 — snapshot falho não pode derrubar a projeção
            log.error("snapshot da saída falhou: %s", exc)
        with self._lock:
            self._png = png
        self._done.set()
