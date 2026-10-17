"""Dinâmica de segunda ordem — tradução de ``DinamicaSegundaOrdem.h`` do
visual_frames.

Segue um alvo como um sistema massa-mola-amortecedor (t3ssel8r, "Giving
Personality to Procedural Animations using Math"):

- ``f``: frequência natural (Hz) — quão rápido responde;
- ``z``: amortecimento — < 1 balança e passa do ponto, 1 crítico, > 1 lento;
- ``r``: resposta inicial — 0 começa devagar, 1 imediato, > 1 antecipa, < 0 recua.

Dá inércia, follow-through e acomodação, coisa que uma média exponencial (sem
massa) não dá. Funciona com escalar (``float``) ou vetor (``np.ndarray``): as
operações são as mesmas nos dois casos.
"""

from __future__ import annotations

import math

import numpy as np

def aproximar(atual: float, alvo: float, dt: float, tau: float) -> float:
    """Média exponencial com constante de tempo ``tau`` (o ``aproximar`` do C++)."""
    return atual + (alvo - atual) * (1.0 - math.exp(-dt / tau)) if dt > 0 else atual


def smoothstep(e0: float, e1: float, x: float) -> float:
    """``glm::smoothstep``."""
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0))) if e1 != e0 else float(x >= e1)
    return t * t * (3.0 - 2.0 * t)


def normalizar(v: np.ndarray, padrao: np.ndarray | None = None) -> np.ndarray:
    """``glm::normalize`` com guarda para vetor nulo."""
    n = float(np.hypot(v[0], v[1]))
    if n > 1e-6:
        return v / n
    return padrao if padrao is not None else np.array([1.0, 0.0], np.float32)


class SecondOrder:
    def __init__(self, f: float, z: float, r: float, initial: "float | np.ndarray" = 0.0):
        self.k1 = z / (math.pi * f)
        self.k2 = 1.0 / ((2.0 * math.pi * f) ** 2)
        self.k3 = r * z / (2.0 * math.pi * f)
        self.reset(initial)

    def reset(self, value: "float | np.ndarray") -> None:
        # Cópia: um np.ndarray do chamador não pode virar o estado interno.
        self._prev_target = np.array(value, np.float32) if isinstance(value, np.ndarray) else float(value)
        self.y = np.array(value, np.float32) if isinstance(value, np.ndarray) else float(value)
        self.velocity = self.y * 0.0

    def update(self, dt: float, target: "float | np.ndarray") -> "float | np.ndarray":
        if dt <= 0:
            return self.y
        target_velocity = (target - self._prev_target) / dt
        self._prev_target = np.array(target, np.float32) if isinstance(target, np.ndarray) else float(target)
        # k2 mínimo para manter a integração estável com dt grande.
        k2 = max(self.k2, dt * dt / 2.0 + dt * self.k1 / 2.0, dt * self.k1)
        self.y = self.y + self.velocity * dt
        self.velocity = self.velocity + (target + target_velocity * self.k3
                                         - self.y - self.velocity * self.k1) * (dt / k2)
        return self.y
