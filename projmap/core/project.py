"""Modelo de dados do projeto (``project.json``, esquema versionado).

O JSON é a fonte de verdade em disco e na rede. Pydantic valida tudo na
entrada: um quad cruzado ou uma superfície apontando para um nó inexistente
são recusados com mensagem clara, antes de chegar ao renderer.

Evolução do esquema: ``version`` sobe a cada mudança incompatível e
:func:`migrate` converte documentos antigos. Campos novos *opcionais* não
mudam a versão.
"""

from __future__ import annotations

import re
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .geometry import rect_quad, validate_quad

SCHEMA_VERSION = 1

Point = tuple[float, float]

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

MediaKind = Literal["video", "image", "gif"]
SourceKind = Literal["none", "video", "image", "gif", "color", "test", "interactive"]
Pattern = Literal["none", "white", "grid", "edges", "black"]


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class _Model(BaseModel):
    # Campos desconhecidos são rejeitados: erro de digitação no JSON vira erro, não silêncio.
    model_config = ConfigDict(extra="forbid")


class MediaItem(_Model):
    """Mídia endereçada por conteúdo: o arquivo vive em ``media/<sha256><ext>``."""

    sha256: str
    filename: str = Field(description="nome original, só para exibição")
    ext: str
    kind: MediaKind
    size_bytes: int = 0

    @field_validator("sha256")
    @classmethod
    def _sha(cls, v: str) -> str:
        if not _SHA_RE.match(v):
            raise ValueError("sha256 inválido")
        return v

    @field_validator("ext")
    @classmethod
    def _ext(cls, v: str) -> str:
        if not re.match(r"^\.[a-z0-9]{1,5}$", v):
            raise ValueError("extensão inválida")
        return v


class ColorAdjust(_Model):
    """Ajustes de imagem (todos neutros no padrão). Espelho exato em
    ``projmap/mapping/color.py`` (CPU) e ``node/shaders/surface.frag`` (GPU).

    Ordem: contraste → brilho → saturação → temperatura → gama.
    """

    brightness: float = Field(1.0, ge=0.0, le=3.0, description="ganho (1 = original; >1 clareia, pode estourar o branco)")
    contrast: float = Field(1.0, ge=0.0, le=3.0, description="em torno do cinza médio")
    saturation: float = Field(1.0, ge=0.0, le=3.0, description="0 = preto e branco")
    gamma: float = Field(1.0, ge=0.3, le=3.0, description=">1 clareia os tons escuros sem estourar o branco")
    temperature: float = Field(0.0, ge=-1.0, le=1.0, description="-1 frio (azulado) … +1 quente (amarelado)")

    def is_neutral(self) -> bool:
        return self == ColorAdjust()


class Output(_Model):
    """Saída de um nó (um projetor)."""

    width: int = Field(1920, ge=16, le=16384)
    height: int = Field(1080, ge=16, le=16384)
    intensity: float = Field(1.0, ge=0.0, le=1.0, description="dimmer master do nó")
    blackout: bool = False
    pattern: Pattern = Field("none", description="padrão de teste/alinhamento em tela cheia")
    show_outlines: bool = Field(False, description="desenha contornos e cantos sobre o conteúdo")
    latency_ms: float = Field(0.0, ge=0.0, le=1000.0, description="input lag do projetor (F2/F4)")
    color: ColorAdjust = Field(default_factory=ColorAdjust, description="ajuste de imagem do projetor inteiro")
    flip_h: bool = Field(False, description="espelha na horizontal (retroprojeção: projetor atrás da tela)")
    flip_v: bool = Field(False, description="inverte na vertical (projetor de teto, de cabeça para baixo)")


class Node(_Model):
    """Um projetor + o computador que o alimenta."""

    id: str
    name: str = ""
    output: Output = Field(default_factory=Output)
    photo: Optional[str] = Field(None, description="caminho relativo da foto tirada da posição do projetor")
    # Onde o quadro branco inteiro do projetor aparece na foto (TL, TR, BR, BL), em
    # coordenadas normalizadas [0,1] da foto. Liga foto ↔ projetor por homografia.
    photo_boundary: list[Point] = Field(default_factory=lambda: [tuple(p) for p in rect_quad(0, 0, 1, 1)])

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError("id deve ser minúsculo, [a-z0-9_-], até 63 caracteres")
        return v

    @field_validator("photo_boundary")
    @classmethod
    def _boundary(cls, v: list[Point]) -> list[Point]:
        err = validate_quad(v, min_area=1e-4)
        if err:
            raise ValueError(f"photo_boundary: {err}")
        return v


class SourceSpec(_Model):
    """O que uma superfície mostra. Cada superfície tem a sua fonte (requisito 5)."""

    kind: SourceKind = "none"
    media: Optional[str] = Field(None, description="sha256 de um item de mídia")
    color: tuple[int, int, int] = (255, 255, 255)
    fit: Literal["stretch", "cover", "contain"] = "stretch"
    loop: bool = True
    speed: float = Field(1.0, gt=0.0, le=16.0)
    offset_s: float = Field(0.0, description="deslocamento de tempo da fonte")

    @model_validator(mode="after")
    def _media_required(self) -> "SourceSpec":
        if self.kind in ("video", "image", "gif") and not self.media:
            raise ValueError(f"fonte '{self.kind}' exige 'media'")
        return self


class Warp(_Model):
    """Warp da superfície no espaço do projetor.

    F1: só a homografia base (``base`` = 4 cantos em px). Correções de grade e
    Bézier (F1+/F4) entram como *offsets* sobre esta base — ver BLUEPRINT E1.
    """

    type: Literal["homography"] = "homography"
    base: list[Point]

    @field_validator("base")
    @classmethod
    def _quad(cls, v: list[Point]) -> list[Point]:
        err = validate_quad(v)
        if err:
            raise ValueError(err)
        return v


