"""Mundo da interação: a parede projetada, as pessoas e para onde elas olham.

Unidades e eixos (iguais aos do canvas projetado):

- O mundo é o plano da parede: ``x ∈ [0, aspect]``, ``y ∈ [0, 1]`` (y para
  baixo), com 1 unidade = altura da área projetada. Assim distâncias valem igual
  nos dois eixos e a cena independe da resolução do projetor.
- Uma pessoa (``Player``) fica diante da parede: ``x`` é a posição dela ao longo
  da parede, ``distance`` o afastamento (mesma unidade), ``yaw`` a rotação da
  cabeça (0 = olhando reto para a parede, + = virada para a direita da parede,
  ±180° = de costas).

O olhar vira uma **região na parede**: o raio do olhar sai da cabeça, cruza a
parede em ``x + distance·tan(yaw)`` e o campo de visão (``fov``) abre um disco
em torno desse ponto. Algo está "sendo olhado" se cai dentro do disco *e* a
pessoa está de frente para a parede (|yaw| < 90°). De costas, nada é olhado —
é a mecânica dos fantasmas tímidos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

Vec = tuple[float, float]

# Além disso o ponto de olhar escaparia para o infinito (raio quase paralelo à parede).
MAX_YAW_FOR_GAZE = math.radians(80)


@dataclass
class Player:
    id: int = 0
    x: float = 0.5  # posição ao longo da parede (unidades do mundo)
    distance: float = 1.0  # afastamento da parede
    yaw: float = 0.0  # rad; 0 = de frente para a parede
    eye_y: float = 0.45  # altura do olhar na parede (0 = topo)
    tracked: bool = True  # sensor está vendo a pessoa?
    face_visible: Optional[bool] = None  # webcam: rosto detectado? (None = sensor não sabe)

    @property
    def facing_wall(self) -> bool:
        if not self.tracked:
            return False
        if self.face_visible is False:
            return False  # câmera na parede não vê o rosto ⇒ pessoa de costas
        return abs(_wrap(self.yaw)) < math.pi / 2

    @property
    def anchor(self) -> Vec:
        """Ponto da parede "na frente" da pessoa — o alvo de quem persegue."""
        return (self.x, self.eye_y)


@dataclass(frozen=True)
class Gaze:
    center: Vec
    radius: float
    active: bool  # False = de costas / não rastreado: não olha nada

    def sees(self, p: Vec) -> bool:
        return self.active and math.dist(p, self.center) <= self.radius


def gaze_of(player: Player, fov: float) -> Gaze:
    """Região da parede que a pessoa está olhando (disco aproximado)."""
    if not player.facing_wall:
        return Gaze(player.anchor, 0.0, False)
    yaw = max(-MAX_YAW_FOR_GAZE, min(MAX_YAW_FOR_GAZE, _wrap(player.yaw)))
    gx = player.x + player.distance * math.tan(yaw)
    # Olhando de lado, o cone cruza a parede mais longe e mais aberto.
    slant = player.distance / math.cos(yaw)
    radius = slant * math.tan(fov / 2)
    return Gaze((gx, player.eye_y), radius, True)


@dataclass
class WorldState:
    aspect: float = 16 / 9
    players: list[Player] = field(default_factory=list)

    def clamp(self, p: Vec, margin: float = 0.0) -> Vec:
        return (min(max(p[0], margin), self.aspect - margin), min(max(p[1], margin), 1.0 - margin))


def _wrap(a: float) -> float:
    """Ângulo em (-π, π]."""
    return (a + math.pi) % (2 * math.pi) - math.pi
