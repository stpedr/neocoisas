"""Biblioteca de mídias: pastas do computador (inclusive o Google Drive sincronizado).

O caminho mais simples para "ver as pastas do Drive" é o **Google Drive para
computador**: ele espelha o Drive numa pasta local (ex.: ``G:\\Meu Drive``). O
ProjMap só lê essa pasta, sem chave de API nem login. O mesmo vale para
OneDrive, Dropbox ou um HD externo.

- As pastas raiz ficam em ``~/.projmap/library.json`` (são da máquina, não do
  projeto) ou vêm de ``--library``.
- A varredura é recursiva e só lista vídeo/GIF/imagem. Os metadados (tamanho,
  duração) e as miniaturas ficam em cache por (caminho, data de modificação).
- Nada é copiado até o operador escolher: aí o arquivo entra em ``media/`` do
  projeto (por hash, sem duplicar).
- Os ids são opacos (hash do caminho). A API nunca aceita caminhos do cliente.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

from .config import config_dir
from .core.store import GIF_EXTS, IMAGE_EXTS, VIDEO_EXTS, _atomic_write_bytes, media_kind_for

log = logging.getLogger(__name__)

MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS | GIF_EXTS
MAX_ITEMS = 5000
THUMB_SIZE = 320
CONFIG_PATH = config_dir() / "library.json"


@dataclass
class LibraryItem:
    id: str
    name: str
    folder: str  # "<raiz>/sub/pasta", para agrupar na galeria
    kind: str  # video | image | gif
    size_bytes: int
    mtime: float
    width: int = 0
    height: int = 0
    duration: float = 0.0

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.width and self.height else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["aspect"] = round(self.aspect, 4)
        return d


def load_roots(path: Path = CONFIG_PATH) -> list[str]:
    try:
        return [str(r) for r in json.loads(path.read_text(encoding="utf-8")).get("roots", [])]
    except (OSError, ValueError):
        return []


def _load_config(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_config(path: Path, **changes) -> None:
    data = {**_load_config(path), **changes}  # preserva as outras chaves
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write_bytes(path, payload)


def save_roots(roots: Iterable[str], path: Path = CONFIG_PATH) -> None:
    _save_config(path, roots=list(roots))


def load_gdrive_folder(path: Path = CONFIG_PATH) -> str:
    """Link/id da pasta do Google Drive colado no editor (ver ``gdrive.py``)."""
    return str(_load_config(path).get("gdrive_folder", ""))


def save_gdrive_folder(folder: str, path: Path = CONFIG_PATH) -> None:
    _save_config(path, gdrive_folder=folder)


def probe(path: Path, kind: str) -> tuple[int, int, float]:
    """(largura, altura, duração em s). Falhas viram zeros: a galeria ainda lista o arquivo."""
    if kind == "motion":  # HTML: o navegador dos motions renderiza em 1280x720
        return 1280, 720, 0.0
    try:
        if kind == "video":
            import av

            with av.open(str(path)) as c:
                s = c.streams.video[0]
                dur = float(s.duration * s.time_base) if s.duration and s.time_base else (
                    c.duration / av.time_base if c.duration else 0.0)
                return s.codec_context.width, s.codec_context.height, dur
        from PIL import Image

        with Image.open(path) as im:  # lê só o cabeçalho
            dur = 0.0
            if kind == "gif":
                frames = getattr(im, "n_frames", 1)
                dur = frames * im.info.get("duration", 100) / 1000.0
            return im.width, im.height, dur
    except Exception as exc:  # noqa: BLE001 — arquivo corrompido não derruba a galeria
        log.warning("biblioteca: não consegui ler %s (%s)", path.name, exc)
        return 0, 0, 0.0


def _motion_card(path: Path):  # noqa: ANN202 — PIL.Image
    """Miniatura de um motion (HTML não tem quadro para extrair): cartão com o nome do manifesto."""
    from PIL import Image, ImageDraw

    from .motion.manifest import parse_motion_html

    try:
        info = parse_motion_html(path.read_bytes())
        title, sub = info.name, f"v{info.version}" + (" · vídeo" if info.video_input else "")
    except (OSError, ValueError):
        title, sub = path.stem, ""
    im = Image.new("RGB", (320, 180))
    g = ImageDraw.Draw(im)
    for x in range(320):  # degradê roxo do ProjMap
        g.line([(x, 0), (x, 179)], fill=(40 + x // 8, 30, 90 + x // 5))
    g.text((14, 14), "MOTION", fill=(255, 255, 255))
    g.text((14, 120), title[:40], fill=(255, 255, 255))
    if sub:
        g.text((14, 140), sub, fill=(220, 210, 255))
    return im


def make_thumbnail(path: Path, kind: str, size: int = THUMB_SIZE) -> bytes:
    """Miniatura JPEG (lado maior = ``size``). Vídeo: quadro a ~10% da duração."""
    from io import BytesIO

    from PIL import Image

    if kind == "motion":
        im = _motion_card(path)
    elif kind == "video":
        import av

        with av.open(str(path)) as c:
            s = c.streams.video[0]
            if s.duration and s.time_base:
                c.seek(int(s.duration * 0.1), stream=s)
            frame = next(c.decode(s))
            im = frame.to_image()
    else:
        im = Image.open(path)
        im.seek(0)
        im = im.convert("RGB")
    im.thumbnail((size, size))
    buf = BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=78)
    return buf.getvalue()


class Library:
    def __init__(self, roots: Iterable[str], cache_dir: Path):
        self.roots = [str(r) for r in roots]
        self.cache_dir = Path(cache_dir)
        self._lock = threading.Lock()
        self._items: dict[str, tuple[LibraryItem, Path]] = {}
        self._meta_path = self.cache_dir / "library-meta.json"
        self._meta: dict[str, list] = self._load_meta()

    # ------------------------------------------------------------- varredura
    def _load_meta(self) -> dict:
        try:
            return json.loads(self._meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_meta(self) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._meta_path.write_text(json.dumps(self._meta), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _id(path: Path) -> str:
        return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]

    def scan(self) -> list[LibraryItem]:
        """Relê as pastas (rápido: só os arquivos novos/alterados são abertos)."""
        found: dict[str, tuple[LibraryItem, Path]] = {}
        for root_s in self.roots:
            root = Path(root_s)
            if not root.is_dir():
                continue
            label = root.name or str(root)
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "$")))
                rel_dir = Path(dirpath).relative_to(root)
                folder = label if str(rel_dir) == "." else f"{label}/{rel_dir.as_posix()}"
                for name in sorted(filenames):
                    path = Path(dirpath) / name
                    if path.suffix.lower() not in MEDIA_EXTS or name.startswith("."):
                        continue
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    kind = media_kind_for(name)
                    iid = self._id(path)
                    key = f"{path}|{st.st_mtime}"
                    meta = self._meta.get(key)
                    if meta is None:
                        meta = list(probe(path, kind))
                        self._meta[key] = meta
                    found[iid] = (LibraryItem(iid, name, folder, kind, st.st_size, st.st_mtime, *meta), path)
                    if len(found) >= MAX_ITEMS:
                        break
                if len(found) >= MAX_ITEMS:
                    log.warning("biblioteca: limite de %d arquivos atingido", MAX_ITEMS)
                    break
        with self._lock:
            self._items = found
        self._save_meta()
        return [it for it, _ in found.values()]

    def items(self) -> list[LibraryItem]:
        with self._lock:
            return [it for it, _ in self._items.values()]

    def get(self, item_id: str) -> tuple[LibraryItem, Path]:
        with self._lock:
            hit = self._items.get(item_id)
        if hit is None:
            raise KeyError(item_id)
        return hit

    # ------------------------------------------------------------ miniaturas
    def thumbnail(self, item_id: str) -> bytes:
        item, path = self.get(item_id)
        return cached_thumbnail(self.cache_dir, path, item.kind, item.mtime)


def cached_thumbnail(cache_dir: Path, path: Path, kind: str, mtime: Optional[float] = None) -> bytes:
    mtime = mtime if mtime is not None else path.stat().st_mtime
    key = hashlib.sha1(f"{path.resolve()}|{mtime}".encode("utf-8")).hexdigest()[:20]
    thumb = Path(cache_dir) / "thumbs" / f"{key}.jpg"
    if thumb.is_file():
        return thumb.read_bytes()
    data = make_thumbnail(path, kind)
    try:
        thumb.parent.mkdir(parents=True, exist_ok=True)
        thumb.write_bytes(data)
    except OSError:
        pass
    return data
