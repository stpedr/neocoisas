"""Ajuste de imagem em CPU — espelho exato do ``adjust()`` de ``surface.frag``.

Serve de oráculo nos testes (GPU vs. CPU) e documenta a fórmula num lugar só.
Opera em RGB **linear de exibição** em [0, 1], antes do alfa pré-multiplicado.
"""

from __future__ import annotations

import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)  # Rec. 709


def temperature_gain(t: float) -> np.ndarray:
    """Ganho por canal: +1 = quente (mais vermelho, menos azul), -1 = frio."""
    return np.array([1.0 + 0.12 * t, 1.0 + 0.02 * t, 1.0 - 0.12 * t], np.float32)


def adjust(rgb: np.ndarray, brightness=1.0, contrast=1.0, saturation=1.0, gamma=1.0, temperature=0.0) -> np.ndarray:
    c = np.asarray(rgb, np.float32)
    c = (c - 0.5) * contrast + 0.5
    c = c * brightness
    luma = (c * LUMA).sum(axis=-1, keepdims=True)
    c = luma + (c - luma) * saturation
    c = c * temperature_gain(temperature)
    c = np.clip(c, 0.0, 1.0)
    return np.power(c, 1.0 / gamma)
