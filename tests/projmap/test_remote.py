"""Remote no celular (F6): token de pareamento, comandos por superfície e looks."""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from projmap.core.state import ProjectState  # noqa: E402
from projmap.core.store import ProjectStore  # noqa: E402
from projmap.master.app import create_app  # noqa: E402
from projmap.master.remote import remote_url  # noqa: E402

QUAD = [[100, 100], [500, 120], [520, 400], [90, 380]]
TOKEN = "segredo-123"


def _state(tmp_path, name="show"):
    store = ProjectStore.create(tmp_path / f"{name}.projmap", "Teste")
    state = ProjectState(store)

    def add(p):
        from projmap.core.project import Surface, Warp

        p.surfaces.append(Surface(id="parede", node_id="proj-1", warp=Warp(base=QUAD)))
        p.surfaces.append(Surface(id="coluna", node_id="proj-1", warp=Warp(base=QUAD)))
        return p

    state.update(add)
    return state


@pytest.fixture
def remote(tmp_path):
    """Cliente "de fora" (TestClient se apresenta como host 'testclient')."""
    state = _state(tmp_path)
    return TestClient(create_app(state, token=TOKEN)), state


@pytest.fixture
def local(tmp_path):
    state = _state(tmp_path, "local")
    return TestClient(create_app(state, token=TOKEN), client=("127.0.0.1", 50000)), state


# ---------------------------------------------------------------- token
def test_sem_token_nenhum_comando_aceito(remote):
    c, state = remote
    rev = state.revision
    assert c.get("/api/project").status_code == 401
    assert c.patch("/api/nodes/proj-1/output", json={"blackout": True}).status_code == 401
    assert c.patch("/api/surfaces/parede", json={"visible": False}).status_code == 401
    assert c.post("/api/looks", json={"name": "x"}).status_code == 401
    assert c.get("/api/project", headers={"X-ProjMap-Token": "errado"}).status_code == 401
    assert state.revision == rev


def test_com_token_no_cabecalho_ou_query(remote):
    c, _ = remote
    assert c.get("/api/project", headers={"X-ProjMap-Token": TOKEN}).status_code == 200
    assert c.get(f"/api/project?token={TOKEN}").status_code == 200


def test_ui_estatica_e_publica(remote):
    c, _ = remote
    assert c.get("/").status_code == 200


def test_loopback_dispensa_token(local):
    c, _ = local
    assert c.get("/api/project").status_code == 200


def test_sem_token_configurado_modo_local_da_f1(tmp_path):
    c = TestClient(create_app(_state(tmp_path)))
    assert c.get("/api/project").status_code == 200


def test_websocket_do_sensor_exige_token(remote):
    c, _ = remote
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/api/interact/phone") as ws:
            ws.receive_text()


# ---------------------------------------------------------------- pareamento
def test_pair_so_no_mestre(remote, local):
    c, _ = remote
    assert c.get("/api/remote/pair", headers={"X-ProjMap-Token": TOKEN}).status_code == 403
    lc, _ = local
    data = lc.get("/api/remote/pair").json()
    assert data["token"] == TOKEN and data["url"].endswith(f"/remote/#t={TOKEN}")


def test_remote_url():
    assert remote_url("192.168.0.10", 8100, "abc") == "http://192.168.0.10:8100/remote/#t=abc"
    assert remote_url("127.0.0.1", 8100, None) == "http://localhost:8100/remote/"
    assert remote_url("0.0.0.0", 8100, "abc").startswith("http://")


# ---------------------------------------------------------------- comandos
H = {"X-ProjMap-Token": TOKEN}


def test_patch_surface_visibilidade_opacidade_fonte(remote):
    c, state = remote
    r = c.patch("/api/surfaces/parede", headers=H,
                json={"visible": False, "opacity": 0.4, "source": {"kind": "color", "color": [255, 0, 0]}})
    assert r.status_code == 200
    s = state.store.load().surfaces[0]
    assert (s.visible, s.opacity, s.source.kind, s.source.color) == (False, 0.4, "color", (255, 0, 0))


def test_patch_surface_recusa_midia_inexistente(remote):
    c, _ = remote
    r = c.patch("/api/surfaces/parede", headers=H, json={"source": {"kind": "video", "media": "a" * 64}})
    assert r.status_code == 422


def test_patch_surface_404(remote):
    c, _ = remote
    assert c.patch("/api/surfaces/nada", headers=H, json={"visible": False}).status_code == 404


def test_blackout_e_dimmer_pelo_remote(remote):
    c, state = remote
    r = c.patch("/api/nodes/proj-1/output", headers=H, json={"blackout": True, "intensity": 0.5})
    assert r.status_code == 200
    out = state.store.load().nodes[0].output
    assert out.blackout is True and out.intensity == 0.5


# ---------------------------------------------------------------- looks
def test_salvar_e_recuperar_look(remote):
    c, state = remote
    c.patch("/api/surfaces/parede", headers=H, json={"source": {"kind": "color", "color": [0, 0, 255]}})
    look = c.post("/api/looks", headers=H, json={"name": "Azul"}).json()["project"]["looks"][0]
    assert look["name"] == "Azul"

    c.patch("/api/surfaces/parede", headers=H, json={"visible": False, "source": {"kind": "test"}})
    r = c.post(f"/api/looks/{look['id']}/recall", headers=H).json()
    assert r["skipped"] == []
    s = state.store.load().surfaces[0]
    assert s.visible is True and s.source.kind == "color" and s.source.color == (0, 0, 255)


def test_recall_ignora_superficie_apagada(remote):
    c, state = remote
    look_id = c.post("/api/looks", headers=H, json={}).json()["project"]["looks"][0]["id"]

    def drop(p):
        p.surfaces = [s for s in p.surfaces if s.id != "coluna"]
        return p

    state.update(drop)
    r = c.post(f"/api/looks/{look_id}/recall", headers=H).json()
    assert len(r["skipped"]) == 1 and r["skipped"][0].startswith("coluna")


def test_apagar_look(remote):
    c, state = remote
    look_id = c.post("/api/looks", headers=H, json={"name": "x"}).json()["project"]["looks"][0]["id"]
    assert c.delete(f"/api/looks/{look_id}", headers=H).status_code == 200
    assert state.store.load().looks == []
    assert c.delete(f"/api/looks/{look_id}", headers=H).status_code == 404
