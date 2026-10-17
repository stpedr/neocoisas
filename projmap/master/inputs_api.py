"""Rotas das entradas ao vivo (vídeo/áudio), da saída e do mapeamento rápido.

Comandos pequenos, no estilo do remote (F6), usados pelo editor, pelo celular
e pelo servidor MCP (``projmap/mcp_server``):

- ``GET  /api/inputs`` — câmeras/placas de captura e dispositivos de áudio;
- ``GET  /api/inputs/audio`` — níveis ao vivo da entrada de áudio dos efeitos;
- ``PATCH /api/audio`` — escolhe a entrada de áudio (``project.audio``);
- ``POST /api/surfaces`` — cria uma superfície (opcionalmente em tela cheia);
- ``POST /api/surfaces/{id}/fullscreen`` — mapeia a superfície na saída inteira;
- ``GET  /api/nodes/{id}/snapshot`` — PNG do que a janela do projetor está mostrando.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..core.geometry import rect_quad
from ..core.project import AudioInput, Point, Project, SourceSpec, Surface, Warp, new_id
from ..core.state import ProjectState
from ..node.tap import OutputTap


class AudioPatch(BaseModel):
    device: Optional[str] = Field(None, min_length=1, max_length=128)
    gain: Optional[float] = Field(None, ge=0.0, le=8.0, allow_inf_nan=False)


class SurfaceCreate(BaseModel):
    node_id: str = Field(..., max_length=63)
    label: str = Field("", max_length=80)
    fullscreen: bool = True
    source: Optional[SourceSpec] = None


def _points(quad: list) -> list[Point]:
    return [(float(x), float(y)) for x, y in quad]


def full_quad(project: Project, node_id: str) -> list[Point]:
    out = project.node(node_id).output
    return _points(rect_quad(0, 0, out.width, out.height))


def create_router(state: ProjectState, tap: Optional[OutputTap] = None) -> APIRouter:
    r = APIRouter()

    def _payload() -> dict:
        rev, project = state.snapshot()
        return {"revision": rev, "project": project.model_dump(mode="json")}

    def _surface(p: Project, sid: str) -> Surface:
        for s in p.surfaces:
            if s.id == sid:
                return s
        raise HTTPException(404, f"superfície '{sid}' não existe")

    @r.get("/api/inputs")
    def inputs() -> dict[str, Any]:
        from ..inputs.audio import bus, list_audio_devices
        from ..inputs.video import active_captures, list_video_devices

        return {"video": list_video_devices(), "audio": list_audio_devices(),
                "captures": active_captures(), "audio_bus": bus().status()}

    @r.get("/api/inputs/audio")
    def audio_levels() -> dict[str, Any]:
        from ..inputs.audio import bus
        from ..inputs.video import active_captures

        return {**bus().status(), "captures": active_captures()}

    @r.patch("/api/audio")
    def patch_audio(body: AudioPatch) -> dict:
        def apply(p: Project) -> Project:
            changes = body.model_dump(exclude_none=True)
            p.audio = AudioInput.model_validate({**p.audio.model_dump(), **changes})
            return p

        state.update(apply)
        return _payload()

    @r.post("/api/surfaces")
    def create_surface(body: SurfaceCreate) -> dict:
        created: dict[str, str] = {}

        def apply(p: Project) -> Project:
            try:
                quad = full_quad(p, body.node_id)
            except KeyError:
                raise HTTPException(404, f"nó '{body.node_id}' não existe") from None
            if not body.fullscreen:  # meio da tela, para o operador ajustar
                out = p.node(body.node_id).output
                quad = _points(rect_quad(out.width / 4, out.height / 4, out.width / 2, out.height / 2))
            sid = new_id("superficie")
            z = max((s.z for s in p.surfaces if s.node_id == body.node_id), default=-1) + 1
            p.surfaces.append(Surface(id=sid, label=body.label or f"Superfície {len(p.surfaces) + 1}",
                                      node_id=body.node_id, z=z, warp=Warp(base=quad),
                                      source=body.source or SourceSpec(kind="test")))
            created["id"] = sid
            return p

        try:
            state.update(apply)
        except ValueError as exc:
            raise HTTPException(422, [str(exc)]) from exc
        return {**_payload(), "surface_id": created["id"]}

    @r.post("/api/surfaces/{surface_id}/fullscreen")
    def fullscreen(surface_id: str) -> dict:
        def apply(p: Project) -> Project:
            surf = _surface(p, surface_id)
            surf.warp = Warp(base=full_quad(p, surf.node_id))
            return p

        state.update(apply)
        return _payload()

    @r.get("/api/nodes/{node_id}/snapshot")
    def snapshot(node_id: str, max_width: int = Query(960, ge=16, le=3840)) -> Response:
        _, project = state.snapshot()
        try:
            project.node(node_id)
        except KeyError:
            raise HTTPException(404, f"nó '{node_id}' não existe") from None
        if tap is None or not tap.attached:
            raise HTTPException(503, ["sem janela de saída neste mestre (rodando com --no-output?)"])
        png = tap.request(max_width=max_width)
        if png is None:
            raise HTTPException(504, ["a janela de saída não respondeu a tempo"])
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})

    return r
