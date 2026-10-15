"""Google Drive direto na galeria (API oficial Drive v3, só leitura).

Navega uma pasta do Drive (a "pasta raiz" do operador, com subpastas de GIFs,
vídeos etc.), mostra miniaturas e importa o arquivo escolhido para ``media/``
do projeto. Nada é baixado até alguém escolher.

Dois modos de acesso, escolhidos pelo ``.env`` (segredos nunca no git):

- **oauth** (recomendado, pasta privada): ``PROJMAP_GDRIVE_CLIENT_ID`` e
  ``PROJMAP_GDRIVE_CLIENT_SECRET`` de um cliente OAuth do tipo *App para
  computador*. O botão "Conectar Google Drive" do editor abre o consentimento
  do Google; o *refresh token* fica em ``~/.projmap/gdrive-token.json`` (só
  leitura: escopo ``drive.readonly``).
- **apikey** (sem login): ``PROJMAP_GDRIVE_API_KEY`` + pasta compartilhada como
  "qualquer pessoa com o link".

A pasta raiz vem de ``PROJMAP_GDRIVE_FOLDER`` ou do link colado no editor
(guardado em ``~/.projmap/library.json``). Sem pasta, o modo oauth usa o
"Meu Drive" inteiro.

Segurança: o cliente só navega a raiz e as pastas que o próprio servidor já
listou, e só importa arquivos vistos nessas listagens (ids opacos do Drive,
nunca caminhos).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol
from urllib.parse import urlencode

import httpx

from .core.store import GIF_EXTS, IMAGE_EXTS, VIDEO_EXTS

log = logging.getLogger(__name__)

API = "https://www.googleapis.com/drive/v3"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
TOKEN_PATH = Path.home() / ".projmap" / "gdrive-token.json"
MAX_DOWNLOAD = 4 << 30  # 4 GiB: mais que isso não é mídia de projeção razoável
FIELDS = ("nextPageToken,files(id,name,mimeType,size,modifiedTime,md5Checksum,fileExtension,thumbnailLink,"
          "imageMediaMetadata(width,height),videoMediaMetadata(width,height,durationMillis),"
          "shortcutDetails(targetId,targetMimeType))")

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,200}$")
_URL_ID_RES = [
    re.compile(r"/folders/([A-Za-z0-9_-]{10,})"),
    re.compile(r"[?&]id=([A-Za-z0-9_-]{10,})"),
    re.compile(r"/d/([A-Za-z0-9_-]{10,})"),
]


class DriveError(Exception):
    def __init__(self, msg: str, status: int = 502):
        super().__init__(msg)
        self.status = status


def folder_id_from(text: str) -> str:
    """Id da pasta a partir do link do Drive (ou do próprio id)."""
    text = (text or "").strip()
    for rx in _URL_ID_RES:
        m = rx.search(text)
        if m:
            return m.group(1)
    if _ID_RE.match(text):
        return text
    raise ValueError("link de pasta do Google Drive inválido (cole o link da barra de endereço da pasta)")


def valid_id(file_id: str) -> bool:
    return bool(_ID_RE.match(file_id or "")) or file_id == "root"


def kind_for(mime: str, name: str, ext: str = "") -> Optional[str]:
    """video | image | gif | None (não é mídia). Pela extensão, que é o que o
    store usa; o mimeType cobre arquivos sem extensão no nome."""
    e = ("." + ext.lower()) if ext else Path(name).suffix.lower()
    if e in GIF_EXTS or mime == "image/gif":
        return "gif"
    if e in VIDEO_EXTS or (not e and mime.startswith("video/")):
        return "video"
    if e in IMAGE_EXTS or (not e and mime in ("image/png", "image/jpeg", "image/webp", "image/bmp")):
        return "image"
    return None


_MIME_EXT = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm", "video/x-matroska": ".mkv",
             "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/bmp": ".bmp", "image/gif": ".gif"}


def import_name(name: str, mime: str, ext: str = "") -> str:
    """Nome com extensão válida para o store (que decide o tipo pela extensão)."""
    e = Path(name).suffix.lower()
    if e in VIDEO_EXTS | IMAGE_EXTS | GIF_EXTS:
        return name
    if ext and ("." + ext.lower()) in VIDEO_EXTS | IMAGE_EXTS | GIF_EXTS:
        return f"{name}.{ext.lower()}"
    return name + _MIME_EXT.get(mime, "")


@dataclass
class DriveEntry:
    id: str
    name: str
    kind: str  # folder | video | image | gif
    size_bytes: int = 0
    modified: str = ""
    md5: str = ""
    mime: str = ""
    ext: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    thumb: str = ""  # thumbnailLink (não vai para o cliente)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("thumb")
        d["has_thumb"] = bool(self.thumb)
        d["aspect"] = round(self.width / self.height, 4) if self.width and self.height else 0
        return d


# ------------------------------------------------------------------- auth
class DriveAuth(Protocol):
    mode: str

    def ready(self) -> bool: ...
    def apply(self, headers: dict, params: dict) -> None: ...


class ApiKeyAuth:
    """Pasta pública ("qualquer pessoa com o link"): só a chave de API."""

    mode = "apikey"

    def __init__(self, key: str):
        self.key = key

    def ready(self) -> bool:
        return bool(self.key)

    def apply(self, headers: dict, params: dict) -> None:
        params["key"] = self.key


class OAuthAuth:
    """OAuth 2.0 de app instalado (loopback + PKCE). Guarda só o refresh token."""

    mode = "oauth"

    def __init__(self, client_id: str, client_secret: str, token_path: Path = TOKEN_PATH,
                 http: Optional[httpx.Client] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_path = Path(token_path)
        self._http = http or httpx.Client(timeout=30)
        self._lock = threading.Lock()
        self._access: tuple[str, float] = ("", 0.0)
        self._pending: dict[str, tuple[str, str, float]] = {}  # state → (verifier, redirect, criado)

    # -- consentimento
    def auth_url(self, redirect_uri: str) -> str:
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        now = time.time()
        self._pending = {k: v for k, v in self._pending.items() if now - v[2] < 900}
        self._pending[state] = (verifier, redirect_uri, now)
        q = {"client_id": self.client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE,
             "access_type": "offline", "prompt": "consent", "state": state, "code_challenge": challenge,
             "code_challenge_method": "S256"}
        return f"{AUTH_URL}?{urlencode(q)}"

    def finish(self, code: str, state: str) -> None:
        pending = self._pending.pop(state, None)
        if pending is None:
            raise DriveError("pedido de conexão expirado ou desconhecido; clique em Conectar de novo", 400)
        verifier, redirect, _ = pending
        res = self._http.post(TOKEN_URL, data={
            "code": code, "client_id": self.client_id, "client_secret": self.client_secret,
            "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
        if res.status_code != 200:
            raise DriveError(f"Google recusou a conexão ({res.status_code}): {_google_msg(res)}", 400)
        data = res.json()
        refresh = data.get("refresh_token")
        if not refresh:
            raise DriveError("o Google não devolveu refresh token; remova o acesso do app na conta e conecte de novo", 400)
        self._save({"refresh_token": refresh})
        self._access = (data.get("access_token", ""), time.time() + float(data.get("expires_in", 0)) - 60)

    def disconnect(self) -> None:
        self._access = ("", 0.0)
        try:
            self.token_path.unlink()
        except FileNotFoundError:
            pass

    # -- uso
    def ready(self) -> bool:
        return bool(self._refresh_token())

    def apply(self, headers: dict, params: dict) -> None:
        headers["Authorization"] = f"Bearer {self._token()}"

    def _token(self) -> str:
        with self._lock:
            tok, exp = self._access
            if tok and time.time() < exp:
                return tok
            refresh = self._refresh_token()
            if not refresh:
                raise DriveError("Google Drive não conectado: clique em Conectar Google Drive no editor", 401)
            res = self._http.post(TOKEN_URL, data={
                "client_id": self.client_id, "client_secret": self.client_secret,
                "refresh_token": refresh, "grant_type": "refresh_token"})
            if res.status_code != 200:
                if res.status_code in (400, 401):
                    self.disconnect()  # revogado: o botão "Conectar" volta a aparecer
                raise DriveError(f"não consegui renovar o acesso ao Drive: {_google_msg(res)}", 401)
            data = res.json()
            self._access = (data["access_token"], time.time() + float(data.get("expires_in", 3600)) - 60)
            return self._access[0]

    def _refresh_token(self) -> str:
        try:
            return json.loads(self.token_path.read_text(encoding="utf-8")).get("refresh_token", "")
        except (OSError, ValueError):
            return ""

    def _save(self, data: dict) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.token_path.parent, prefix=".gdrive.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.token_path)


def _google_msg(res: httpx.Response) -> str:
    try:
        body = res.json()
    except ValueError:
        return res.text[:200]
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("message", err))
    return str(body.get("error_description") or err or body)[:200]


# ----------------------------------------------------------------- cliente
class DriveClient:
    def __init__(self, auth: DriveAuth, root: str, cache_dir: Path, http: Optional[httpx.Client] = None):
        self.auth = auth
        self.root = root
        self.cache_dir = Path(cache_dir)
        self._http = http or httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=True)
        self._lock = threading.Lock()
        self._folders: dict[str, str] = {}  # pastas já vistas (id → nome): as únicas navegáveis
        self._files: dict[str, DriveEntry] = {}  # arquivos já vistos: os únicos importáveis

    @property
    def mode(self) -> str:
        return self.auth.mode

    def ready(self) -> bool:
        return bool(self.root) and self.auth.ready()

    # -- HTTP
    def _get(self, url: str, params: Optional[dict] = None, stream: bool = False):
        headers: dict = {}
        params = dict(params or {})
        self.auth.apply(headers, params)
        req = self._http.build_request("GET", url, params=params, headers=headers)
        try:
            res = self._http.send(req, stream=stream)
        except httpx.HTTPError as exc:
            raise DriveError(f"sem conexão com o Google Drive ({exc.__class__.__name__})") from exc
        if res.status_code >= 400:
            if stream:
                res.read()
            status = 404 if res.status_code == 404 else (403 if res.status_code in (401, 403) else 502)
            hint = " (a pasta está compartilhada com o link?)" if res.status_code in (403, 404) and self.mode == "apikey" else ""
            raise DriveError(f"Google Drive respondeu {res.status_code}: {_google_msg(res)}{hint}", status)
        return res

    def folder_name(self, folder_id: str) -> str:
        if folder_id in self._folders:
            return self._folders[folder_id]
        data = self._get(f"{API}/files/{folder_id}", {"fields": "id,name,mimeType", "supportsAllDrives": "true"}).json()
        if data.get("mimeType") != FOLDER_MIME:
            raise DriveError("o link não é de uma pasta", 422)
        name = data.get("name") or "Drive"
        with self._lock:
            self._folders[folder_id] = name
        return name

    def can_browse(self, folder_id: str) -> bool:
        return folder_id == self.root or folder_id in self._folders

    def list(self, folder_id: Optional[str] = None) -> dict:
        """Subpastas e mídias de uma pasta (só a raiz e pastas já vistas)."""
        folder_id = folder_id or self.root
        if not self.can_browse(folder_id):
            raise DriveError("pasta fora da raiz configurada", 403)
        name = self.folder_name(folder_id) if folder_id != "root" else "Meu Drive"
        folders: list[DriveEntry] = []
        files: list[DriveEntry] = []
        page = None
        for _ in range(20):  # até ~20 mil itens; pasta maior que isso não é galeria
            params = {"q": f"'{folder_id}' in parents and trashed=false", "fields": FIELDS, "pageSize": 1000,
                      "orderBy": "folder,name_natural", "supportsAllDrives": "true",
                      "includeItemsFromAllDrives": "true"}
            if page:
                params["pageToken"] = page
            data = self._get(f"{API}/files", params).json()
            for f in data.get("files", []):
                e = self._entry(f)
                if e is None:
                    continue
                (folders if e.kind == "folder" else files).append(e)
            page = data.get("nextPageToken")
            if not page:
                break
        with self._lock:
            for e in folders:
                self._folders[e.id] = e.name
            for e in files:
                self._files[e.id] = e
        return {"folder": {"id": folder_id, "name": name}, "folders": [e.to_dict() for e in folders],
                "items": [e.to_dict() for e in files]}

    @staticmethod
    def _entry(f: dict) -> Optional[DriveEntry]:
        mime = f.get("mimeType", "")
        fid = f.get("id", "")
        if mime == SHORTCUT_MIME:  # atalho para pasta: navega como pasta
            sd = f.get("shortcutDetails") or {}
            if sd.get("targetMimeType") == FOLDER_MIME and sd.get("targetId"):
                return DriveEntry(id=sd["targetId"], name=f.get("name", ""), kind="folder", mime=FOLDER_MIME)
            return None
        if mime == FOLDER_MIME:
            return DriveEntry(id=fid, name=f.get("name", ""), kind="folder", mime=mime)
        kind = kind_for(mime, f.get("name", ""), f.get("fileExtension", ""))
        if kind is None:
            return None
        img = f.get("imageMediaMetadata") or {}
        vid = f.get("videoMediaMetadata") or {}
        return DriveEntry(
            id=fid, name=f.get("name", ""), kind=kind, size_bytes=int(f.get("size") or 0),
            modified=f.get("modifiedTime", ""), md5=f.get("md5Checksum", ""), mime=mime,
            ext=f.get("fileExtension", ""), width=int(img.get("width") or vid.get("width") or 0),
            height=int(img.get("height") or vid.get("height") or 0),
            duration=round(int(vid.get("durationMillis") or 0) / 1000.0, 2), thumb=f.get("thumbnailLink", ""))

    def entry(self, file_id: str) -> DriveEntry:
        e = self._files.get(file_id)
        if e is None:
            raise DriveError("arquivo não encontrado (abra a pasta dele na galeria)", 404)
        return e

    # -- miniaturas
    def thumbnail(self, file_id: str, make_thumb: Callable[[Path, str], bytes]) -> bytes:
        e = self.entry(file_id)
        tdir = self.cache_dir / "gdrive-thumbs"
        key = hashlib.sha1(f"{e.id}:{e.modified}:{e.md5}".encode()).hexdigest()[:20]
        path = tdir / f"{key}.jpg"
        if path.is_file():
            return path.read_bytes()
        data = b""
        if e.thumb:
            try:
                # thumbnailLink aceita "=s<lado>" no fim para escolher o tamanho
                url = re.sub(r"=s\d+$", "=s320", e.thumb)
                res = self._get(url)
                if res.headers.get("content-type", "").startswith("image/"):
                    data = _to_jpeg(res.content)
            except DriveError as exc:
                log.debug("miniatura do Drive indisponível para %s: %s", e.name, exc)
        if not data and e.kind in ("image", "gif") and 0 < e.size_bytes <= 25 << 20:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / import_name(e.name, e.mime, e.ext)
                self._download_to(e, p)
                data = make_thumb(p, e.kind)
        if not data:
            raise DriveError("miniatura indisponível", 404)
        tdir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return data

    # -- download
    def download(self, file_id: str, dest_dir: Path) -> tuple[DriveEntry, Path]:
        e = self.entry(file_id)
        if e.size_bytes > MAX_DOWNLOAD:
            raise DriveError(f"arquivo grande demais ({e.size_bytes >> 20} MiB)", 413)
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = Path(dest_dir) / import_name(e.name, e.mime, e.ext)
        self._download_to(e, path)
        return e, path

    def _download_to(self, e: DriveEntry, path: Path) -> None:
        res = self._get(f"{API}/files/{e.id}", {"alt": "media", "supportsAllDrives": "true"}, stream=True)
        size = 0
        try:
            with open(path, "wb") as out:
                for chunk in res.iter_bytes(1 << 20):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD:
                        raise DriveError("download passou do limite", 413)
                    out.write(chunk)
        finally:
            res.close()


def _to_jpeg(data: bytes) -> bytes:
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(data)) as im:
        im = im.convert("RGB")
        im.thumbnail((320, 320))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=78)
        return buf.getvalue()


# ----------------------------------------------------------------- factory
@dataclass
class DriveConfig:
    mode: str  # off | oauth | apikey
    root: str
    client_id: str = ""
    client_secret: str = ""
    api_key: str = ""


def drive_config(env: Optional[dict] = None, saved_folder: str = "") -> DriveConfig:
    """Lê o ``.env``/ambiente. ``PROJMAP_GDRIVE`` força o modo (off|oauth|apikey);
    sem ele, o modo sai das credenciais presentes (OAuth tem prioridade)."""
    env = os.environ if env is None else env
    cid = env.get("PROJMAP_GDRIVE_CLIENT_ID", "").strip()
    secret = env.get("PROJMAP_GDRIVE_CLIENT_SECRET", "").strip()
    key = env.get("PROJMAP_GDRIVE_API_KEY", "").strip()
    mode = env.get("PROJMAP_GDRIVE", "").strip().lower()
    if mode not in ("off", "oauth", "apikey"):
        mode = "oauth" if cid and secret else ("apikey" if key else "off")
    folder = env.get("PROJMAP_GDRIVE_FOLDER", "").strip() or saved_folder
    try:
        root = folder_id_from(folder) if folder else ""
    except ValueError:
        log.warning("PROJMAP_GDRIVE_FOLDER inválido: %r", folder)
        root = ""
    if mode == "oauth" and not root:
        root = "root"  # sem pasta escolhida: o Meu Drive inteiro
    return DriveConfig(mode=mode, root=root, client_id=cid, client_secret=secret, api_key=key)


def get_drive(cfg: DriveConfig, cache_dir: Path, token_path: Path = TOKEN_PATH,
              http: Optional[httpx.Client] = None) -> Optional[DriveClient]:
    """Factory: ``None`` quando o Drive não está configurado (modo off)."""
    if cfg.mode == "oauth":
        if not (cfg.client_id and cfg.client_secret):
            return None
        auth: DriveAuth = OAuthAuth(cfg.client_id, cfg.client_secret, token_path, http=http)
    elif cfg.mode == "apikey":
        if not cfg.api_key:
            return None
        auth = ApiKeyAuth(cfg.api_key)
    else:
        return None
    return DriveClient(auth, cfg.root, cache_dir, http=http)
