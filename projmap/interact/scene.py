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

Opcional, ``star``: estrela de poder em senoide; pegá-la deixa a pessoa
invencível e os fantasmas que ela tocar são derrotados (voltam depois).
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

Sprite = Literal["ghost", "orb", "firefly", "fish", "image"]

# Imagens das cenas (fundo e sprites) só vêm daqui: uma cena gerada pela IA ou
# enviada pela API não pode apontar para arquivos arbitrários do disco.
ASSET_DIR = Path.home() / ".projmap" / "scenes"


def asset_path(rel: str) -> Path:
    return ASSET_DIR / Path(*PurePosixPath(rel).parts)


def _check_asset(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    p = PurePosixPath(v.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or ":" in v or not v.strip():
        raise ValueError("imagem deve ser um caminho relativo a ~/.projmap/scenes (ex.: boo/castelo.png)")
    if p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        raise ValueError("imagem deve ser PNG/JPG/WebP/BMP")
    return p.as_posix()
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


class Skin(_M):
    """Aparência de um sprite ``image``: a imagem normal e a de quando é olhado."""

    image: str
    shy_image: Optional[str] = Field(None, description="imagem quando olhado (ex.: tampando o rosto); vazio = a mesma")

    _img = field_validator("image", "shy_image")(classmethod(lambda cls, v: _check_asset(v)))


class EntityGroup(_M):
    name: str = Field("grupo", max_length=40)
    sprite: Sprite = "orb"
    skins: list[Skin] = Field(default_factory=list, max_length=32,
                              description="sprite 'image': cada entidade usa uma (em rodízio)")
    shy_alpha: float = Field(0.35, ge=0.0, le=1.0, description="opacidade enquanto é olhado (1 = opaco)")
    pixelated: bool = Field(True, description="amplia sem suavizar (pixel art fica nítida)")
    count: int = Field(3, ge=1, le=200)
    color: tuple[int, int, int] = (235, 240, 255)
    size: float = Field(0.08, gt=0.005, le=0.6, description="diâmetro, em altura da parede")
    spawn: Spawn = "edges"
    behaviors: list[Behavior] = Field(default_factory=list)


class StarSpec(_M):
    """Estrela de poder: atravessa a parede em senoide; quem a pega fica invencível
    por ``duration_s`` e derrota os fantasmas que tocar (eles fogem enquanto isso)."""

    image: Optional[str] = Field(None, description="PNG em ~/.projmap/scenes; vazio = estrela desenhada")
    size: float = Field(0.13, gt=0.01, le=0.5, description="diâmetro, em altura da parede")
    speed: float = Field(0.22, gt=0.01, le=2, description="avanço horizontal (unidades/s)")
    amplitude: float = Field(0.2, ge=0, le=0.5, description="altura da onda")
    frequency: float = Field(0.7, gt=0, le=5, description="ondas por segundo")
    interval_s: float = Field(10.0, ge=1, le=600, description="espera entre uma estrela e outra")
    duration_s: float = Field(8.0, ge=1, le=60, description="tempo de invencibilidade")
    catch_radius: float = Field(0.14, gt=0, le=1, description="distância (na parede) que conta como pegar")
    respawn_s: float = Field(6.0, ge=0.5, le=120, description="quanto tempo um fantasma derrotado demora a voltar")
    flee_speed: float = Field(0.3, gt=0, le=3, description="velocidade dos fantasmas fugindo")

    _img = field_validator("image")(classmethod(lambda cls, v: _check_asset(v)))


class SceneSpec(_M):
    version: int = 1
    title: str = Field("Cena", max_length=80)
    description: str = Field("", max_length=500)
    aspect: float = Field(16 / 9, gt=0.2, le=10)
    background: tuple[int, int, int] = (0, 0, 0)
    background_image: Optional[str] = Field(None, description="relativo a ~/.projmap/scenes")
    background_fit: Literal["cover", "contain", "stretch"] = "cover"
    fov_deg: float = Field(60.0, gt=5, le=170, description="campo de visão que conta como 'olhando'")
    catch_radius: float = Field(0.07, gt=0, le=1, description="distância que conta como 'pegou'")
    on_caught: list[Action] = Field(default_factory=lambda: ["flash", "reset"])
    groups: list[EntityGroup] = Field(default_factory=list, min_length=1, max_length=8)
    star: Optional[StarSpec] = Field(None, description="estrela de poder (opcional)")
    seed: int = 0

    _bg = field_validator("background_image")(classmethod(lambda cls, v: _check_asset(v)))


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
    # Arte do usuário (fica em ~/.projmap/scenes/boo, fora do repositório).
    # Sem os arquivos, cai no fantasma desenhado e no fundo liso.
    "castelo-boo": SceneSpec(
        title="Castelo dos Boos",
        description="Boos vivos te perseguem quando você vira de costas; quando você olha, ficam com vergonha e translúcidos.",
        background=(14, 20, 38),
        background_image="boo/castelo.png",
        on_caught=["flash", "reset"],
        groups=[
            EntityGroup(
                name="boos", sprite="image", count=6, size=0.17, spawn="edges", shy_alpha=0.3,
                skins=[Skin(image="boo/boo_04.png", shy_image="boo/boo_08.png"),
                       Skin(image="boo/boo_10.png", shy_image="boo/boo_09.png"),
                       Skin(image="boo/boo_06.png", shy_image="boo/boo_08.png"),
                       Skin(image="boo/boo_07.png", shy_image="boo/boo_08.png"),
                       Skin(image="boo/boo_05.png", shy_image="boo/boo_08.png")],
                behaviors=[ChasePlayer(speed=0.12), FreezeWhenWatched(shy=True)],
            )
        ],
        star=StarSpec(image="boo/estrela.png"),
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
