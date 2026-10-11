"""API do mestre: edição do projeto, uploads, toggles de saída e exportação."""

import io
import zipfile

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from projmap.core.state import ProjectState  # noqa: E402
from projmap.core.store import ProjectStore  # noqa: E402
from projmap.master.app import create_app  # noqa: E402

QUAD = [[100, 100], [500, 120], [520, 400], [90, 380]]


@pytest.fixture
def client(tmp_path):
    store = ProjectStore.create(tmp_path / "show.projmap", "Teste")
    state = ProjectState(store)
    return TestClient(create_app(state)), state


def _gif_bytes():
    from PIL import Image

    buf = io.BytesIO()
    frames = [Image.new("RGB", (4, 4), c) for c in ((255, 0, 0), (0, 0, 255))]
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return buf.getvalue()


def test_get_e_put_projeto_com_superficie(client):
    c, state = client
    data = c.get("/api/project").json()
    project = data["project"]
    project["surfaces"].append({"id": "parede", "node_id": "proj-1", "warp": {"base": QUAD},
                                "source": {"kind": "test"}})
    r = c.put("/api/project", json={"project": project})
    assert r.status_code == 200 and r.json()["revision"] == data["revision"] + 1
    assert state.store.load().surfaces[0].id == "parede"


def test_put_recusa_quad_cruzado_com_mensagem_legivel(client):
    c, state = client
    project = c.get("/api/project").json()["project"]
    project["surfaces"].append({"id": "x", "node_id": "proj-1",
                                "warp": {"base": [[0, 0], [300, 120], [300, 0], [0, 80]]}})
    r = c.put("/api/project", json={"project": project})
    assert r.status_code == 422
    assert any("cruzado" in m for m in r.json()["detail"])
    assert state.store.load().surfaces == []  # nada foi gravado


def test_put_nao_aceita_midia_ou_foto_inventada(client):
    c, _ = client
    project = c.get("/api/project").json()["project"]
    sha = "c" * 64
    project["media"][sha] = {"sha256": sha, "filename": "x.mp4", "ext": ".mp4", "kind": "video"}
    assert c.put("/api/project", json={"project": project}).status_code == 422
    project = c.get("/api/project").json()["project"]
    project["nodes"][0]["photo"] = "../../../etc/passwd"
    assert c.put("/api/project", json={"project": project}).status_code == 422


def test_upload_de_gif_e_uso_numa_superficie(client):
    c, state = client
    r = c.post("/api/media", files={"file": ("loop.gif", _gif_bytes(), "image/gif")})
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["kind"] == "gif"
    assert c.get(f"/media/{item['sha256']}").content == _gif_bytes()

    project = c.get("/api/project").json()["project"]
    project["surfaces"].append({"id": "s1", "node_id": "proj-1", "warp": {"base": QUAD},
                                "source": {"kind": "gif", "media": item["sha256"]}})
    assert c.put("/api/project", json={"project": project}).status_code == 200
    assert state.snapshot()[1].surfaces[0].source.media == item["sha256"]


def test_upload_formato_invalido(client):
    c, _ = client
    r = c.post("/api/media", files={"file": ("planilha.xlsx", b"abc", "application/octet-stream")})
    assert r.status_code == 422


def test_foto_do_no_upload_e_download(client):
    c, state = client
    r = c.post("/api/nodes/proj-1/photo", files={"file": ("parede.jpg", b"\xff\xd8\xff-foto", "image/jpeg")})
    assert r.status_code == 200
    assert state.snapshot()[1].nodes[0].photo == "captures/proj-1/photo.jpg"
    assert c.get("/api/nodes/proj-1/photo").content == b"\xff\xd8\xff-foto"
    assert c.post("/api/nodes/nao-existe/photo", files={"file": ("a.jpg", b"x", "image/jpeg")}).status_code == 404


def test_patch_output_toggles(client):
    c, state = client
    r = c.patch("/api/nodes/proj-1/output", json={"pattern": "grid", "show_outlines": True, "intensity": 0.4})
    assert r.status_code == 200
    out = state.snapshot()[1].nodes[0].output
    assert (out.pattern, out.show_outlines, out.intensity) == ("grid", True, 0.4)
    assert c.patch("/api/nodes/proj-1/output", json={"intensity": 3}).status_code == 422
    assert c.patch("/api/nodes/proj-1/output", json={"inventado": 1}).status_code == 422


def test_exportar_pmz(client):
    c, _ = client
    c.post("/api/media", files={"file": ("loop.gif", _gif_bytes(), "image/gif")})
    r = c.get("/api/project/export")
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "project.json" in names and any(n.startswith("media/") for n in names)


def test_health_e_raiz_sem_ui(client):
    c, _ = client
    assert c.get("/api/health").json()["ok"] is True
    assert "UI não compilada" in c.get("/").json()["msg"]
