"""Google Drive na galeria (API v3 simulada com httpx.MockTransport) e presets de imagem."""

import io
import json
import os
import stat
from urllib.parse import parse_qs, urlparse

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from projmap.core.project import Surface, Warp
from projmap.core.state import ProjectState
from projmap.core.store import ProjectStore
from projmap.gdrive import (DriveConfig, drive_config, folder_id_from, import_name, kind_for)
from projmap.master.app import create_app

ROOT = "RootFolder_0123456789"
SUB = "SubFolder_GIFs_0123456789"


def _png(color=(255, 0, 0), size=(64, 32)) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.full((size[1], size[0], 3), color, np.uint8)).save(buf, format="PNG")
    return buf.getvalue()


def _gif() -> bytes:
    frames = [Image.fromarray(np.full((20, 20, 3), c, np.uint8)) for c in ((255, 0, 0), (0, 0, 255))]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return buf.getvalue()


class FakeDrive:
    """O suficiente da Drive API v3 + OAuth para o ProjMap."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.png = _png()
        self.gif = _gif()
        self.tree = {
            ROOT: [
                {"id": SUB, "name": "GIFs", "mimeType": "application/vnd.google-apps.folder"},
                {"id": "Shortcut_000000001", "name": "Atalho Vídeos", "mimeType": "application/vnd.google-apps.shortcut",
                 "shortcutDetails": {"targetId": "VideosFolder_0123456", "targetMimeType": "application/vnd.google-apps.folder"}},
                {"id": "Photo_0000000001", "name": "parede.png", "mimeType": "image/png", "size": str(len(self.png)),
                 "md5Checksum": "aaa", "modifiedTime": "2026-10-01T00:00:00Z", "fileExtension": "png",
                 "imageMediaMetadata": {"width": 64, "height": 32}, "thumbnailLink": "https://lh3.example/thumb=s220"},
                {"id": "Doc_000000000001", "name": "roteiro.docx", "mimeType": "application/vnd.openxmlformats"},
            ],
            SUB: [
                {"id": "Gif_00000000001", "name": "fantasma", "mimeType": "image/gif", "size": str(len(self.gif)),
                 "md5Checksum": "bbb", "modifiedTime": "2026-10-02T00:00:00Z"},
            ],
        }
        self.files = {"Photo_0000000001": self.png, "Gif_00000000001": self.gif}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        url = req.url
        if url.host == "oauth2.googleapis.com":
            form = parse_qs(req.content.decode())
            if form["grant_type"] == ["authorization_code"]:
                assert form["code"] == ["CODE"] and form["code_verifier"][0]
                return httpx.Response(200, json={"access_token": "AT1", "refresh_token": "RT1", "expires_in": 3600})
            assert form["refresh_token"] == ["RT1"]
            return httpx.Response(200, json={"access_token": "AT2", "expires_in": 3600})
        if url.host == "lh3.example":
            return httpx.Response(200, content=_png((0, 255, 0)), headers={"content-type": "image/png"})
        path = url.path.removeprefix("/drive/v3")
        if path == "/files":
            q = url.params["q"]
            parent = q.split("'")[1]
            return httpx.Response(200, json={"files": self.tree.get(parent, [])})
        fid = path.removeprefix("/files/")
        if url.params.get("alt") == "media":
            if fid not in self.files:
                return httpx.Response(404, json={"error": {"message": "File not found"}})
            return httpx.Response(200, content=self.files[fid])
        if fid in self.tree:
            return httpx.Response(200, json={"id": fid, "name": "Projeção", "mimeType": "application/vnd.google-apps.folder"})
        return httpx.Response(404, json={"error": {"message": "File not found"}})


@pytest.fixture
def fake():
    return FakeDrive()


def _app(tmp_path, fake, cfg: DriveConfig):
    state = ProjectState(ProjectStore.create(tmp_path / "s.projmap", "T"))
    http = httpx.Client(transport=httpx.MockTransport(fake), follow_redirects=True)
    app = create_app(state, save_library_config=False, config_dir=tmp_path / "cfg", drive_config=cfg, drive_http=http)
    return TestClient(app, client=("127.0.0.1", 5000)), TestClient(app), state


# ---------------------------------------------------------------- funções puras
@pytest.mark.parametrize("text", [
    f"https://drive.google.com/drive/folders/{ROOT}",
    f"https://drive.google.com/drive/u/0/folders/{ROOT}?usp=sharing",
    f"https://drive.google.com/open?id={ROOT}",
    ROOT,
])
def test_id_da_pasta_pelo_link(text):
    assert folder_id_from(text) == ROOT


def test_link_invalido():
    with pytest.raises(ValueError):
        folder_id_from("https://exemplo.com/pasta")


def test_tipo_e_nome_de_importacao():
    assert kind_for("image/gif", "a") == "gif"
    assert kind_for("video/mp4", "clipe.mp4") == "video"
    assert kind_for("video/mp4", "sem-extensao") == "video"
    assert kind_for("application/pdf", "a.pdf") is None
    assert import_name("fantasma", "image/gif") == "fantasma.gif"
    assert import_name("clip", "video/quicktime", "mov") == "clip.mov"
    assert import_name("a.png", "image/png") == "a.png"


def test_modo_pelo_env():
    assert drive_config({}).mode == "off"
    c = drive_config({"PROJMAP_GDRIVE_API_KEY": "k", "PROJMAP_GDRIVE_FOLDER": f"https://drive.google.com/drive/folders/{ROOT}"})
    assert (c.mode, c.root) == ("apikey", ROOT)
    c = drive_config({"PROJMAP_GDRIVE_CLIENT_ID": "id", "PROJMAP_GDRIVE_CLIENT_SECRET": "s", "PROJMAP_GDRIVE_API_KEY": "k"})
    assert (c.mode, c.root) == ("oauth", "root")  # OAuth sem pasta = Meu Drive
    c = drive_config({"PROJMAP_GDRIVE": "off", "PROJMAP_GDRIVE_API_KEY": "k"})
    assert c.mode == "off"
    assert drive_config({"PROJMAP_GDRIVE_API_KEY": "k"}, saved_folder=ROOT).root == ROOT


# ---------------------------------------------------------------- modo chave de API
def test_navega_importa_e_nao_baixa_de_novo(tmp_path, fake):
    local, _, state = _app(tmp_path, fake, DriveConfig(mode="apikey", root=ROOT, api_key="KEY"))
    st = local.get("/api/gdrive/status").json()
    assert st["configured"] and st["connected"] and st["mode"] == "apikey"

    root = local.get("/api/gdrive/list").json()
    assert root["folder"]["id"] == ROOT
    assert [f["name"] for f in root["folders"]] == ["GIFs", "Atalho Vídeos"]
    assert [i["name"] for i in root["items"]] == ["parede.png"]  # .docx fica de fora
    assert root["items"][0]["width"] == 64 and "thumb" not in root["items"][0]
    assert all(r.url.params.get("key") == "KEY" for r in fake.calls)

    # pasta desconhecida é recusada; a subpasta listada é navegável
    assert local.get("/api/gdrive/list?folder=OutraPasta_123456789").status_code == 403
    sub = local.get(f"/api/gdrive/list?folder={SUB}").json()
    assert [i["kind"] for i in sub["items"]] == ["gif"]

    th = local.get("/api/gdrive/Photo_0000000001/thumb")
    assert th.status_code == 200 and th.headers["content-type"] == "image/jpeg"

    r = local.post("/api/gdrive/Gif_00000000001/import")
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert item["kind"] == "gif" and item["filename"] == "fantasma.gif"
    _, proj = state.snapshot()
    assert item["sha256"] in proj.media
    downloads = sum(1 for c in fake.calls if c.url.params.get("alt") == "media")
    assert local.post("/api/gdrive/Gif_00000000001/import").json()["item"]["sha256"] == item["sha256"]
    assert sum(1 for c in fake.calls if c.url.params.get("alt") == "media") == downloads  # não baixou de novo
    assert not list((tmp_path / "s.projmap" / "cache" / "downloads").glob("*/*"))  # temporário limpo

    assert local.post("/api/gdrive/NaoVisto_0000001/import").status_code == 404


def test_drive_desligado_e_pasta_so_no_mestre(tmp_path, fake):
    local, remote, _ = _app(tmp_path, fake, DriveConfig(mode="off", root=""))
    assert local.get("/api/gdrive/status").json()["configured"] is False
    assert local.get("/api/gdrive/list").status_code == 409

    local, remote, _ = _app(tmp_path / "b", fake, DriveConfig(mode="apikey", root="", api_key="KEY"))
    assert local.get("/api/gdrive/list").status_code == 409  # falta a pasta
    assert remote.put("/api/gdrive/folder", json={"folder": ROOT}).status_code == 403  # do celular, não
    assert local.put("/api/gdrive/folder", json={"folder": "lixo"}).status_code == 422
    st = local.put("/api/gdrive/folder", json={"folder": f"https://drive.google.com/drive/folders/{ROOT}"}).json()
    assert st["root"] == ROOT and st["folder_set"]
    assert local.get("/api/gdrive/list").status_code == 200


# ---------------------------------------------------------------- modo OAuth
def test_oauth_conecta_usa_bearer_e_desconecta(tmp_path, fake):
    local, remote, _ = _app(tmp_path, fake, DriveConfig(mode="oauth", root=ROOT, client_id="CID", client_secret="SEC"))
    assert local.get("/api/gdrive/status").json()["connected"] is False
    assert local.get("/api/gdrive/list").status_code == 401
    assert remote.get("/api/gdrive/connect", follow_redirects=False).status_code == 403

    r = local.get("/api/gdrive/connect", follow_redirects=False)
    assert r.status_code in (302, 307)
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["client_id"] == ["CID"] and q["code_challenge_method"] == ["S256"]
    assert q["scope"] == ["https://www.googleapis.com/auth/drive.readonly"]
    assert q["redirect_uri"][0].startswith("http://127.0.0.1:") and q["redirect_uri"][0].endswith("/api/gdrive/callback")

    assert local.get("/api/gdrive/callback?code=CODE&state=errado", follow_redirects=False).status_code == 400
    r = local.get(f"/api/gdrive/callback?code=CODE&state={q['state'][0]}", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/?gdrive=ok"

    token = tmp_path / "cfg" / "gdrive-token.json"
    assert json.loads(token.read_text()) == {"refresh_token": "RT1"}  # só o refresh token
    if os.name == "posix":
        assert stat.S_IMODE(token.stat().st_mode) == 0o600

    assert local.get("/api/gdrive/list").status_code == 200
    drive_calls = [c for c in fake.calls if c.url.host == "www.googleapis.com"]
    assert drive_calls[-1].headers["authorization"] == "Bearer AT1"

    st = local.post("/api/gdrive/disconnect").json()
    assert st["connected"] is False and not token.exists()


# ---------------------------------------------------------------- presets de imagem
def test_presets_de_imagem(tmp_path, fake):
    local, remote, state = _app(tmp_path, fake, DriveConfig(mode="off", root=""))
    assert local.get("/api/color-presets").json() == {"presets": []}
    color = {"brightness": 1.2, "contrast": 1.1, "saturation": 1.3, "gamma": 1.4, "temperature": -0.2}
    r = remote.post("/api/color-presets", json={"name": "  Parede da  igreja ", "color": color})
    assert r.status_code == 200
    assert r.json()["preset"]["id"] == "parede-da-igreja" and r.json()["preset"]["name"] == "Parede da igreja"
    # mesmo nome atualiza em vez de duplicar
    local.post("/api/color-presets", json={"name": "Parede da igreja", "color": {**color, "gamma": 1.0}})
    presets = local.get("/api/color-presets").json()["presets"]
    assert len(presets) == 1 and presets[0]["color"]["gamma"] == 1.0
    assert local.post("/api/color-presets", json={"name": "x", "color": {**color, "gamma": 9}}).status_code == 422
    assert local.post("/api/color-presets", json={"name": "", "color": color}).status_code == 422

    # aplicar numa superfície pelo remote
    def add(p):
        p.surfaces.append(Surface(id="parede", node_id="proj-1", warp=Warp(base=[[0, 0], [100, 0], [100, 100], [0, 100]])))
        return p

    state.update(add)
    r = local.patch("/api/surfaces/parede", json={"color": color})
    assert r.status_code == 200
    _, proj = state.snapshot()
    assert proj.surfaces[0].color.saturation == pytest.approx(1.3)

    assert local.delete("/api/color-presets/parede-da-igreja").status_code == 200
    assert local.delete("/api/color-presets/parede-da-igreja").status_code == 404
    assert (tmp_path / "cfg" / "color-presets.json").is_file()
