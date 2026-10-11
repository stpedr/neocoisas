"""F3: detecção clássica de superfícies (OpenCV, sem torch) em imagens sintéticas."""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from projmap.detect import get_detector  # noqa: E402
from projmap.detect.classic import drop_nested, fit_quad, order_quad  # noqa: E402
from projmap.detect.base import Candidate  # noqa: E402

W, H = 900, 700


def _scene(quads_colors, occluder=False, seed=0):
    """Parede cinza com ruído + quads coloridos em perspectiva (com textura leve)."""
    rng = np.random.RandomState(seed)
    img = np.full((H, W, 3), (150, 150, 155), np.uint8)
    img = cv2.add(img, rng.randint(0, 12, img.shape).astype(np.uint8))
    for quad, color in quads_colors:
        layer = np.zeros_like(img)
        cv2.fillConvexPoly(layer, np.array(quad, np.int32), color)
        noise = rng.randint(0, 14, img.shape).astype(np.uint8)
        mask = layer.any(axis=2)
        img[mask] = cv2.add(layer, noise)[mask]
    if occluder:
        # "fita" escura vertical cruzando o primeiro quad (algo na frente)
        x = int(np.mean([p[0] for p in quads_colors[0][0]]))
        cv2.rectangle(img, (x - 6, 0), (x + 6, H), (30, 30, 30), -1)
    return img


DOOR = [(300, 150), (520, 170), (510, 640), (290, 620)]  # porta em perspectiva
PANEL = [(620, 260), (840, 250), (850, 420), (630, 440)]


def _corner_error(found, truth):
    f = np.array(found) * [W, H]
    return float(np.max(np.linalg.norm(f - np.array(truth, float), axis=1)) / np.hypot(W, H))


def _best(cands, truth):
    return min(cands, key=lambda c: _corner_error(c.quad, truth))


def test_quads_em_perspectiva_com_erro_de_canto_menor_que_1pct():
    img = _scene([(DOOR, (40, 110, 170)), (PANEL, (180, 60, 40))])
    cands = get_detector("classic").detect(img, sensitivity=0.5)
    assert len(cands) >= 2
    for truth in (DOOR, PANEL):
        assert _corner_error(_best(cands, truth).quad, truth) < 0.01


def test_superficie_cortada_por_objeto_na_frente_vira_uma_so():
    img = _scene([(DOOR, (40, 110, 170))], occluder=True)
    cands = get_detector("classic").detect(img, sensitivity=0.5)
    best = _best(cands, DOOR)
    assert _corner_error(best.quad, DOOR) < 0.015
    assert best.score > 0.8


def test_saida_normalizada_ordenada_e_serializavel():
    img = _scene([(DOOR, (40, 110, 170))])
    c = _best(get_detector("classic").detect(img), DOOR)
    q = np.array(c.quad)
    assert ((q >= -0.01) & (q <= 1.01)).all()
    tl, tr, br, bl = q
    assert tl[0] < tr[0] and bl[0] < br[0] and tl[1] < bl[1] and tr[1] < br[1]
    d = c.to_dict()
    assert set(d) >= {"quad", "polygon", "score", "area", "label", "color"}


def test_imagem_lisa_nao_inventa_superficies_pequenas():
    img = np.full((H, W, 3), 128, np.uint8)
    cands = get_detector("classic").detect(img)
    assert all(c.area > 0.5 for c in cands)  # no máximo "a parede inteira"


def test_order_quad():
    pts = np.array([[10, 10], [0, 100], [100, 0], [110, 110]], float)
    assert order_quad(pts).tolist() == [[10, 10], [100, 0], [110, 110], [0, 100]]


def test_fit_quad_em_retangulo_tem_nota_alta():
    region = np.zeros((200, 200), np.uint8)
    cv2.fillConvexPoly(region, np.array([[20, 30], [180, 40], [170, 170], [30, 160]], np.int32), 1)
    cnt, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    _, score = fit_quad(cnt[0], region)
    assert score > 0.97


def test_drop_nested_remove_o_menor_contido():
    big = Candidate(quad=[(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)], polygon=[], area=0.6, score=0.9)
    small = Candidate(quad=[(0.3, 0.3), (0.5, 0.3), (0.5, 0.5), (0.3, 0.5)], polygon=[], area=0.04, score=0.95)
    other = Candidate(quad=[(0.92, 0.1), (0.99, 0.1), (0.99, 0.3), (0.92, 0.3)], polygon=[], area=0.01, score=0.9)
    out = drop_nested([small, big, other], (100, 100))
    assert [c.area for c in out] == [0.6, 0.01]
    assert [c.label for c in out] == ["Região 1", "Região 2"]


def test_factory():
    assert get_detector("classic").name == "classic"
    with pytest.raises(ValueError):
        get_detector("nao-existe")


# ---------------------------------------------------------------- API do mestre
def test_api_detect(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from projmap.core.state import ProjectState
    from projmap.core.store import ProjectStore
    from projmap.master.app import create_app

    state = ProjectState(ProjectStore.create(tmp_path / "s.projmap", "T"))
    c = TestClient(create_app(state))
    assert c.post("/api/nodes/proj-1/detect", json={}).status_code == 422  # sem foto ainda

    ok, png = cv2.imencode(".png", _scene([(DOOR, (40, 110, 170))]))
    c.post("/api/nodes/proj-1/photo", files={"file": ("foto.png", png.tobytes(), "image/png")})
    r = c.post("/api/nodes/proj-1/detect", json={"sensitivity": 0.5})
    assert r.status_code == 200
    cands = r.json()["candidates"]
    assert cands and min(_corner_error(cd["quad"], DOOR) for cd in cands) < 0.01
    rev = state.revision
    assert c.post("/api/nodes/proj-1/detect", json={"detector": "x"}).status_code == 422
    assert state.revision == rev  # detectar não altera o projeto
