"""Rotas do Google Drive na galeria e dos presets de imagem do operador."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from ..color_presets import ColorPresetStore
from ..core.project import ColorAdjust, Project
from ..core.state import ProjectState
from ..gdrive import DriveClient, DriveConfig, DriveError, OAuthAuth, folder_id_from, get_drive, valid_id
from ..library import make_thumbnail
from .auth import is_loopback


class FolderBody(BaseModel):
    folder: str = Field("", max_length=500, description="link da pasta do Drive (vazio = padrão)")


class PresetBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    color: ColorAdjust


def create_router(state: ProjectState, config: DriveConfig, cache_dir: Path, presets: ColorPresetStore,
                  token_path: Optional[Path] = None, save_folder: Optional[Callable[[str], None]] = None,
                  http=None) -> APIRouter:
    r = APIRouter()
    store = state.store
    kw = {"token_path": token_path} if token_path else {}
    holder: dict[str, Optional[DriveClient]] = {"drive": get_drive(config, cache_dir, http=http, **kw)}
    imported: dict[str, str] = {}  # id do Drive + md5 → sha256 no projeto

    def drive() -> DriveClient:
        d = holder["drive"]
        if d is None:
            raise HTTPException(409, "Google Drive não configurado (veja o GUIA: PROJMAP_GDRIVE_* no .env)")
        if not d.root:
            raise HTTPException(409, "escolha a pasta do Google Drive (cole o link no editor)")
        if not d.auth.ready():
            raise HTTPException(401, "Google Drive não conectado: clique em Conectar Google Drive")
        return d

    def fail(exc: DriveError):
        raise HTTPException(exc.status, str(exc)) from exc

    def local_only(request: Request, what: str) -> None:
        if not is_loopback(request.scope):
            raise HTTPException(403, f"{what} só no próprio mestre")

    # --------------------------------------------------------------- Drive
    @r.get("/api/gdrive/status")
    def status(request: Request) -> dict:
        d = holder["drive"]
        return {
            "mode": config.mode if d else "off",
            "configured": d is not None,
            "connected": bool(d and d.auth.ready()),
            "root": d.root if d else "",
            "folder_set": bool(d and d.root and d.root != "root"),
            "can_configure": is_loopback(request.scope),
        }

    @r.put("/api/gdrive/folder")
    def set_folder(body: FolderBody, request: Request) -> dict:
        local_only(request, "trocar a pasta do Drive")
        d = holder["drive"]
        if d is None:
            raise HTTPException(409, "Google Drive não configurado no .env")
        try:
            fid = folder_id_from(body.folder) if body.folder.strip() else ("root" if d.mode == "oauth" else "")
        except ValueError as exc:
            raise HTTPException(422, [str(exc)]) from exc
        old = d.root
        d.root = fid
        if fid and d.auth.ready():
            try:
                d.folder_name(fid)  # confere já: link errado vira erro aqui, não na galeria
            except DriveError as exc:
                d.root = old
                fail(exc)
        if save_folder:
            save_folder(body.folder.strip())
        return status(request)

    @r.get("/api/gdrive/connect")
    def connect(request: Request):
        local_only(request, "conectar o Google Drive")
        d = holder["drive"]
        if d is None or not isinstance(d.auth, OAuthAuth):
            raise HTTPException(409, "modo OAuth não configurado (PROJMAP_GDRIVE_CLIENT_ID/SECRET no .env)")
        # Loopback de app instalado: o Google aceita 127.0.0.1 em qualquer porta.
        port = request.url.port or 80
        return RedirectResponse(d.auth.auth_url(f"http://127.0.0.1:{port}/api/gdrive/callback"))

    @r.get("/api/gdrive/callback")
    def callback(request: Request, code: str = "", state: str = "", error: str = ""):
        local_only(request, "conectar o Google Drive")
        d = holder["drive"]
        if d is None or not isinstance(d.auth, OAuthAuth):
            raise HTTPException(409, "modo OAuth não configurado")
        if error or not code:
            return HTMLResponse(_page("Conexão cancelada", f"O Google respondeu: {error or 'sem código'}."), 400)
        try:
            d.auth.finish(code, state)
        except DriveError as exc:
            return HTMLResponse(_page("Não deu certo", str(exc)), exc.status)
        return RedirectResponse("/?gdrive=ok")

    @r.post("/api/gdrive/disconnect")
    def disconnect(request: Request) -> dict:
        local_only(request, "desconectar o Google Drive")
        d = holder["drive"]
        if d is not None and isinstance(d.auth, OAuthAuth):
            d.auth.disconnect()
        return status(request)

    @r.get("/api/gdrive/list")
    def list_folder(folder: str = "") -> dict:
        d = drive()
        if folder and not valid_id(folder):
            raise HTTPException(422, "id de pasta inválido")
        try:
            return d.list(folder or None)
        except DriveError as exc:
            fail(exc)

    @r.get("/api/gdrive/{file_id}/thumb")
    def thumb(file_id: str) -> Response:
        d = drive()
        try:
            data = d.thumbnail(file_id, make_thumbnail)
        except DriveError as exc:
            fail(exc)
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

    @r.post("/api/gdrive/{file_id}/import")
    def import_file(file_id: str) -> dict:
        """Baixa do Drive e registra no projeto (por hash: repetir não duplica)."""
        d = drive()
        try:
            entry = d.entry(file_id)
        except DriveError as exc:
            fail(exc)
        _, project = state.snapshot()
        key = f"{entry.id}:{entry.md5 or entry.modified}"
        sha = imported.get(key)
        if sha and sha in project.media:
            return {"revision": state.revision, "item": project.media[sha].model_dump(mode="json")}
        with tempfile.TemporaryDirectory(dir=_tmp_parent(store.root)) as td:
            try:
                entry, path = d.download(file_id, Path(td))
                media = store.add_media(path, path.name)
            except DriveError as exc:
                fail(exc)
            except (OSError, ValueError) as exc:
                raise HTTPException(422, [str(exc)]) from exc
        imported[key] = media.sha256

        def apply(p: Project) -> Project:
            p.media[media.sha256] = media
            return p

        rev = state.update(apply)
        return {"revision": rev, "item": media.model_dump(mode="json")}

    # ------------------------------------------------------ presets de imagem
    @r.get("/api/color-presets")
    def list_presets() -> dict:
        return {"presets": [p.model_dump(mode="json") for p in presets.list()]}

    @r.post("/api/color-presets")
    def save_preset(body: PresetBody) -> dict:
        try:
            p = presets.save(body.name, body.color)
        except ValueError as exc:
            raise HTTPException(422, [str(exc)]) from exc
        return {"preset": p.model_dump(mode="json"), **list_presets()}

    @r.delete("/api/color-presets/{preset_id}")
    def delete_preset(preset_id: str) -> dict:
        if not presets.delete(preset_id):
            raise HTTPException(404, "preset não encontrado")
        return list_presets()

    return r


def _tmp_parent(root: Path) -> Path:
    # Baixa ao lado do projeto: o add_media copia no mesmo disco, sem estourar o /tmp.
    p = Path(root) / "cache" / "downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _page(title: str, msg: str) -> str:
    from html import escape

    return (f"<!doctype html><meta charset=utf-8><title>{escape(title)}</title>"
            f"<body style='font-family:system-ui;background:#0b0f17;color:#e8eef6;padding:40px'>"
            f"<h1>{escape(title)}</h1><p>{escape(msg)}</p><p><a style='color:#9d87ff' href='/'>Voltar ao editor</a></p>")
