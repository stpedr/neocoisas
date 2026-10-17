"""Entradas ao vivo (vídeo/áudio) e efeitos reativos ao áudio (``Surface.fx``)."""

import math
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from projmap.core.project import AudioFx, AudioInput, Node, Project, SourceSpec, Surface, parse_project
from projmap.inputs import video as vin
from projmap.inputs.audio import AudioBus
from projmap.mapping.fx import NEUTRAL_FX, FxUniforms, apply_color_fx, compute_fx, hue_matrix
from projmap.node.tap import OutputTap

QUAD = [[0.0, 0.0], [320.0, 0.0], [320.0, 180.0], [0.0, 180.0]]
SILENCE = dict.fromkeys(("bass", "mid", "high", "level", "beat"), 0.0)


# ------------------------------------------------------------------ esquema
def test_projeto_antigo_continua_valido_com_padroes_neutros():
    p = parse_project({"nodes": [{"id": "p1"}], "surfaces": [{"id": "s1", "node_id": "p1", "warp": {"base": QUAD}}]})
    assert p.audio == AudioInput() and p.audio.device == "loopback"
    assert p.surfaces[0].fx == []


def test_fonte_capture_aceita_dispositivo_sem_midia():
    spec = SourceSpec(kind="capture", device="HD Webcam")
    assert spec.media is None and spec.device == "HD Webcam"
    with pytest.raises(ValidationError):
        SourceSpec(kind="capture", device="x" * 200)


@pytest.mark.parametrize("bad", [{"type": "pulse", "amount": 1.5}, {"type": "pulse", "amount": float("nan")},
                                 {"type": "explode"}, {"type": "pulse", "band": "subgrave"}])
def test_fx_invalido_e_recusado(bad):
    with pytest.raises(ValidationError):
        AudioFx.model_validate(bad)


def test_no_maximo_8_efeitos_por_superficie():
    with pytest.raises(ValidationError):
        Surface(id="s1", node_id="p1", warp={"base": QUAD}, fx=[AudioFx(type="pulse")] * 9)


def test_ganho_de_audio_tem_limite():
    with pytest.raises(ValidationError):
        AudioInput(gain=float("inf"))
    with pytest.raises(ValidationError):
        AudioInput(device="")


# ------------------------------------------------------------- compute_fx
def test_sem_audio_os_efeitos_sao_neutros():
    fx = [AudioFx(type=t, amount=1.0) for t in ("pulse", "hue", "zoom", "rgb_split", "strobe", "shake", "invert")]
    assert compute_fx(fx, SILENCE, 1.0) == NEUTRAL_FX


def test_pulse_segue_a_banda_escolhida():
    fx = [AudioFx(type="pulse", band="bass", amount=1.0)]
    assert compute_fx(fx, {**SILENCE, "high": 1.0}, 0).gain == 1.0
    assert compute_fx(fx, {**SILENCE, "bass": 0.5}, 0).gain == pytest.approx(1.75)


def test_strobe_no_envelope_de_batida_e_efeito_desligado_nao_conta():
    fx = [AudioFx(type="strobe", band="beat", amount=0.8), AudioFx(type="invert", amount=1.0, enabled=False)]
    u = compute_fx(fx, {**SILENCE, "beat": 1.0, "bass": 1.0}, 0)
    assert u.flash == pytest.approx(0.8) and u.invert == 0.0


def test_efeitos_do_mesmo_tipo_somam_e_satura():
    fx = [AudioFx(type="zoom", amount=0.7), AudioFx(type="zoom", amount=0.7)]
    assert compute_fx(fx, {**SILENCE, "bass": 1.0}, 0).zoom == pytest.approx(1.35)


def test_shake_oscila_no_tempo():
    fx = [AudioFx(type="shake", band="level", amount=1.0)]
    a = compute_fx(fx, {**SILENCE, "level": 1.0}, 0.0).shift
    b = compute_fx(fx, {**SILENCE, "level": 1.0}, 0.02).shift
    assert a != b and max(abs(v) for v in a + b) <= 0.03 + 1e-9


