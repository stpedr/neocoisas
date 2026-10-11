"""Detecção de superfícies a partir da foto (F3).

Contrato + factory, como o resto do repo: ``get_detector("classic")`` devolve um
:class:`~projmap.detect.base.Detector`. O ``classic`` usa só OpenCV (sem torch,
roda no CI). O ``sam2`` entra depois pelo mesmo contrato.
"""

from .base import Candidate, Detector
from .factory import get_detector

__all__ = ["Candidate", "Detector", "get_detector"]
