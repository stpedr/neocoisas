"""Factory das fontes de conteúdo — mesmo padrão "contrato + factory" do repo.

``get_source(spec, media_path)`` escolhe a implementação pelo ``kind`` da
superfície. NDI (F5) entra aqui como mais um ``kind``, sem mexer no renderer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from ..core.project import SourceSpec
from .base import FrameSource, StaticSource
from .patterns import make_test_card, solid

MediaResolver = Callable[[str], Path]


class _TimeShift:
    """Aplica ``speed`` e ``offset_s`` da superfície sem cada fonte reimplementar."""

    def __init__(self, inner: FrameSource, speed: float, offset: float):
        self.inner, self.speed, self.offset = inner, speed, offset

    @property
    def size(self):
        return self.inner.size

    @property
    def duration(self):
        return self.inner.duration

    def frame_at(self, t: float):
        return self.inner.frame_at(t * self.speed + self.offset)

    def close(self) -> None:
        self.inner.close()


def load_image_rgba(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)  # fromfile+imdecode: aceita caminhos unicode no Windows
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"imagem ilegível: {path.name}")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGBA)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
    return img


def get_source(spec: SourceSpec, media_path: Optional[MediaResolver] = None) -> Optional[FrameSource]:
    """Cria a fonte da superfície; ``None`` quando não há o que mostrar."""
    kind = spec.kind
    if kind == "none":
        return None
    if kind == "color":
        return StaticSource(solid(4, 4, spec.color))
    if kind == "test":
        return StaticSource(make_test_card())
    if media_path is None or not spec.media:
        raise ValueError(f"fonte '{kind}' precisa de mídia")
    path = media_path(spec.media)
    if kind == "image":
        src: FrameSource = StaticSource(load_image_rgba(path))
    elif kind == "gif":
        from .gif import GifSource

        src = GifSource(path, loop=spec.loop)
    elif kind == "video":
        from .video import VideoSource  # import tardio: PyAV só é exigido se houver vídeo

        src = VideoSource(path, loop=spec.loop)
    else:  # pragma: no cover — o esquema já restringe os kinds
        raise ValueError(f"fonte desconhecida: {kind}")
    if spec.speed != 1.0 or spec.offset_s:
        src = _TimeShift(src, spec.speed, spec.offset_s)
    return src
