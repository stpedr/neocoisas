"""Efeitos reativos ao áudio — fórmulas num lugar só (CPU) e o que o shader recebe.

Cada superfície tem uma lista ``fx`` (``core/project.py::AudioFx``). A cada
frame os níveis da entrada de áudio (0..1 por banda) viram um punhado de
uniforms (:class:`FxUniforms`), e ``surface.frag`` aplica em cima da fonte —
qualquer fonte: vídeo ao vivo, arquivo, GIF, imagem.

Ordem no shader (e aqui): coordenadas (zoom → tremor → separação RGB) →
cor (ganho → matiz → inversão → flash) → ajustes de cor da superfície/projetor.
:func:`fx_sample_uv` e :func:`apply_color_fx` são o espelho exato em CPU
(oráculo dos testes GPU × CPU, como ``color.py``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from ..core.project import AudioFx

BANDS = ("bass", "mid", "high", "level", "beat")

# Quanto cada efeito mexe com amount=1 e banda no máximo.
PULSE_MAX_GAIN = 1.5  # brilho até 2,5×
HUE_MAX_RAD = math.pi  # meia volta no círculo de cores
ZOOM_MAX = 0.35  # até 1,35× de zoom
SPLIT_MAX_UV = 0.03  # separação R/B em fração da textura
SHAKE_MAX_UV = 0.03
SHAKE_HZ = 13.0


@dataclass(frozen=True)
class FxUniforms:
    gain: float = 1.0
    hue: float = 0.0  # rad
    zoom: float = 1.0  # >1 aproxima
    split: float = 0.0  # uv
    shift: tuple[float, float] = (0.0, 0.0)  # uv
    invert: float = 0.0  # 0..1
    flash: float = 0.0  # 0..1 (mistura com branco)

    def is_neutral(self) -> bool:
        return self == NEUTRAL_FX


NEUTRAL_FX = FxUniforms()


def compute_fx(fx: Sequence[AudioFx], levels: Mapping[str, float], t: float) -> FxUniforms:
    """Níveis de áudio + lista de efeitos → uniforms. Efeitos do mesmo tipo somam."""
    acc = dict.fromkeys(("pulse", "hue", "zoom", "rgb_split", "strobe", "shake", "invert"), 0.0)
    for f in fx:
        if not f.enabled or f.amount <= 0:
            continue
        v = float(np.clip(levels.get(f.band, 0.0), 0.0, 1.0))
        acc[f.type] += f.amount * v
    if not any(acc.values()):
        return NEUTRAL_FX
    shake = min(acc["shake"], 1.0) * SHAKE_MAX_UV
    phase = 2 * math.pi * SHAKE_HZ * t
    return FxUniforms(
        gain=1.0 + min(acc["pulse"], 1.0) * PULSE_MAX_GAIN,
        hue=min(acc["hue"], 1.0) * HUE_MAX_RAD,
        zoom=1.0 + min(acc["zoom"], 1.0) * ZOOM_MAX,
        split=min(acc["rgb_split"], 1.0) * SPLIT_MAX_UV,
        shift=(shake * math.sin(phase), shake * math.cos(phase * 1.31)),
        invert=min(acc["invert"], 1.0),
        flash=min(acc["strobe"], 1.0),
    )


def fx_sample_uv(tu: np.ndarray, tv: np.ndarray, fx: FxUniforms) -> tuple[np.ndarray, np.ndarray]:
    """Coordenada de amostragem depois do zoom (em volta do centro) e do tremor."""
    su = np.clip((tu - 0.5) / fx.zoom + 0.5 + fx.shift[0], 0.0, 1.0)
    sv = np.clip((tv - 0.5) / fx.zoom + 0.5 + fx.shift[1], 0.0, 1.0)
    return su, sv


def hue_matrix(angle: float) -> np.ndarray:
    """Rotação de Rodrigues em torno do eixo cinza (1,1,1)/√3 — preserva o cinza."""
    c, s = math.cos(angle), math.sin(angle)
    k = 1.0 / math.sqrt(3.0)
    kx = np.array([[0, -k, k], [k, 0, -k], [-k, k, 0]], np.float64)
    kk = np.full((3, 3), k * k)
    return (c * np.eye(3) + s * kx + (1 - c) * kk).astype(np.float32)


def apply_color_fx(rgb: np.ndarray, fx: FxUniforms) -> np.ndarray:
    """Cor (``float32`` em [0,1], ``(..., 3)``) depois de ganho, matiz, inversão e flash."""
    c = np.asarray(rgb, np.float32) * fx.gain
    if fx.hue:
        c = c @ hue_matrix(fx.hue).T
    c = np.clip(c, 0.0, 1.0)
    c = c + (1.0 - 2.0 * c) * fx.invert
    return c + (1.0 - c) * fx.flash