def test_matiz_preserva_cinza_e_gira_cores():
    assert np.allclose(np.array([0.4, 0.4, 0.4]) @ hue_matrix(1.0).T, 0.4, atol=1e-6)
    red = apply_color_fx(np.array([[1.0, 0.0, 0.0]]), FxUniforms(hue=2 * math.pi / 3))
    assert np.allclose(red, [[0.0, 1.0, 0.0]], atol=1e-5)  # 120° leva vermelho em verde


def test_inversao_e_flash():
    c = np.array([[0.2, 0.5, 1.0]], np.float32)
    assert np.allclose(apply_color_fx(c, FxUniforms(invert=1.0)), [[0.8, 0.5, 0.0]])
    assert np.allclose(apply_color_fx(c, FxUniforms(flash=1.0)), 1.0)


# --------------------------------------------------------- GPU × CPU (fx)
def _fx_project(tmp_path, checker, fx):
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "checker.png"
    cv2.imwrite(str(path), cv2.cvtColor(checker, cv2.COLOR_RGBA2BGRA))
    sha = "b" * 64
    project = Project(
        nodes=[Node(id="p1", output={"width": 320, "height": 180})],
        surfaces=[Surface(id="s1", node_id="p1", warp={"base": QUAD}, source={"kind": "image", "media": sha}, fx=fx)],
        media={sha: {"sha256": sha, "filename": "c.png", "ext": ".png", "kind": "image"}},
    )
    return project, (lambda _sha: path)


@pytest.mark.parametrize("fx", [
    [AudioFx(type="pulse", amount=0.6)],
    [AudioFx(type="hue", amount=0.5), AudioFx(type="invert", band="mid", amount=0.3)],
    [AudioFx(type="zoom", amount=0.8), AudioFx(type="rgb_split", band="high", amount=1.0)],
    [AudioFx(type="strobe", band="beat", amount=0.7)],
])
def test_gpu_aplica_fx_igual_a_referencia_cpu(gl_ctx, tmp_path, checker, fx):
    from projmap.mapping.warp import render_surface_cpu
    from projmap.node.renderer import render_offscreen

    levels = {"bass": 0.8, "mid": 0.5, "high": 0.9, "level": 0.6, "beat": 1.0}
    project, media = _fx_project(tmp_path, checker, fx)
    gpu = render_offscreen(project, "p1", media, lambda r: None, ctx=gl_ctx, t=0.5, audio_levels=lambda: levels)
    ref = render_surface_cpu((320, 180), QUAD, checker, fx=compute_fx(fx, levels, 0.5))
    cpu = (np.clip(ref[..., :3], 0, 1) * 255).round().astype(np.uint8)
    diff = np.abs(gpu.astype(int) - cpu.astype(int)).max(axis=-1)
    assert float((diff <= 12).mean()) > 0.98
    neutral = render_offscreen(project, "p1", media, lambda r: None, ctx=gl_ctx, audio_levels=lambda: SILENCE)
    assert np.abs(gpu.astype(int) - neutral.astype(int)).mean() > 3  # o efeito mudou a imagem


def test_renderer_liga_a_entrada_de_audio_so_quando_ha_efeito(gl_ctx, tmp_path, checker):
    from projmap.node.renderer import Renderer

    started = []
    project, media = _fx_project(tmp_path, checker, [])
    r = Renderer(gl_ctx, media, lambda _p: None, audio_levels=lambda: SILENCE, audio_ensure=started.append)
    try:
        r.sync(project, "p1")
        assert started == []
        project.surfaces[0].fx = [AudioFx(type="pulse")]
        project.audio = AudioInput(device="mic")
        r.sync(project, "p1")
        assert [s.device for s in started] == ["mic"]
    finally:
        r.release()


# ----------------------------------------------------------- AudioBus
class _FakeAnalyzer:
    instances: list["_FakeAnalyzer"] = []

    def __init__(self, device):
        self.device, self.device_label = device, f"fake {device}"
        self.lv = SimpleNamespace(grave=0.0, medio=0.0, agudo=0.0, geral=0.0, batidas=0, ativo=True)
        self.running = False
        _FakeAnalyzer.instances.append(self)

    def start(self):
        self.running = True
        return self

    def stop(self):
        self.running = False

    def get(self):
        return self.lv


