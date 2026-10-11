"""Especificação de cena interativa (o que o NLP produz e a UI edita).

A IA **não escreve código**: ela escolhe e parametriza peças prontas
(sprites e comportamentos) dentro deste esquema. Tudo é validado pelo pydantic
antes de rodar — um LLM que "invente" um comportamento recebe erro e é corrigido
(ou cai no parser por palavras-chave).

Comportamentos disponíveis (combináveis por grupo):

==================== ========================================================
``chase_player``     vai na direção da pessoa (ponto da parede à frente dela)
``flee_player``      afasta-se da pessoa quando ela chega perto
``wander``           passeio aleatório suave
``seek_gaze``        vai para onde a pessoa está olhando (ex.: vaga-lumes)
``freeze_when_watched`` para quando está na região do olhar; ``shy`` = cobre o rosto
==================== ========================================================
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

Sprite = Literal["ghost", "orb", "firefly", "fish"]
Spawn = Literal["edges", "random", "center", "far_from_player"]
Action = Literal["flash", "reset", "shake"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChasePlayer(_M):
    type: Literal["chase_player"] = "chase_player"
    speed: float = Field(0.12, gt=0, le=3, description="unidades da parede por segundo")


class FleePlayer(_M):
    type: Literal["flee_player"] = "flee_player"
    speed: float = Field(0.25, gt=0, le=3)
    radius: float = Field(0.45, gt=0, le=3, description="só foge se a pessoa estiver mais perto que isso")


class Wander(_M):
    type: Literal["wander"] = "wander"
    speed: float = Field(0.08, gt=0, le=3)
    turn: float = Field(2.0, ge=0, le=20, description="quão rápido muda de direção (rad/s)")


class SeekGaze(_M):
    type: Literal["seek_gaze"] = "seek_gaze"
    speed: float = Field(0.3, gt=0, le=3)


class FreezeWhenWatched(_M):
    type: Literal["freeze_when_watched"] = "freeze_when_watched"
    shy: bool = Field(True, description="cobre o rosto enquanto é olhado")


Behavior = Annotated[
    Union[ChasePlayer, FleePlayer, Wander, SeekGaze, FreezeWhenWatched], Field(discriminator="type")
]


class EntityGroup(_M):
    name: str = Field("grupo", max_length=40)
    sprite: Sprite = "orb"
    count: int = Field(3, ge=1, le=200)
    color: tuple[int, int, int] = (235, 240, 255)
    size: float = Field(0.08, gt=0.005, le=0.6, description="diâmetro, em altura da parede")
    spawn: Spawn = "edges"
    behaviors: list[Behavior] = Field(default_factory=list)


class SceneSpec(_M):
    version: int = 1
    title: str = Field("Cena", max_length=80)
    description: str = Field("", max_length=500)
    aspect: float = Field(16 / 9, gt=0.2, le=10)
    background: tuple[int, int, int] = (0, 0, 0)
    fov_deg: float = Field(60.0, gt=5, le=170, description="campo de visão que conta como 'olhando'")
    catch_radius: float = Field(0.07, gt=0, le=1, description="distância que conta como 'pegou'")
    on_caught: list[Action] = Field(default_factory=lambda: ["flash", "reset"])
    groups: list[EntityGroup] = Field(default_factory=list, min_length=1, max_length=8)
    seed: int = 0


# --------------------------------------------------------------------- presets
# Mecânica inspirada no clássico "fantasma que para quando você olha" (o
# personagem é da Nintendo; aqui o design do fantasma é original).
PRESETS: dict[str, SceneSpec] = {
    "fantasmas-timidos": SceneSpec(
        title="Fantasmas tímidos",
        description="Param e cobrem o rosto quando você olha; quando você vira de costas, vêm te buscar.",
        on_caught=["flash", "reset"],
        groups=[
            EntityGroup(
                name="fantasmas", sprite="ghost", count=5, color=(240, 244, 255), size=0.16, spawn="edges",
                behaviors=[ChasePlayer(speed=0.12), FreezeWhenWatched(shy=True)],
            )
        ],
    ),
    "vaga-lumes": SceneSpec(
        title="Vaga-lumes do olhar",
        description="Vaga-lumes vagam e se juntam onde você estiver olhando.",
        on_caught=[],
        groups=[
            EntityGroup(name="vaga-lumes", sprite="firefly", count=40, color=(255, 230, 120), size=0.03,
                        spawn="random", behaviors=[Wander(speed=0.06, turn=4), SeekGaze(speed=0.12)])
        ],
    ),
    "cardume": SceneSpec(
        title="Cardume assustado",
        description="Peixes nadam pela parede e fogem quando alguém chega perto.",
        background=(0, 8, 20),
        on_caught=[],
        groups=[
            EntityGroup(name="peixes", sprite="fish", count=18, color=(90, 200, 255), size=0.07,
                        spawn="random", behaviors=[Wander(speed=0.1, turn=1.5), FleePlayer(speed=0.35, radius=0.5)])
        ],
    ),
}
