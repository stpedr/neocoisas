"""Camada interativa: olhar, comportamentos, NLP, sensores/saídas OSC, render e API."""

import json
import math
import socket
import threading
import time

import numpy as np
import pytest

pytest.importorskip("cv2")

from projmap.interact.nlp import keyword_scene, scene_from_text  # noqa: E402
from projmap.interact.scene import (  # noqa: E402
    PRESETS,
    ChasePlayer,
    EntityGroup,
    FleePlayer,
    FreezeWhenWatched,
    SceneSpec,
    SeekGaze,
)
from projmap.interact.sim import Simulation  # noqa: E402
from projmap.interact.world import Player, gaze_of  # noqa: E402

A = 16 / 9
FACING = Player(x=A / 2, distance=1.0, yaw=0.0)
BACK = Player(x=A / 2, distance=1.0, yaw=math.pi)


def _scene(*behaviors, count=1, size=0.1, spawn="edges", **kw):
    return SceneSpec(groups=[EntityGroup(sprite="ghost", count=count, size=size, spawn=spawn,
                                         behaviors=list(behaviors))], **kw)


def _place(sim, *xy):
    for e, (x, y) in zip(sim.entities, xy):
        e.x, e.y = x, y


# ------------------------------------------------------------------ olhar
def test_regiao_do_olhar_segue_a_rotacao_da_cabeca():
    fov = math.radians(60)
    g0 = gaze_of(FACING, fov)
    assert g0.active and g0.center == pytest.approx((A / 2, 0.45))
    assert g0.radius == pytest.approx(math.tan(math.radians(30)))
    g30 = gaze_of(Player(x=A / 2, distance=1.0, yaw=math.radians(30)), fov)
    assert g30.center[0] == pytest.approx(A / 2 + math.tan(math.radians(30)))
    assert g30.radius > g0.radius  # olhando de lado o cone abre mais na parede
    assert not gaze_of(BACK, fov).active
    assert not gaze_of(Player(tracked=False), fov).active
    assert not gaze_of(Player(face_visible=False), fov).active  # webcam: sem rosto = de costas


# ------------------------------------------------------- mecânica dos fantasmas
def test_fantasma_persegue_quando_voce_esta_de_costas():
    sim = Simulation(_scene(ChasePlayer(speed=0.2), FreezeWhenWatched(), on_caught=[]))
    _place(sim, (0.1, 0.45))
    d0 = math.dist((0.1, 0.45), BACK.anchor)
    for _ in range(30):
        snap = sim.step(1 / 30, [BACK])
    e = snap.entities[0]
    assert e.state == "move"
    assert math.dist((e.x, e.y), BACK.anchor) == pytest.approx(d0 - 0.2, abs=0.01)


def test_fantasma_olhado_para_e_cobre_o_rosto_e_os_de_fora_continuam():
    sim = Simulation(_scene(ChasePlayer(speed=0.2), FreezeWhenWatched(shy=True), count=2, on_caught=[]))
    # um dentro da região do olhar (raio ~0.577), outro bem fora
    _place(sim, (A / 2 + 0.3, 0.45), (0.05, 0.9))
    snap = sim.step(1 / 30, [FACING])
    inside, outside = snap.entities
    assert inside.state == "shy" and (inside.x, inside.y) == pytest.approx((A / 2 + 0.3, 0.45))
    assert outside.state == "move"
    # virou de costas: o de dentro volta a andar
    snap = sim.step(1 / 30, [BACK])
    assert snap.entities[0].state == "move"


def test_pegou_dispara_evento_flash_e_reinicia():
    sim = Simulation(_scene(ChasePlayer(speed=0.5), on_caught=["flash", "reset"], catch_radius=0.05))
    _place(sim, (A / 2 + 0.2, 0.45))
    caught = []
    for _ in range(40):
        snap = sim.step(1 / 30, [BACK])
        caught += snap.events
    assert [ev.name for ev in caught][:1] == ["caught"]
    assert snap.flash < 1.0  # decai
    # reiniciou: voltou para a borda, longe da pessoa
    e = snap.entities[0]
    assert math.dist((e.x, e.y), BACK.anchor) > 0.3


def test_ninguem_rastreado_nao_pega_ninguem():
    sim = Simulation(_scene(ChasePlayer(speed=1.0), catch_radius=0.5))
    snap = None
    for _ in range(30):
        snap = sim.step(1 / 30, [Player(x=A / 2, tracked=False)])
    assert all(not s.events for s in [snap])