def test_audio_bus_troca_de_dispositivo_e_aplica_ganho():
    _FakeAnalyzer.instances.clear()
    bus = AudioBus(factory=_FakeAnalyzer)
    assert bus.levels() == SILENCE and not bus.running
    bus.ensure(AudioInput(device="loopback", gain=2.0))
    bus.ensure(AudioInput(device="loopback", gain=2.0))  # mesmo dispositivo: não reabre
    assert len(_FakeAnalyzer.instances) == 1
    _FakeAnalyzer.instances[0].lv.grave = 0.3
    _FakeAnalyzer.instances[0].lv.agudo = 0.8
    lv = bus.levels()
    assert lv["bass"] == pytest.approx(0.6) and lv["high"] == 1.0  # ganho satura em 1
    bus.ensure(AudioInput(device="mic"))
    assert len(_FakeAnalyzer.instances) == 2
    assert _wait(lambda: not _FakeAnalyzer.instances[0].running)  # parado em segundo plano
    assert bus.status()["device_label"] == "fake mic"
    bus.stop()
    assert not _FakeAnalyzer.instances[1].running


def test_envelope_de_batida_decai_com_meia_vida():
    now = [100.0]
    bus = AudioBus(factory=_FakeAnalyzer, clock=lambda: now[0])
    bus.ensure(AudioInput())
    an = _FakeAnalyzer.instances[-1]
    assert bus.levels()["beat"] == 0.0
    an.lv.batidas = 1
    assert bus.levels()["beat"] == pytest.approx(1.0)
    now[0] += 0.12
    assert bus.levels()["beat"] == pytest.approx(0.5)
    now[0] += 1.0
    assert bus.levels()["beat"] < 0.01


# ----------------------------------------------------------- captura de vídeo
class _FakeCap:
    def __init__(self):
        self.n = 0
        self.released = False

    def read(self):
        self.n += 1
        time.sleep(0.005)
        img = np.full((6, 8, 3), self.n % 255, np.uint8)
        return True, img

    def release(self):
        self.released = True


