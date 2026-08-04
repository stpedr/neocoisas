"""Publicação via APIs oficiais das plataformas (pontos de extensão).

Nada de automação de evasão de detecção — apenas as APIs oficiais, dentro das
regras de cada rede. Ver [[auto-niche-engine]] / HANDOFF.md.
"""

from .factory import get_publisher

__all__ = ["get_publisher"]
