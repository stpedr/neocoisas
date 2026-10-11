"""Persistência do projeto: diretório ``.projmap`` + exportação ``.pmz``.

Layout em disco::

    meu-show.projmap/
      project.json          # esquema em core/project.py
      media/<sha256><ext>   # mídia endereçada por conteúdo (sem duplicatas)
      captures/<node>/...   # fotos por projetor

Decisões:

- **Escrita atômica** (arquivo temporário + ``os.replace``): queda de energia
  durante um show não deixa um ``project.json`` pela metade.
- **Mídia por sha256**: o mesmo vídeo usado em 5 superfícies existe uma vez, e o
  hash é também o que os nós vão conferir ao baixar (F2).
- ``.pmz`` é um zip simples (portável, inspecionável). A importação recusa
  caminhos que escapem do destino (*zip slip*).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import BinaryIO, Optional, Union

from .project import MediaItem, MediaKind, Project, default_project, parse_project

PROJECT_FILE = "project.json"
MEDIA_DIR = "media"
CAPTURES_DIR = "captures"

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
GIF_EXTS = {".gif"}
PHOTO_EXTS = IMAGE_EXTS

PathLike = Union[str, Path]


def media_kind_for(filename: str) -> MediaKind:
    ext = Path(filename).suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in GIF_EXTS:
        return "gif"
    if ext in IMAGE_EXTS:
        return "image"
    raise ValueError(f"formato não suportado: '{ext or filename}'")


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)  # mkstemp cria 0600; o projeto é compartilhável (cópia p/ nós)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class ProjectStore:
    """Acesso a um diretório de projeto."""

    def __init__(self, root: PathLike):
        self.root = Path(root)

    # ------------------------------------------------------------------ projeto
    @property
    def project_path(self) -> Path:
        return self.root / PROJECT_FILE

    def exists(self) -> bool:
        return self.project_path.is_file()

    @classmethod
    def create(cls, root: PathLike, name: str = "Novo projeto") -> "ProjectStore":
        store = cls(root)
        if store.exists():
            raise FileExistsError(f"já existe um projeto em {store.root}")
        store.root.mkdir(parents=True, exist_ok=True)
        store.save(default_project(name))
        return store

    @classmethod
    def open_or_create(cls, root: PathLike, name: str = "Novo projeto") -> "ProjectStore":
        store = cls(root)
        return store if store.exists() else cls.create(root, name)

    def load(self) -> Project:
        data = json.loads(self.project_path.read_text(encoding="utf-8"))
        return parse_project(data)

    def save(self, project: Project) -> None:
        payload = json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2)
        _atomic_write_bytes(self.project_path, payload.encode("utf-8"))

    # -------------------------------------------------------------------- mídia
    def media_path(self, item: MediaItem) -> Path:
        return self.root / MEDIA_DIR / f"{item.sha256}{item.ext}"

    def add_media(self, src: Union[PathLike, BinaryIO], filename: str) -> MediaItem:
        """Copia a mídia para ``media/`` (por hash) e devolve o item.

        Não altera o ``project.json`` — quem chama registra o item em
        ``project.media`` (assim upload e edição do projeto ficam desacoplados).
        """
        kind = media_kind_for(filename)
        ext = Path(filename).suffix.lower()
        media_dir = self.root / MEDIA_DIR
        media_dir.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256()
        size = 0
        fd, tmp = tempfile.mkstemp(dir=media_dir, prefix=".upload.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as out:
                fh = open(src, "rb") if isinstance(src, (str, Path)) else src
                try:
                    while True:
                        chunk = fh.read(1 << 20)
                        if not chunk:
                            break
                        digest.update(chunk)
                        size += len(chunk)
                        out.write(chunk)
                finally:
                    if isinstance(src, (str, Path)):
                        fh.close()
            if size == 0:
                raise ValueError("arquivo vazio")
            item = MediaItem(
                sha256=digest.hexdigest(), filename=Path(filename).name, ext=ext, kind=kind, size_bytes=size
            )
            dest = self.media_path(item)
            if dest.exists():
                os.unlink(tmp)  # dedupe: conteúdo idêntico já está no projeto
            else:
                os.chmod(tmp, 0o644)
                os.replace(tmp, dest)
            return item
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # -------------------------------------------------------------------- fotos
    def set_photo(self, node_id: str, data: bytes, filename: str) -> str:
        """Grava a foto da posição do projetor; devolve o caminho relativo."""
        ext = Path(filename).suffix.lower()
        if ext not in PHOTO_EXTS:
            raise ValueError(f"foto deve ser imagem ({', '.join(sorted(PHOTO_EXTS))})")
        if not data:
            raise ValueError("arquivo vazio")
        rel = Path(CAPTURES_DIR) / node_id / f"photo{ext}"
        node_dir = self.root / CAPTURES_DIR / node_id
        if node_dir.is_dir():
            for old in node_dir.glob("photo.*"):
                old.unlink()
        _atomic_write_bytes(self.root / rel, data)
        return rel.as_posix()

    def resolve(self, rel: Optional[str]) -> Optional[Path]:
        """Resolve um caminho relativo do projeto, recusando fuga do diretório."""
        if not rel:
            return None
        path = (self.root / rel).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"caminho fora do projeto: {rel}")
        return path

    # ------------------------------------------------------- exportar/importar
    def export_pmz(self, dest: PathLike) -> Path:
        """Empacota project.json + mídia + capturas num ``.pmz`` (zip)."""
        dest = Path(dest)
        project = self.load()
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(self.project_path, PROJECT_FILE)
            for item in project.media.values():
                path = self.media_path(item)
                # Vídeo já é comprimido: STORED evita gastar CPU à toa.
                zf.write(path, f"{MEDIA_DIR}/{path.name}", compress_type=zipfile.ZIP_STORED)
            for node in project.nodes:
                photo = self.resolve(node.photo)
                if photo and photo.is_file():
                    zf.write(photo, node.photo)
        return dest

    @classmethod
    def import_pmz(cls, src: PathLike, dest_root: PathLike) -> "ProjectStore":
        """Extrai um ``.pmz`` num diretório novo (ou vazio) e valida o projeto."""
        dest = Path(dest_root)
        if dest.exists() and any(dest.iterdir()):
            raise FileExistsError(f"destino não está vazio: {dest}")
        dest.mkdir(parents=True, exist_ok=True)
        root = dest.resolve()
        with zipfile.ZipFile(src) as zf:
            for info in zf.infolist():
                target = (dest / info.filename).resolve()
                if not target.is_relative_to(root):
                    shutil.rmtree(dest, ignore_errors=True)
                    raise ValueError(f"entrada insegura no pacote: {info.filename}")
            zf.extractall(dest)
        store = cls(dest)
        project = store.load()  # valida esquema e referências
        for item in project.media.values():
            path = store.media_path(item)
            if not path.is_file():
                raise ValueError(f"pacote incompleto: falta {path.name}")
            if _sha256_file(path) != item.sha256:
                raise ValueError(f"mídia corrompida: {path.name}")
        return store


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
