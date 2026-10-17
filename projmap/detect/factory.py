"""Factory de detectores (padrão do repo: contrato + seleção por nome/config)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Detector

DETECTORS = ("classic",)


def get_detector(name: str = "classic") -> Detector:
    name = (name or "classic").lower()
    if name == "classic":
        from .classic import ClassicDetector

        return ClassicDetector()
    raise ValueError(f"detector desconhecido: '{name}' (disponíveis: {', '.join(DETECTORS)})")


def detect_from_photo(
    photo_path: Path,
    detector_name: str = "classic",
    sensitivity: float = 0.5,
    max_candidates: int = 12,
) -> dict[str, Any]:
    """Lê a foto do nó e devolve o nome do detector e a lista de candidatos serializados."""
    import cv2
    import numpy as np

    bgr = cv2.imdecode(np.fromfile(str(photo_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("foto ilegível")
    detector = get_detector(detector_name)
    cands = detector.detect(bgr, sensitivity=sensitivity, max_candidates=max_candidates)
    return {"detector": detector.name, "candidates": [c.to_dict() for c in cands]}
