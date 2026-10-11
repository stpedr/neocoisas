"""GIF animado com a duração real de cada frame.

GIFs têm atraso por frame (não um fps fixo). Tratamos como os navegadores:
atraso ≤ 10 ms (ou ausente) vira 100 ms — muitos GIFs "0 ms" contam com isso.
Todos os frames são decodificados na carga (GIFs são pequenos); ``frame_at`` é
uma busca binária nos tempos acumulados.
"""

from __future__ import annotations

import bisect
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageSequence

from .base import loop_time

MIN_DELAY_MS = 10
DEFAULT_DELAY_MS = 100
MAX_FRAMES = 2000


class GifSource:
    def __init__(self, path: Path, loop: bool = True):
        self.loop = loop
        frames: list[np.ndarray] = []
        delays: list[float] = []
        with Image.open(path) as im:
            for frame in ImageSequence.Iterator(im):
                if len(frames) >= MAX_FRAMES:
                    break
                delay = frame.info.get("duration", DEFAULT_DELAY_MS) or 0
                if delay <= MIN_DELAY_MS:
                    delay = DEFAULT_DELAY_MS
                frames.append(np.asarray(frame.convert("RGBA"), dtype=np.uint8).copy())
                delays.append(delay / 1000.0)
        if not frames:
            raise ValueError(f"GIF sem frames: {path}")
        self._frames = frames
        self.delays = delays
        self._starts = [0.0]
        for d in delays[:-1]:
            self._starts.append(self._starts[-1] + d)
        self._duration = sum(delays)

    @property
    def size(self) -> tuple[int, int]:
        h, w = self._frames[0].shape[:2]
        return w, h

    @property
    def duration(self) -> Optional[float]:
        return self._duration

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    def index_at(self, t: float) -> int:
        local = loop_time(t, self._duration, self.loop)
        # Folga contra soma de floats (0.1+0.1+0.1 = 0.30000000000000004).
        return max(0, bisect.bisect_right(self._starts, local + 1e-9) - 1)

    def frame_at(self, t: float) -> tuple[int, np.ndarray]:
        i = self.index_at(t)
        return i, self._frames[i]

    def close(self) -> None:
        self._frames = self._frames[:1]
