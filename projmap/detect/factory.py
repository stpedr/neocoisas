"""Factory de detectores (padrão do repo: contrato + seleção por nome/config)."""

from __future__ import annotations

from .base import Detector

DETECTORS = ("classic",)


def get_detector(name: str = "classic") -> Detector:
    name = (name or "classic").lower()
    if name == "classic":
        from .classic import ClassicDetector

        return ClassicDetector()
    raise ValueError(f"detector desconhecido: '{name}' (disponíveis: {', '.join(DETECTORS)})")
