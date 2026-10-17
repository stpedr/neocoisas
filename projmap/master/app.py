"""API do mestre (FastAPI) — a UI de edição fala só com ela.

Princípios:

- **O projeto inteiro é o documento.** A UI envia o ``project.json`` completo a
  cada edição (``PUT /api/project``). É simples, idempotente e o servidor valida
  tudo de uma vez (quads, referências). Enquanto o usuário arrasta um canto, a
  UI manda ~20 PUTs/s; cada um custa uma validação e uma escrita atômica pequena.
- **Toggles de saída** (padrão de teste, contornos, blackout, dimmer) têm rota
  própria (``PATCH .../output``) — são os comandos que o remote do celular (F6)
  vai usar.
- **Mídia por upload** vai para ``media/<sha256>`` e é registrada no projeto.
- Por padrão o mestre escuta só em ``127.0.0.1``. Exposto na LAN (``--host
  0.0.0.0``), clientes de fora exigem o token de pareamento (ver ``auth.py``).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.background import BackgroundTask

from .. import __version__
from ..config import config_dir as default_config_dir, max_photo_bytes
from ..core.project import Output, Project, parse_project
from ..core.state import ProjectState
from .auth import PairingTokenMiddleware
from ..library import Library, load_roots
from .library_api import create_router as create_library_router
from .remote import create_router as create_remote_router

MAX_PHOTO_BYTES = max_photo_bytes()


class ProjectBody(BaseModel):
    project: dict[str, Any]


class DetectBody(BaseModel):
    detector: str = "classic"
    sensitivity: float = Field(0.5, ge=0.0, le=1.0)
    max_candidates: int = Field(12, ge=1, le=40)


def _validation_detail(exc: ValidationError) -> list[str]:
    out = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "__root__")
        msg = err.get("msg", "inválido").removeprefix("Value error, ")
        out.append(f"{loc}: {msg}" if loc else msg)
    return out


def create_app(state: ProjectState, ui_dir: Optional[Path] = None, runtime: Any = None,
               nlp_client_factory: Any = None, token: Optional[str] = None,
               host: str = "127.0.0.1", port: int = 8100,
               library_roots: Optional[list[str]] = None, save_library_config: bool = True,
               config_dir: Optional[Path] = None, drive_config: Any = None, drive_http: Any = None) -> FastAPI:
    """``runtime``: ``InteractionRuntime`` da camada interativa (opcional).
    ``nlp_client_factory``: devolve o cliente LLM para texto→cena (padrão: o do repo).
    ``token``: token de pareamento; exigido de clientes fora desta máquina (F6).
    ``host``/``port``: onde o servidor escuta, para montar a URL do remote.
    ``library_roots``: pastas da galeria (padrão: ``~/.projmap/library.json``).
    ``config_dir``: preferências da máquina (padrão ``~/.projmap``): presets de
    imagem, token e pasta do Google Drive.
    ``drive_config``: ``gdrive.DriveConfig`` (padrão: lido do ambiente/.env)."""
    app = FastAPI(title="ProjMap — mestre", version=__version__)
    # Dev: UI no `next dev` (outra porta) chamando a API local.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(PairingTokenMiddleware, token=token)
    store = state.store

    @app.exception_handler(ValidationError)
    async def _pydantic_error(_request, exc: ValidationError):  # noqa: ANN001
        return JSONResponse(status_code=422, content={"detail": _validation_detail(exc)})

    def _payload() -> dict:
        rev, project = state.snapshot()
        return {"revision": rev, "project": project.model_dump(mode="json")}

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__, "revision": state.revision}

    @app.get("/api/project")
    def get_project() -> dict:
        return _payload()

    @app.put("/api/project")
    def put_project(body: ProjectBody) -> dict:
        _, current = state.snapshot()
        try:
            project = parse_project(body.project)
        except ValueError as exc:
            if isinstance(exc, ValidationError):
                raise
            raise HTTPException(422, [str(exc)]) from exc
        # Mídia e fotos só entram por upload: o cliente não inventa arquivos nem
        # aponta caminhos arbitrários do disco.
        if set(project.media) - set(current.media):
            raise HTTPException(422, ["media: itens novos só via POST /api/media"])
        photos = {n.id: n.photo for n in current.nodes}
        for node in project.nodes:
            if node.photo != photos.get(node.id):
                raise HTTPException(422, [f"nodes.{node.id}.photo: troque a foto via upload"])
        rev = state.replace(project)
        return {"revision": rev}

    @app.patch("/api/nodes/{node_id}/output")
    def patch_output(node_id: str, changes: dict[str, Any]) -> dict:
        unknown = set(changes) - set(Output.model_fields)
        if unknown:
            raise HTTPException(422, [f"campo desconhecido: {', '.join(sorted(unknown))}"])

        def apply(p: Project) -> Project:
            node = _node_or_404(p, node_id)
            node.output = Output.model_validate({**node.output.model_dump(), **changes})
            return p

        state.update(apply)
        return _payload()

    @app.post("/api/media")
    def upload_media(file: UploadFile = File(...)) -> dict:
        try:
            item = store.add_media(file.file, file.filename or "arquivo")
        except ValueError as exc:
            raise HTTPException(422, [str(exc)]) from exc

        def apply(p: Project) -> Project:
            p.media[item.sha256] = item
            return p

        rev = state.update(apply)
        return {"revision": rev, "item": item.model_dump(mode="json")}

    @app.get("/media/{sha256}")
    def get_media(sha256: str) -> FileResponse:
        _, project = state.snapshot()
        item = project.media.get(sha256)
        if item is None:
            raise HTTPException(404, "mídia não encontrada")
        return FileResponse(store.media_path(item), filename=item.filename)

    @app.post("/api/nodes/{node_id}/photo")
    async def upload_photo(node_id: str, file: UploadFile = File(...)) -> dict:
        _, project = state.snapshot()
        _node_or_404(project, node_id)
        data = await file.read(MAX_PHOTO_BYTES + 1)
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(413, ["foto excede o limite de 25 MB"])
        try:
            rel = store.set_photo(node_id, data, file.filename or "foto.jpg")
        except ValueError as exc:
            raise HTTPException(422, [str(exc)]) from exc

        def apply(p: Project) -> Project:
            _node_or_404(p, node_id).photo = rel
            return p

        state.update(apply)
        return _payload()

    @app.get("/api/nodes/{node_id}/photo")
    def get_photo(node_id: str) -> FileResponse:
        _, project = state.snapshot()
        node = _node_or_404(project, node_id)
        path = store.resolve(node.photo)
        if path is None or not path.is_file():
            raise HTTPException(404, "nó sem foto")
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    @app.post("/api/nodes/{node_id}/detect")
    def detect_surfaces(node_id: str, body: DetectBody) -> dict:
        """Sugere superfícies a partir da foto do nó (F3). Não altera o projeto:
        a UI mostra os candidatos e cria só os que o operador escolher."""
        import cv2
        import numpy as np

        from ..detect import get_detector

        _, project = state.snapshot()
        node = _node_or_404(project, node_id)
        path = store.resolve(node.photo)
        if path is None or not path.is_file():
            raise HTTPException(422, ["envie a foto da posição do projetor antes de detectar"])
        bgr = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise HTTPException(422, ["foto ilegível"])
        try:
            detector = get_detector(body.detector)
        except ValueError as exc:
            raise HTTPException(422, [str(exc)]) from exc
        cands = detector.detect(bgr, sensitivity=body.sensitivity, max_candidates=body.max_candidates)
        return {"detector": detector.name, "candidates": [c.to_dict() for c in cands]}

    @app.get("/api/project/export")
    def export_project() -> FileResponse:
        _, project = state.snapshot()
        tmp_dir = Path(tempfile.mkdtemp(prefix="projmap-export-"))
        tmp = tmp_dir / "projeto.pmz"
        try:
            store.export_pmz(tmp)
        except BaseException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in project.name).strip("-") or "projeto"
        return FileResponse(
            tmp,
            filename=f"{safe}.pmz",
            media_type="application/zip",
            background=BackgroundTask(shutil.rmtree, tmp_dir, True),
        )

    app.include_router(create_remote_router(state, host=host, port=port, token=token))
    library = Library(load_roots() if library_roots is None else library_roots, store.root / "cache")
    app.include_router(create_library_router(state, library, save_config=save_library_config))

    from ..color_presets import ColorPresetStore
    from ..gdrive import drive_config as read_drive_config
    from ..library import load_gdrive_folder, save_gdrive_folder
    from .gdrive_api import create_router as create_gdrive_router

    cfg_dir = Path(config_dir) if config_dir else default_config_dir()
    lib_cfg = cfg_dir / "library.json"
    dcfg = drive_config or read_drive_config(saved_folder=load_gdrive_folder(lib_cfg))
    app.include_router(create_gdrive_router(
        state, dcfg, store.root / "cache", ColorPresetStore(cfg_dir / "color-presets.json"),
        token_path=cfg_dir / "gdrive-token.json",
        save_folder=(lambda f: save_gdrive_folder(f, lib_cfg)) if save_library_config else None,
        http=drive_http))

    if runtime is not None:
        from ..interact.api import create_router
        from ..interact.nlp import default_client

        app.include_router(create_router(runtime, nlp_client_factory or default_client))

    if ui_dir is not None and (ui_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
    else:
        @app.get("/")
        def no_ui() -> dict:
            return {
                "ok": True,
                "msg": "UI não compilada. Rode: cd projmap/ui && npm ci && npm run build",
            }

    return app


def _node_or_404(project: Project, node_id: str):
    try:
        return project.node(node_id)
    except KeyError:
        raise HTTPException(404, f"nó '{node_id}' não existe") from None
