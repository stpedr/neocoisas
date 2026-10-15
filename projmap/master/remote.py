"""Rotas do remote no celular (F6): comandos pequenos e idempotentes.

O editor manda o projeto inteiro (``PUT /api/project``); o celular não. Numa
rede Wi-Fi instável um PUT do documento inteiro atropelaria edições do editor
feitas ao mesmo tempo. Aqui cada comando mexe só no que precisa:

- ``PATCH /api/surfaces/{id}`` — visibilidade, opacidade e fonte;
- ``/api/looks`` — salvar/recuperar/apagar cenas (cues);
- ``GET /api/remote/pair`` — URL + token + QR (SVG) para parear (só no próprio mestre).

Blackout, dimmer e padrões de teste usam ``PATCH /api/nodes/{id}/output``, que
já existe.
"""

from __future__ import annotations

import socket
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from ..core.project import ColorAdjust, Look, Project, SourceSpec, SurfaceLook, new_id
from ..core.state import ProjectState
from .auth import is_loopback


class SurfacePatch(BaseModel):
    visible: Optional[bool] = None
    opacity: Optional[float] = Field(None, ge=0.0, le=1.0)
    source: Optional[dict[str, Any]] = None
    color: Optional[ColorAdjust] = None  # preset de imagem aplicado na superfície


class LookCreate(BaseModel):
    name: str = Field("", max_length=80)


def lan_ip() -> str:
    """IP desta máquina na LAN (o que o celular deve usar). Não envia pacotes."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def remote_url(host: str, port: int, token: Optional[str]) -> str:
    if host in ("0.0.0.0", "::", "127.0.0.1", "localhost"):
        host = lan_ip() if host in ("0.0.0.0", "::") else "localhost"
    url = f"http://{host}:{port}/remote/"
    return f"{url}#t={token}" if token else url


def qr_svg(text: str) -> Optional[str]:
    """QR em SVG (``segno``, opcional). ``None`` se a lib não estiver instalada."""
    try:
        import segno
    except ImportError:
        return None
    return segno.make(text, error="m").svg_inline(scale=6, border=2, dark="#000", light="#fff")


def recall_look(project: Project, look: Look) -> list[str]:
    """Aplica o look ao projeto (in place). Devolve o que foi ignorado e por quê."""
    skipped = []
    by_id = {s.id: s for s in project.surfaces}
    for sid, saved in look.surfaces.items():
        surf = by_id.get(sid)
        if surf is None:
            skipped.append(f"{sid}: superfície não existe mais")
            continue
        src = saved.source
        if src.media and src.media not in project.media:
            skipped.append(f"{sid}: mídia removida")
            continue
        surf.visible = saved.visible
        surf.opacity = saved.opacity
        surf.source = src.model_copy(deep=True)
        if saved.layers is not None:
            keep = [layer for layer in saved.layers if not layer.source.media or layer.source.media in project.media]
            if len(keep) != len(saved.layers):
                skipped.append(f"{sid}: {len(saved.layers) - len(keep)} camada(s) com mídia removida")
            surf.layers = [layer.model_copy(deep=True) for layer in keep]
    return skipped


def create_router(state: ProjectState, host: str = "127.0.0.1", port: int = 8100,
                  token: Optional[str] = None) -> APIRouter:
    r = APIRouter()

    def _payload() -> dict:
        rev, project = state.snapshot()
        return {"revision": rev, "project": project.model_dump(mode="json")}

    def _surface(p: Project, sid: str):
        for s in p.surfaces:
            if s.id == sid:
                return s
        raise HTTPException(404, f"superfície '{sid}' não existe")

    def _look(p: Project, lid: str) -> Look:
        for lk in p.looks:
            if lk.id == lid:
                return lk
        raise HTTPException(404, f"look '{lid}' não existe")

    @r.patch("/api/surfaces/{surface_id}")
    def patch_surface(surface_id: str, body: SurfacePatch) -> dict:
        def apply(p: Project) -> Project:
            surf = _surface(p, surface_id)
            if body.visible is not None:
                surf.visible = body.visible
            if body.opacity is not None:
                surf.opacity = body.opacity
            if body.source is not None:
                surf.source = SourceSpec.model_validate({**surf.source.model_dump(), **body.source})
            if body.color is not None:
                surf.color = body.color
            return p

        try:
            state.update(apply)
        except ValidationError:
            raise
        except ValueError as exc:  # referência inválida (mídia inexistente, tipo errado)
            raise HTTPException(422, [str(exc)]) from exc
        return _payload()

    @r.post("/api/looks")
    def save_look(body: LookCreate) -> dict:
        def apply(p: Project) -> Project:
            look = Look(
                id=new_id("look"),
                name=body.name.strip() or f"Look {len(p.looks) + 1}",
                surfaces={s.id: SurfaceLook(visible=s.visible, opacity=s.opacity,
                                            source=s.source.model_copy(deep=True),
                                            layers=[layer.model_copy(deep=True) for layer in s.layers])
                          for s in p.surfaces},
            )
            p.looks.append(look)
            return p

        state.update(apply)
        return _payload()

    @r.post("/api/looks/{look_id}/recall")
    def recall(look_id: str) -> dict:
        skipped: list[str] = []

        def apply(p: Project) -> Project:
            skipped.extend(recall_look(p, _look(p, look_id)))
            return p

        state.update(apply)
        return {**_payload(), "skipped": skipped}

    @r.delete("/api/looks/{look_id}")
    def delete_look(look_id: str) -> dict:
        def apply(p: Project) -> Project:
            _look(p, look_id)
            p.looks = [lk for lk in p.looks if lk.id != look_id]
            return p

        state.update(apply)
        return _payload()

    @r.get("/api/remote/pair")
    def pair(request: Request) -> dict:
        # O token só é mostrado a quem está no próprio mestre (o editor).
        if not is_loopback(request.scope):
            raise HTTPException(403, "pareamento só pelo mestre")
        url = remote_url(host, port, token)
        return {"url": url, "token": token, "lan": host not in ("127.0.0.1", "localhost"),
                "qr_svg": qr_svg(url)}

    return r