def _wait(cond, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_captura_compartilhada_entrega_quadros_novos_e_fecha_no_ultimo_release():
    caps = []

    def opener(device):
        caps.append(_FakeCap())
        return caps[-1], f"Fake {device}"

    a = vin.open_capture("Fake Cam", opener)
    b = vin.open_capture("fake cam", opener)  # mesmo dispositivo (sem diferenciar maiúsculas)
    try:
        assert _wait(lambda: a.frame_at(0)[0] > 2)
        k1, img = a.frame_at(0)
        assert img.shape == (6, 8, 4) and a.size == (8, 6)
        assert _wait(lambda: b.frame_at(0)[0] > k1)  # chave avança com quadro novo
        assert len(caps) == 1
        st = [c for c in vin.active_captures() if c["device"] == "fake cam"][0]
        assert st["name"] == "Fake fake cam" and st["refs"] == 2 and st["frames"] > 0
    finally:
        a.close()
        assert not caps[0].released
        b.close()
    assert _wait(lambda: caps[0].released)
    assert not [c for c in vin.active_captures() if c["device"] == "fake cam"]


def test_captura_que_falha_mostra_preto_e_guarda_o_erro():
    def opener(device):
        raise RuntimeError("câmera ocupada")

    src = vin.open_capture("quebrada", opener)
    try:
        key, img = src.frame_at(0)
        assert key == 0 and img[..., :3].max() == 0
        assert _wait(lambda: any(c["error"] == "câmera ocupada" for c in vin.active_captures()))
    finally:
        src.close()


def test_factory_cria_fonte_capture(monkeypatch):
    from projmap.content.factory import get_source

    monkeypatch.setattr(vin, "_default_opener", lambda device: (_FakeCap(), device))
    src = get_source(SourceSpec(kind="capture", device="cam-x"))
    try:
        assert isinstance(src, vin.CaptureSource)
    finally:
        src.close()


# ----------------------------------------------------------- tap da saída
def test_output_tap_entrega_png_do_proximo_quadro():
    cv2 = pytest.importorskip("cv2")
    tap = OutputTap()
    assert tap.request() is None  # sem janela
    tap.attached = True
    stop = threading.Event()
    frame = np.zeros((40, 100, 3), np.uint8)
    frame[:, :50] = (255, 0, 0)

    def window():
        while not stop.is_set():
            tap.service(lambda: frame)
            time.sleep(0.005)

    th = threading.Thread(target=window, daemon=True)
    th.start()
    try:
        png = tap.request(max_width=50)
    finally:
        stop.set()
        th.join()
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape == (20, 50, 3)
    assert tuple(img[10, 5]) == (0, 0, 255)  # BGR do vermelho


# ----------------------------------------------------------- API
@pytest.fixture
def client(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from projmap.core.state import ProjectState
    from projmap.core.store import ProjectStore
    from projmap.master.app import create_app

    store = ProjectStore.create(tmp_path / "show.projmap", "Teste")
    state = ProjectState(store)
    tap = OutputTap()
    return TestClient(create_app(state, output_tap=tap, save_library_config=False, config_dir=tmp_path)), state, tap


def test_api_cria_superficie_em_tela_cheia_com_entrada_de_video(client):
    c, state, _ = client
    r = c.post("/api/surfaces", json={"node_id": "proj-1", "label": "Câmera",
                                      "source": {"kind": "capture", "device": "auto"}})
    assert r.status_code == 200
    sid = r.json()["surface_id"]
    surf = next(s for s in state.snapshot()[1].surfaces if s.id == sid)
    assert surf.warp.base == [(0, 0), (1920, 0), (1920, 1080), (0, 1080)]
    assert surf.source.kind == "capture"
    assert c.post("/api/surfaces", json={"node_id": "nada"}).status_code == 404


def test_api_fullscreen_e_fx_por_patch(client):
    c, state, _ = client
    sid = c.post("/api/surfaces", json={"node_id": "proj-1", "fullscreen": False}).json()["surface_id"]
    assert state.snapshot()[1].surfaces[0].warp.base[0] == (480, 270)
    c.post(f"/api/surfaces/{sid}/fullscreen")
    assert state.snapshot()[1].surfaces[0].warp.base[2] == (1920, 1080)
    fx = [{"type": "strobe", "band": "beat", "amount": 0.9}, {"type": "pulse", "band": "bass", "amount": 0.5}]
    r = c.patch(f"/api/surfaces/{sid}", json={"fx": fx})
    assert r.status_code == 200
    assert [f.type for f in state.snapshot()[1].surfaces[0].fx] == ["strobe", "pulse"]
    assert c.patch(f"/api/surfaces/{sid}", json={"fx": [{"type": "pulse", "amount": 3}]}).status_code == 422
    assert c.post("/api/surfaces/nada/fullscreen").status_code == 404


def test_api_entrada_de_audio(client):
    c, state, _ = client
    r = c.patch("/api/audio", json={"device": "mic", "gain": 2.5})
    assert r.status_code == 200 and r.json()["project"]["audio"] == {"device": "mic", "gain": 2.5}
    assert c.patch("/api/audio", json={"gain": 99}).status_code == 422
    lv = c.get("/api/inputs/audio").json()
    assert set(lv["levels"]) == {"bass", "mid", "high", "level", "beat"}


def test_api_snapshot_sem_janela_e_com_janela(client):
    c, _, tap = client
    assert c.get("/api/nodes/proj-1/snapshot").status_code == 503
    assert c.get("/api/nodes/nada/snapshot").status_code == 404
    tap.attached = True
    stop = threading.Event()

    def window():
        while not stop.is_set():
            tap.service(lambda: np.full((90, 160, 3), 200, np.uint8))
            time.sleep(0.005)

    th = threading.Thread(target=window, daemon=True)
    th.start()
    try:
        r = c.get("/api/nodes/proj-1/snapshot?max_width=80")
    finally:
        stop.set()
        th.join()
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