def test_fugir_e_seguir_o_olhar():
    flee = Simulation(_scene(FleePlayer(speed=0.5, radius=0.6), spawn="center", on_caught=[]))
    _place(flee, (A / 2 + 0.1, 0.45))
    for _ in range(30):
        snap = flee.step(1 / 30, [FACING])
    assert math.dist((snap.entities[0].x, snap.entities[0].y), FACING.anchor) > 0.3

    seek = Simulation(_scene(SeekGaze(speed=0.6), on_caught=[]))
    _place(seek, (0.1, 0.1))
    looking_right = Player(x=A / 2, distance=1.0, yaw=math.radians(25))
    for _ in range(90):
        snap = seek.step(1 / 30, [looking_right])
    g = gaze_of(looking_right, math.radians(60))
    assert math.dist((snap.entities[0].x, snap.entities[0].y), g.center) < g.radius


def test_simulacao_e_deterministica_e_fica_na_parede():
    def run():
        sim = Simulation(PRESETS["cardume"])
        for _ in range(120):
            snap = sim.step(1 / 60, [FACING])
        return [(round(e.x, 9), round(e.y, 9)) for e in snap.entities]

    a, b = run(), run()
    assert a == b
    assert all(0 <= x <= A and 0 <= y <= 1 for x, y in a)


def test_separacao_evita_fantasmas_empilhados():
    sim = Simulation(_scene(ChasePlayer(speed=0.05), count=4, size=0.16, on_caught=[]))
    _place(sim, *[(0.4, 0.45)] * 4)  # todos no mesmo ponto
    for _ in range(60):
        snap = sim.step(1 / 30, [Player(x=A / 2, tracked=False)])
    pts = [(e.x, e.y) for e in snap.entities]
    dmin = min(math.dist(p, q) for i, p in enumerate(pts) for q in pts[i + 1:])
    assert dmin > 0.05


# --------------------------------------------------------------------- NLP
PEDIDO = ("reproduzir os fantasmas do mario, que se você olha pra frente eles param "
          "e se você vira eles buscam você")


def test_fallback_entende_o_pedido_dos_fantasmas():
    spec = keyword_scene(PEDIDO)
    g = spec.groups[0]
    kinds = {b.type for b in g.behaviors}
    assert g.sprite == "ghost"
    assert {"chase_player", "freeze_when_watched"} <= kinds
    assert next(b for b in g.behaviors if b.type == "freeze_when_watched").shy
    assert "caught" not in spec.title.lower() and "mario" not in spec.title.lower()


@pytest.mark.parametrize("texto, sprite, comp, n", [
    ("20 peixes azuis que fogem de mim", "fish", "flee_player", 20),
    ("vaga-lumes que vão para onde eu olho", "firefly", "seek_gaze", 40),
    ("três bolas vermelhas flutuando devagar", "orb", "wander", 3),
])
def test_fallback_outras_cenas(texto, sprite, comp, n):
    g = keyword_scene(texto).groups[0]
    assert g.sprite == sprite and comp in {b.type for b in g.behaviors} and g.count == n


class FakeLLM:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        ans = self.answers.pop(0)
        if isinstance(ans, Exception):
            raise ans
        return ans


GOOD = json.dumps({"title": "Orbes", "groups": [{"sprite": "orb", "count": 7,
                                                "behaviors": [{"type": "wander", "speed": 0.1}]}]})


def test_llm_valido_e_usado():
    llm = FakeLLM("```json\n" + GOOD + "\n```")
    res = scene_from_text("orbes vagando", llm)
    assert res.source == "llm" and res.spec.groups[0].count == 7
    assert "orbes vagando" in llm.prompts[0]


def test_llm_errado_recebe_os_erros_e_corrige():
    bad = json.dumps({"groups": [{"sprite": "dragao", "behaviors": [{"type": "voar"}]}]})
    llm = FakeLLM(bad, GOOD)
    res = scene_from_text("orbes", llm)
    assert res.source == "llm" and len(llm.prompts) == 2
    assert "sprite" in llm.prompts[1]  # o erro de validação foi devolvido ao LLM


def test_llm_fora_do_ar_cai_no_fallback_e_avisa():
    res = scene_from_text(PEDIDO, FakeLLM(ConnectionError("ollama offline")))
    assert res.source == "fallback"
    assert any("indisponível" in n for n in res.notes)
    assert res.spec.groups[0].sprite == "ghost"


