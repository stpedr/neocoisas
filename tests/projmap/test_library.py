"""Galeria: biblioteca de pastas (ex.: Google Drive sincronizado), miniaturas, importação e sugestões."""

import numpy as np
import pytest

pytest.importorskip("fastapi")
cv2 = pytest.importorskip("cv2")
from fastapi.testclient import TestClient  # noqa: E402

from projmap.core.project import Surface, Warp  # noqa: E402
from projmap.core.state import ProjectState  # noqa: E402
from projmap.core.store import ProjectStore  # noqa: E402
from projmap.library import Library  # noqa: E402
from projmap.master.app import create_app  # noqa: E402
from projmap.suggest import MediaRef, suggest_all, suggest_for_surface  # noqa: E402


def _imwrite(path, img):
    """cv2.imwrite não aceita caminho com acento no Windows (e pastas do Drive têm)."""
    ok, buf = cv2.imencode(path.suffix, img)
    path.write_bytes(buf.tobytes())


def _make_video(path, size=(320, 180), n=12):
    av = pytest.importorskip("av")
    with av.open(str(path), "w") as out:
        try:
            st = out.add_stream("libx264", rate=12)
        except Exception:  # noqa: BLE001
            st = out.add_stream("mpeg4", rate=12)
        st.width, st.height, st.pix_fmt = size[0], size[1], "yuv420p"
        for i in range(n):
            img = np.full((size[1], size[0], 3), (i * 20) % 255, np.uint8)
            for pkt in st.encode(av.VideoFrame.from_ndarray(img, format="rgb24")):
                out.mux(pkt)
        for pkt in st.encode():
            out.mux(pkt)


@pytest.fixture
def drive(tmp_path):
    """Pasta no formato do Drive sincronizado: subpastas com fotos, GIF e vídeo."""
    root = tmp_path / "Meu Drive" / "Projeção"
    (root / "Natal").mkdir(parents=True)
    (root / "Fachada").mkdir(parents=True)
    _imwrite(root / "Natal" / "arvore_vertical.jpg", np.full((400, 200, 3), 90, np.uint8))  # 1:2
    _imwrite(root / "Fachada" / "panorama.png", np.full((200, 800, 3), 160, np.uint8))  # 4:1
    from PIL import Image

    frames = [Image.new("RGB", (100, 100), c) for c in ((255, 0, 0), (0, 0, 255))]
    frames[0].save(root / "Natal" / "neve.gif", save_all=True, append_images=frames[1:], duration=100, loop=0)
    _make_video(root / "Fachada" / "luzes.mp4")
    (root / "Fachada" / "notas.txt").write_text("ignorar")
    (root / ".oculta").mkdir()
    _imwrite(root / ".oculta" / "x.png", np.zeros((10, 10, 3), np.uint8))
    return root


def test_varredura_lista_so_midia_com_metadados(drive, tmp_path):
    lib = Library([str(drive)], tmp_path / "cache")
    items = {i.name: i for i in lib.scan()}
    assert set(items) == {"arvore_vertical.jpg", "panorama.png", "neve.gif", "luzes.mp4"}
    assert items["arvore_vertical.jpg"].folder == "Projeção/Natal"
    assert (items["panorama.png"].width, items["panorama.png"].height) == (800, 200)
    assert items["luzes.mp4"].kind == "video" and items["luzes.mp4"].width == 320
    assert items["neve.gif"].kind == "gif" and items["neve.gif"].duration > 0


def test_miniaturas_em_cache(drive, tmp_path):
    lib = Library([str(drive)], tmp_path / "cache")
    for it in lib.scan():
        data = lib.thumbnail(it.id)
        assert data[:2] == b"\xff\xd8"  # JPEG
    assert len(list((tmp_path / "cache" / "thumbs").glob("*.jpg"))) == 4


def test_pasta_inexistente_nao_quebra(tmp_path):
    assert Library([str(tmp_path / "nao-existe")], tmp_path / "c").scan() == []


# ---------------------------------------------------------------- sugestões
def test_sugere_pelo_formato():
    tall = MediaRef("lib:a", "arvore", "image", 200, 400)
    wide = MediaRef("lib:b", "panorama", "image", 800, 200)
    porta = [[0, 0], [100, 0], [100, 220], [0, 220]]  # vertical
    faixa = [[0, 0], [800, 0], [800, 200], [0, 200]]  # larga
    assert suggest_for_surface(porta, [wide, tall], 1920 * 1080)[0].name == "arvore"
    assert suggest_for_surface(faixa, [tall, wide], 1920 * 1080)[0].name == "panorama"


def test_sugerir_para_todas_evita_repetir():
    m1 = MediaRef("lib:a", "a", "video", 1920, 1080)
    m2 = MediaRef("lib:b", "b", "video", 1280, 720)
    q = [[0, 0], [1600, 0], [1600, 900], [0, 900]]
    out = suggest_all([("s1", q), ("s2", q)], [m1, m2], 1920 * 1080)
    assert {out["s1"]["pick"]["ref"], out["s2"]["pick"]["ref"]} == {"lib:a", "lib:b"}
    assert out["s1"]["pick"]["reasons"]


# ---------------------------------------------------------------- API
@pytest.fixture
def api(drive, tmp_path):
    state = ProjectState(ProjectStore.create(tmp_path / "s.projmap", "T"))

    def add(p):
        p.surfaces.append(Surface(id="porta", node_id="proj-1", warp=Warp(base=[[100, 100], [300, 100], [300, 540], [100, 540]])))
        return p

    state.update(add)
    app = create_app(state, library_roots=[str(drive)], save_library_config=False)
    return TestClient(app, client=("127.0.0.1", 5000)), TestClient(app), state


def test_api_lista_miniatura_importa_sem_duplicar(api):
    local, _, state = api
    lib = local.get("/api/library").json()
    assert lib["can_edit_roots"] and len(lib["items"]) == 4 and "Projeção/Natal" in lib["folders"]
    item = next(i for i in lib["items"] if i["name"] == "arvore_vertical.jpg")
    assert local.get(f"/api/library/{item['id']}/thumb").headers["content-type"] == "image/jpeg"
    r1 = local.post(f"/api/library/{item['id']}/import").json()
    r2 = local.post(f"/api/library/{item['id']}/import").json()
    assert r1["item"]["sha256"] == r2["item"]["sha256"]
    assert len(state.store.load().media) == 1
    sha = r1["item"]["sha256"]
    assert local.get(f"/api/media/{sha}/thumb").status_code == 200
    info = local.get("/api/media-info").json()["items"][0]
    assert (info["width"], info["height"]) == (200, 400)


def test_api_pastas_so_no_mestre(api, tmp_path):
    local, remote, _ = api
    assert remote.put("/api/library/roots", json={"roots": [str(tmp_path)]}).status_code == 403
    assert local.put("/api/library/roots", json={"roots": [str(tmp_path / "nada")]}).status_code == 422
    assert remote.get("/api/library").json()["can_edit_roots"] is False


def test_api_sugestoes(api):
    local, _, _ = api
    s = local.post("/api/suggest", json={}).json()["suggestions"]["porta"]
    assert s["pick"]["name"] == "arvore_vertical.jpg"  # porta vertical ← imagem vertical
    assert s["pick"]["ref"].startswith("lib:")
