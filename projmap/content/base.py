"""Contrato das fontes de conteúdo.

Toda fonte responde a uma única pergunta: *qual frame mostrar no instante t?*
(``frame_at(t)``). Não existe "próximo frame": o tempo vem de fora (relógio
local na F1, relógio comum sincronizado na F2). É isso que permite vários nós
mostrarem o mesmo frame no mesmo instante sem trocar mensagens por frame.

``frame_at`` devolve ``(chave, imagem)``. A chave muda só quando a imagem muda;
o renderer compara chaves e evita reenviar a textura à GPU (um 1080p RGBA são
~8 MB por upload).
"""

from __future__ import annotations

from typing import Optional, Protocol

import numpy as np


class FrameSource(Protocol):
    @property
    def size(self) -> tuple[int, int]:
        """(largura, altura) em pixels."""

    @property
    def duration(self) -> Optional[float]:
        """Duração em segundos (``None`` para fontes estáticas)."""

    def frame_at(self, t: float) -> tuple[int, np.ndarray]:
        """Frame RGBA ``uint8 (h, w, 4)`` para o instante ``t`` (s) e sua chave."""

    def close(self) -> None:
        ...


def to_rgba(img: np.ndarray) -> np.ndarray:
    """Normaliza para RGBA uint8 contíguo."""
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=-1)
    if img.shape[2] == 3:
        alpha = np.full(img.shape[:2] + (1,), 255, dtype=np.uint8)
        img = np.concatenate([img, alpha], axis=-1)
    return np.ascontiguousarray(img, dtype=np.uint8)


def loop_time(t: float, duration: Optional[float], loop: bool) -> float:
    """Tempo local da fonte: em loop faz módulo; sem loop, para no último instante."""
    if not duration or duration <= 0:
        return max(t, 0.0)
    if loop:
        return t % duration
    return min(max(t, 0.0), max(duration - 1e-6, 0.0))


class StaticSource:
    """Fonte de um único frame (imagem, cor sólida, padrão)."""

    def __init__(self, rgba: np.ndarray):
        self._rgba = to_rgba(rgba)

    @property
    def size(self) -> tuple[int, int]:
        h, w = self._rgba.shape[:2]
        return w, h

    @property
    def duration(self) -> Optional[float]:
        return None

    def frame_at(self, t: float) -> tuple[int, np.ndarray]:
        return 0, self._rgba

    def close(self) -> None:
        pass
