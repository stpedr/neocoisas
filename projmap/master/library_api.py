"""Rotas da galeria: biblioteca de pastas, miniaturas, importação e sugestões."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..core.project import Project
from ..core.state import ProjectState
from ..library import Library, cached_thumbnail, probe, save_roots
from ..suggest import MediaRef, suggest_all
from .auth import is_loopback


class RootsBody(BaseModel):
    roots: list[str] = Field(default_factory=list, max_length=20)


class SuggestBody(BaseModel):
    node_id: Optional[str] = None
    sources: list[str] = Field(default_factory=lambda: ["project", "library"])
    surface_ids: Optional[list[str]] = None


def create_router(state: ProjectState, library: Library, save_config: bool = True) -> APIRouter:
    r = APIRouter()
    store = state.store
    media_meta: dict[str, tuple[int, int, float]] = {}  # sha → (w, h, dur), cache em memória

    def _jpeg(data: bytes) -> Response:
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

    def _project_media_info(project: Project) -> list[dict]:
        out = []
        for sha, item in project.media.items():
            if sha not in media_meta:
                media_meta[sha] = probe(store.media_path(item), item.kind)
            w, h, dur = media_meta[sha]
            out.append({**item.model_dump(mode="json"), "width": w, "height": h, "duration": round(dur, 2),
                        "aspect": round(w / h, 4) if w and h else 0})
        return out

    # ------------------------------------------------------------ biblioteca
    @r.get("/api/library")
    def list_library(request: Request, rescan: bool = False) -> dict:
        items = library.scan() if rescan or not library.items() else library.items()
        folders = sorted({it.folder for it in items})
        return {
            "roots": [{"path": p, "exists": Path(p).is_dir()} for p in library.roots],
            "can_edit_roots": is_loopback(request.scope),
            "folders": folders,
            "items": [it.to_dict() for it in sorted(items, key=lambda i: (i.folder, i.name.lower()))],
        }

    @r.put("/api/library/roots")
    def set_roots(body: RootsBody, request: Request) -> dict:
        # Escolher pastas do disco é coisa de quem está no mestre: do celular, não.
        if not is_loopback(request.scope):
            raise HTTPException(403, "as pastas da biblioteca só podem ser configuradas no próprio mestre")
        roots = [str(Path(p.strip().strip('"')).expanduser()) for p in body.roots if p.strip()]
        missing = [p for p in roots if not Path(p).is_dir()]
        if missing:
            raise HTTPException(422, [f"pasta não encontrada: {p}" for p in missing])
        library.roots = roots
        if save_config:
            save_roots(roots)
        return list_library(request, rescan=True)

    @r.get("/api/library/{item_id}/thumb")
    def library_thumb(item_id: str) -> Response:
        try:
            return _jpeg(library.thumbnail(item_id))
        except KeyError:
            raise HTTPException(404, "item não encontrado (releia a biblioteca)") from None
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, [f"miniatura indisponível: {exc}"]) from exc

    @r.post("/api/library/{item_id}/import")
    def library_import(item_id: str) -> dict:
        """Copia o arquivo para o projeto (por hash: importar de novo não duplica)."""
        try:
            item, path = library.get(item_id)
        except KeyError:
            raise HTTPException(404, "item não encontrado (releia a biblioteca)") from None
        try:
            media = store.add_media(path, item.name)
        except (OSError, ValueError) as exc:
            raise HTTPException(422, [str(exc)]) from exc
        media_meta[media.sha256] = (item.width, item.height, item.duration)

        def apply(p: Project) -> Project:
            p.media[media.sha256] = media
            return p

        rev = state.update(apply)
        return {"revision": rev, "item": media.model_dump(mode="json")}

    # ------------------------------------------------------- mídia do projeto
    @r.get("/api/media-info")
    def media_info() -> dict:
        _, project = state.snapshot()
        return {"items": _project_media_info(project)}

    @r.get("/api/media/{sha256}/thumb")
    def media_thumb(sha256: str) -> Response:
        _, project = state.snapshot()
        item = project.media.get(sha256)
        if item is None:
            raise HTTPException(404, "mídia não encontrada")
        try:
            return _jpeg(cached_thumbnail(library.cache_dir, store.media_path(item), item.kind))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, [f"miniatura indisponível: {exc}"]) from exc

    # ---------------------------------------------------------------- sugestões
    @r.post("/api/suggest")
    def suggest(body: SuggestBody) -> dict:
        _, project = state.snapshot()
        node = project.nodes[0] if body.node_id is None else next(
            (n for n in project.nodes if n.id == body.node_id), None)
        if node is None:
            raise HTTPException(404, "nó não existe")
        medias: list[MediaRef] = []
        known_names: set[tuple[str, int]] = set()
        if "project" in body.sources:
            for m in _project_media_info(project):
                medias.append(MediaRef(f"sha:{m['sha256']}", m["filename"], m["kind"], m["width"], m["height"]))
                known_names.add((m["filename"], m["size_bytes"]))
        if "library" in body.sources:
            items = library.items() or library.scan()
            for it in items:
                if (it.name, it.size_bytes) in known_names:
                    continue  # já está no projeto: não sugerir duas vezes
                medias.append(MediaRef(f"lib:{it.id}", it.name, it.kind, it.width, it.height, it.folder))
        surfaces = [(s.id, s.warp.base) for s in project.surfaces
                    if s.node_id == node.id and (body.surface_ids is None or s.id in body.surface_ids)]
        out_area = float(node.output.width * node.output.height)
        return {"suggestions": suggest_all(surfaces, medias, out_area), "media_count": len(medias)}

    return r