def test_comportamento_inventado_e_recusado_pelo_esquema():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SceneSpec.model_validate({"groups": [{"behaviors": [{"type": "explodir_parede"}]}]})


# -------------------------------------------------------------- pose da cabeça
@pytest.mark.parametrize("yaw_deg", [-35, -15, 0, 20, 40])
def test_yaw_da_cabeca_por_solvepnp(yaw_deg):
    import cv2

    from projmap.interact.sensors import FACE_MODEL_3D, head_yaw_from_points

    w, h = 640, 480
    cam = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float64)
    # Rosto a 60 cm olhando para a câmera, depois girado em yaw.
    flip = cv2.Rodrigues(np.array([math.pi, 0.0, 0.0]))[0]  # modelo y-cima → imagem y-baixo, nariz → câmera
    yaw = cv2.Rodrigues(np.array([0.0, math.radians(yaw_deg), 0.0]))[0]
    rvec = cv2.Rodrigues(yaw @ flip)[0]
    pts, _ = cv2.projectPoints(FACE_MODEL_3D, rvec, np.array([0.0, 0.0, 600.0]), cam, None)
    est = head_yaw_from_points(pts.reshape(-1, 2), w, h)
    # Rotação +y da câmera vira o rosto para a ESQUERDA da imagem; a convenção do
    # sensor é yaw > 0 = rosto apontando para a DIREITA da imagem ⇒ sinal oposto.
    assert math.degrees(est) == pytest.approx(-yaw_deg, abs=3)


def test_yaw_sinal_consistente():
    """Girar para um lado e para o outro dá sinais opostos (o espelhamento é config)."""
    import cv2

    from projmap.interact.sensors import FACE_MODEL_3D, head_yaw_from_points

    w, h = 640, 480
    cam = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float64)
    flip = cv2.Rodrigues(np.array([math.pi, 0.0, 0.0]))[0]

    def est(deg):
        r = cv2.Rodrigues(cv2.Rodrigues(np.array([0.0, math.radians(deg), 0.0]))[0] @ flip)[0]
        pts, _ = cv2.projectPoints(FACE_MODEL_3D, r, np.array([0.0, 0.0, 600.0]), cam, None)
        return head_yaw_from_points(pts.reshape(-1, 2), w, h)

    assert est(25) * est(-25) < 0


# ------------------------------------------------------------------ OSC
def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_saida_osc_para_o_touchdesigner():
    pytest.importorskip("pythonosc")
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import ThreadingOSCUDPServer

    from projmap.interact.outputs import OscOutput

    got = []
    disp = Dispatcher()
    disp.set_default_handler(lambda addr, *args: got.append((addr, args)))
    server = ThreadingOSCUDPServer(("127.0.0.1", 0), disp)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = OscOutput("127.0.0.1", server.server_address[1])
        sim = Simulation(PRESETS["fantasmas-timidos"])
        out.send(sim.step(1 / 30, [FACING]))
        # Espera TODAS as mensagens: o servidor processa cada datagrama numa thread,
        # então a ordem de chegada em `got` não é garantida.
        deadline = time.time() + 3
        while time.time() < deadline and not (
            sum(a == "/projmap/entity" for a, _ in list(got)) >= 5
            and {"/projmap/scene", "/projmap/frame", "/projmap/player"} <= {a for a, _ in list(got)}
        ):
            time.sleep(0.01)
    finally:
        server.shutdown()
        server.server_close()
    addrs = [a for a, _ in got]
    assert "/projmap/scene" in addrs and "/projmap/frame" in addrs and "/projmap/player" in addrs
    ents = [args for a, args in got if a == "/projmap/entity"]
    assert len(ents) == 5
    eid, group, x, y, state, heading, size = ents[0]
    assert group == "fantasmas" and 0 <= x <= 1 and 0 <= y <= 1 and state in {"move", "shy", "frozen", "idle"}