class Layer(_Model):
    """Mídia extra dentro de uma superfície (F9), desenhada por cima do fundo (``source``).

    ``rect`` = ``[x, y, w, h]`` no espaço uv da superfície (0..1 é a superfície
    inteira). Pode passar das bordas: o que sai fica recortado pela superfície.
    """

    id: str
    label: str = ""
    visible: bool = True
    source: SourceSpec
    rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    opacity: float = Field(1.0, ge=0.0, le=1.0)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError("id deve ser minúsculo, [a-z0-9_-], até 63 caracteres")
        return v

    @field_validator("rect")
    @classmethod
    def _rect(cls, v: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x, y, w, h = v
        if not (w > 1e-4 and h > 1e-4):
            raise ValueError("rect: largura e altura devem ser positivas")
        if max(abs(x), abs(y), w, h) > 100:
            raise ValueError("rect: valores fora do razoável (|x|,|y|,w,h ≤ 100)")
        return v


class Surface(_Model):
    id: str
    label: str = ""
    node_id: str
    z: int = 0
    visible: bool = True
    polygon_src: Optional[list[Point]] = Field(None, description="polígono na foto (normalizado), p/ F3")
    warp: Warp
    source: SourceSpec = Field(default_factory=SourceSpec)
    opacity: float = Field(1.0, ge=0.0, le=1.0)
    feather: float = Field(0.0, ge=0.0, le=0.5, description="borda suave, em fração do uv")
    blend_mode: Literal["normal", "add", "multiply"] = "normal"
    layers: list[Layer] = Field(default_factory=list, description="mídias extras por cima do fundo (F9)")
    color: ColorAdjust = Field(default_factory=ColorAdjust, description="ajuste de imagem só desta superfície")

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError("id deve ser minúsculo, [a-z0-9_-], até 63 caracteres")
        return v


class SurfaceLook(_Model):
    """O que um look guarda de cada superfície: só o "conteúdo", nunca a geometria."""

    visible: bool = True
    opacity: float = Field(1.0, ge=0.0, le=1.0)
    source: SourceSpec = Field(default_factory=SourceSpec)
    layers: Optional[list[Layer]] = Field(None, description="None = look antigo: não mexe nas camadas")


class Look(_Model):
    """Cena salva (cue) do remote (F6): recall troca fontes/visibilidade de uma vez.

    Pode citar superfícies ou mídias que já não existem; o recall as ignora.
    """

    id: str
    name: str = ""
    surfaces: dict[str, SurfaceLook] = Field(default_factory=dict)


class Project(_Model):
    version: int = SCHEMA_VERSION
    name: str = "Novo projeto"
    fps: int = Field(30, ge=1, le=240)
    nodes: list[Node] = Field(default_factory=list)
    surfaces: list[Surface] = Field(default_factory=list)
    media: dict[str, MediaItem] = Field(default_factory=dict)
    looks: list[Look] = Field(default_factory=list)

    @model_validator(mode="after")
    def _references(self) -> "Project":
        node_ids = [n.id for n in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("ids de nó duplicados")
        surf_ids = [s.id for s in self.surfaces]
        if len(set(surf_ids)) != len(surf_ids):
            raise ValueError("ids de superfície duplicados")
        for sha, item in self.media.items():
            if sha != item.sha256:
                raise ValueError(f"chave de mídia {sha[:8]}… diverge do sha256 do item")
        known = set(node_ids)
        for s in self.surfaces:
            if s.node_id not in known:
                raise ValueError(f"superfície '{s.id}' aponta para nó inexistente '{s.node_id}'")
            if s.source.media and s.source.media not in self.media:
                raise ValueError(f"superfície '{s.id}' usa mídia desconhecida {s.source.media[:8]}…")
            if s.source.media and s.source.kind != self.media[s.source.media].kind:
                raise ValueError(
                    f"superfície '{s.id}': fonte '{s.source.kind}' não combina com mídia "
                    f"'{self.media[s.source.media].kind}'"
                )
            layer_ids = [layer.id for layer in s.layers]
            if len(set(layer_ids)) != len(layer_ids):
                raise ValueError(f"superfície '{s.id}': ids de camada duplicados")
            for layer in s.layers:
                src = layer.source
                if src.media and src.media not in self.media:
                    raise ValueError(f"superfície '{s.id}', camada '{layer.id}': mídia desconhecida {src.media[:8]}…")
                if src.media and src.kind != self.media[src.media].kind:
                    raise ValueError(f"superfície '{s.id}', camada '{layer.id}': fonte '{src.kind}' não combina com a mídia")
        return self

    def node(self, node_id: str) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)

    def surfaces_for(self, node_id: str) -> list[Surface]:
        """Superfícies visíveis do nó, em ordem de desenho (z crescente, estável)."""
        items = [s for s in self.surfaces if s.node_id == node_id and s.visible]
        return sorted(items, key=lambda s: s.z)


def default_project(name: str = "Novo projeto") -> Project:
    """Projeto inicial: um projetor 1080p, sem superfícies."""
    return Project(name=name, nodes=[Node(id="proj-1", name="Projetor 1")])


def migrate(data: dict) -> dict:
    """Converte um ``project.json`` antigo para :data:`SCHEMA_VERSION`."""
    version = int(data.get("version", 1))
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"projeto na versão {version}, mais nova que a suportada ({SCHEMA_VERSION}); atualize o ProjMap"
        )
    # v1 é a primeira versão: nada a migrar ainda.
    data["version"] = SCHEMA_VERSION
    return data


def parse_project(data: dict) -> Project:
    return Project.model_validate(migrate(dict(data)))
