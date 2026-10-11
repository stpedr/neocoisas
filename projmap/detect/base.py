"""Contrato dos detectores de superfície."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol

import numpy as np

Point = tuple[float, float]


@dataclass
class Candidate:
    """Uma superfície sugerida, em coordenadas **normalizadas** da foto ([0,1]).

    ``quad`` (TL, TR, BR, BL) é o que vira superfície; ``polygon`` é o contorno
    simplificado da região (guardado em ``Surface.polygon_src``).
    """

    quad: list[Point]
    polygon: list[Point]
    area: float  # fração da foto
    score: float  # 0..1: quão bem o quad cobre a região (retangularidade)
    label: str = ""
    color: tuple[int, int, int] = (128, 128, 128)  # cor média (RGB), ajuda a reconhecer na lista
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["quad"] = [list(p) for p in self.quad]
        d["polygon"] = [list(p) for p in self.polygon]
        d["color"] = list(self.color)
        return d


class Detector(Protocol):
    name: str

    def detect(self, bgr: np.ndarray, sensitivity: float = 0.5, max_candidates: int = 12) -> list[Candidate]:
        """``sensitivity`` 0..1: mais alto = mais regiões, menores e mais detalhadas."""
        ...