def test_sensor_osc_recebe_pessoa_do_kinect():
    pytest.importorskip("pythonosc")
    from pythonosc.udp_client import SimpleUDPClient

    from projmap.interact.sensors import OscSensor

    sensor = OscSensor(aspect=A, host="127.0.0.1", port=0, timeout=5)
    try:
        c = SimpleUDPClient("127.0.0.1", sensor.port)
        c.send_message("/player", [0, 0.25, 1.5, 180.0, 1])
        c.send_message("/player/1/x", 0.75)
        c.send_message("/player/1/face", 0)
        def ready():
            ps = {p.id: p for p in sensor.players()}
            return len(ps) == 2 and ps[1].face_visible is False and ps[1].x == pytest.approx(0.75 * A)

        deadline = time.time() + 3
        while time.time() < deadline and not ready():
            time.sleep(0.01)
        ps = {p.id: p for p in sensor.players()}
    finally:
        sensor.close()
    assert ps[0].x == pytest.approx(0.25 * A) and ps[0].distance == 1.5
    assert not ps[0].facing_wall  # yaw 180 = de costas
    assert ps[1].x == pytest.approx(0.75 * A) and ps[1].face_visible is False and not ps[1].facing_wall


# ------------------------------------------------------------------ render
def test_render_desenha_fantasmas_e_timido_e_diferente():
    from projmap.interact.render import render_snapshot

    spec = _scene(ChasePlayer(speed=0.1), FreezeWhenWatched(shy=True), size=0.2, on_caught=[])
    sim = Simulation(spec)
    _place(sim, (A / 2, 0.45))
    shy = render_snapshot(sim.step(1 / 30, [FACING]), (320, 180))
    sim2 = Simulation(spec)
    _place(sim2, (A / 2, 0.45))
    moving = render_snapshot(sim2.step(1 / 30, [BACK]), (320, 180))
    assert shy.shape == (180, 320, 4)
    cx, cy = 160, 81
    assert moving[cy - 10:cy + 10, cx - 10:cx + 10, :3].mean() > 60  # tem fantasma no centro
    assert np.abs(shy.astype(int) - moving.astype(int)).sum() > 1000  # tímido ≠ andando
    assert moving[5, 5, :3].max() == 0  # fundo preto = sem luz


def test_projmap_superficie_interativa_renderiza(gl_ctx):
    from projmap.core.geometry import rect_quad
    from projmap.core.project import Node, Project, Surface
    from projmap.interact.runtime import InteractionRuntime
    from projmap.interact.sensors import SimSensor
    from projmap.node.renderer import render_offscreen

    rt = InteractionRuntime(PRESETS["fantasmas-timidos"], SimSensor(script=None)).start()
    try:
        rt.step(1 / 30)
        project = Project(nodes=[Node(id="p", output={"width": 320, "height": 180})],
                          surfaces=[Surface(id="s", node_id="p", warp={"base": rect_quad(0, 0, 320, 180)},
                                            source={"kind": "interactive"})])
        img = render_offscreen(project, "p", lambda s: None, lambda r: None, ctx=gl_ctx)
    finally:
        rt.stop()
    assert img.max() > 100  # fantasmas acesos


# --------------------------------------------------------------------- API
def test_api_gera_cena_por_texto_e_controla_pessoa(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from projmap.core.state import ProjectState
    from projmap.core.store import ProjectStore
    from projmap.interact.runtime import InteractionRuntime
    from projmap.interact.sensors import SimSensor
    from projmap.master.app import create_app

    rt = InteractionRuntime(PRESETS["cardume"], SimSensor(script=None), scene_file=tmp_path / "scene.json")
    app = create_app(ProjectState(ProjectStore.create(tmp_path / "p")), runtime=rt,
                     nlp_client_factory=lambda: FakeLLM(ConnectionError("sem llm")))
    c = TestClient(app)
    r = c.post("/api/interact/generate", json={"text": PEDIDO})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fallback" and body["spec"]["groups"][0]["sprite"] == "ghost"
    assert (tmp_path / "scene.json").is_file()  # cena persiste

    assert c.post("/api/interact/player", json={"x": 0.2, "yaw_deg": 180}).status_code == 200
    rt.step(1 / 30)
    st = c.get("/api/interact/state").json()
    assert st["players"][0]["watching"] is False and st["players"][0]["x"] == pytest.approx(0.2)
    assert len(st["entities"]) == 5

    assert c.post("/api/interact/presets/vaga-lumes").json()["spec"]["title"] == "Vaga-lumes do olhar"
    assert c.post("/api/interact/presets/nao-existe").status_code == 404
    bad = c.put("/api/interact/spec", json={"groups": [{"sprite": "dragao"}]})
    assert bad.status_code == 422
    assert c.post("/api/interact/sensor", json={"kind": "lidar"}).status_code == 422
