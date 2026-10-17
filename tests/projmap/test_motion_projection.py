"""Motions (HTML) como fonte de superfície: manifesto, hub, protocolo e o caminho
inteiro com um Chromium de verdade (pulado se não houver navegador ou UI compilada)."""

from __future__ import annotations

import io
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from projmap.core.project import SourceSpec
from projmap.motion.hub import MotionHub, pack, unpack
from projmap.motion.manifest import parse_motion_html

FIXTURE = Path(__file__).parent / "fixtures" / "motion_test_av.html"
UI_OUT = Path(__file__).resolve().parents[2] / "projmap" / "ui" / "out"
CAMERA_GRAIN = Path(__file__).resolve().parents[2] / "projmap" / "motion" / "examples" / "camera-grain-crimson.html"


# ---------------------------------------------------------------- manifesto
def test_manifesto_do_motion_de_teste():
    info = parse_motion_html(FIXTURE.read_bytes())
    assert (info.id, info.name, info.version, info.video_input) == ("projmap-teste-av", "Teste AV", "1.0.0", True)


def test_motion_camera_grain_distribuido_declara_video_e_modos():
    raw = CAMERA_GRAIN.read_bytes()
    info = parse_motion_html(raw)
    assert (info.id, info.name, info.version, info.video_input) == (
        "camera-grain-crimson", "Camera Grain Crimson", "1.1.0", True,
    )
    assert info.modes == ["crimson", "monochrome", "negative"]
    source = raw.decode("utf-8")
    assert 'getContext("webgl"' in source
    assert "getImageData" not in source


@pytest.mark.parametrize("html, msg", [
    (b"<html><body>oi</body></html>", "motion-manifest"),
    (b'<script type="application/json" id="motion-manifest">{oops</script>', "JSON"),
    (b'<script type="application/json" id="motion-manifest">{"spec":"x"}</script>', "spec"),
    (b'<script id="motion-manifest" type="application/json">{"spec":"motion-module/1","id":"A B","name":"n",'
     b'"version":"1"}</script>', "id"),
])
def test_html_que_nao_e_motion_e_recusado(html, msg):
    with pytest.raises(ValueError, match=msg):
        parse_motion_html(html)


def test_store_aceita_motion_html_e_recusa_html_qualquer(tmp_path):
    from projmap.core.store import ProjectStore

    store = ProjectStore.create(tmp_path / "s.projmap")
    item = store.add_media(FIXTURE, "Meu Motion.htm")
    assert item.kind == "motion" and item.ext == ".html"
    with pytest.raises(ValueError, match="motion-manifest"):
        store.add_media(io.BytesIO(b"<html></html>"), "pagina.html")


def test_upload_pela_api_e_fonte_motion_na_superficie(tmp_path):
    from fastapi.testclient import TestClient

    from projmap.core.state import ProjectState
    from projmap.core.store import ProjectStore
    from projmap.master.app import create_app

    state = ProjectState(ProjectStore.create(tmp_path / "s.projmap"))
    c = TestClient(create_app(state, save_library_config=False, config_dir=tmp_path))
    r = c.post("/api/media", files={"file": ("teste.html", FIXTURE.read_bytes(), "text/html")})
    assert r.status_code == 200 and r.json()["item"]["kind"] == "motion"
    sha = r.json()["item"]["sha256"]
    sid = c.post("/api/surfaces", json={"node_id": "proj-1"}).json()["surface_id"]
    r = c.patch(f"/api/surfaces/{sid}", json={"source": {"kind": "motion", "media": sha, "device": "auto",
                                                          "params": {"flash": 0.5}, "mode": "default"}})
    assert r.status_code == 200
    src = state.snapshot()[1].surfaces[0].source
    assert (src.kind, src.params, src.device) == ("motion", {"flash": 0.5}, "auto")
    # motion não pode ser usado como "imagem" e vice-versa
    assert c.patch(f"/api/surfaces/{sid}", json={"source": {"kind": "image", "media": sha}}).status_code == 422


def test_post_de_outra_origem_e_bloqueado(tmp_path):
    """Um motion roda num iframe sandbox (origem ``null``): não pode escrever na API."""
    from fastapi.testclient import TestClient

    from projmap.core.state import ProjectState
    from projmap.core.store import ProjectStore
    from projmap.master.app import create_app

    state = ProjectState(ProjectStore.create(tmp_path / "s.projmap"))
    c = TestClient(create_app(state, save_library_config=False, config_dir=tmp_path))
    for origin in ("null", "https://site.example"):
        r = c.post("/api/surfaces", json={"node_id": "proj-1"}, headers={"Origin": origin})
        assert r.status_code == 403
    assert c.post("/api/surfaces", json={"node_id": "proj-1"},
                  headers={"Origin": "http://testserver"}).status_code == 200  # mesma origem
    assert c.post("/api/surfaces", json={"node_id": "proj-1"},
                  headers={"Origin": "http://localhost:3100"}).status_code == 200  # editor em dev
    assert c.get("/api/project", headers={"Origin": "null"}).status_code == 200  # leitura segue o CORS


# ---------------------------------------------------------------- hub
class _FakeBrowser:
    def __init__(self, url):
        self.url, self.running, self.starts, self.exe = url, False, 0, Path("fake")

    def start(self):
        self.running, self.starts = True, self.starts + 1

    def stop(self):
        self.running = False


def test_hub_compartilha_sessao_igual_e_liga_desliga_o_navegador():
    made = []
    h = MotionHub(browser_factory=lambda url: made.append(_FakeBrowser(url)) or made[-1], idle_stop_s=0.2)
    h.configure("http://127.0.0.1:9")
    a = h.open_session("a" * 64, (320, 180), {"seed": 1})
    b = h.open_session("a" * 64, (320, 180), {"seed": 1})
    c = h.open_session("a" * 64, (320, 180), {"seed": 2})
    assert a is b and a is not c
    assert len(h.sessions()[1]) == 2
    deadline = time.monotonic() + 3
    while not (made and made[0].running) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert made[0].url == "http://127.0.0.1:9/motion-host/" and made[0].running
    for s in (a, b, c):
        h.release(s)
    assert h.sessions()[1] == []
    deadline = time.monotonic() + 3
    while made[0].running and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not made[0].running  # ocioso: desliga
    h.shutdown()


def test_hub_recebe_quadros_validos_e_descarta_os_errados():
    h = MotionHub(browser_factory=_FakeBrowser)
    s = h.open_session("b" * 64, (4, 2))
    h.put_frame(pack({"sid": s.sid, "w": 4, "h": 2}, bytes(range(32))))
    key, img = h.latest(s)
    assert key == 1 and img.shape == (2, 4, 4) and img[0, 0, 1] == 1
    h.put_frame(pack({"sid": s.sid, "w": 4, "h": 2, "flip_y": True}, bytes(range(32))))
    key, img = h.latest(s)
    assert key == 2 and img[0, 0, 0] == 16 and img[1, 0, 0] == 0
    with pytest.raises(ValueError):
        h.put_frame(pack({"sid": s.sid, "w": 4, "h": 2}, b"\0" * 10))
    with pytest.raises(ValueError):
        unpack(b"\xff\xff\xff\xff{}")
    h.put_frame(pack({"sid": "outra", "w": 1, "h": 1}, b"\0" * 4))  # sessão fechada: ignora
    assert h.latest(s)[0] == 2


def test_factory_cria_fonte_motion(monkeypatch):
    from projmap.content.factory import get_source
    from projmap.motion import hub as hub_mod

    fake = MotionHub(browser_factory=_FakeBrowser)
    monkeypatch.setattr(hub_mod, "_HUB", fake)
    src = get_source(SourceSpec(kind="motion", media="c" * 64, params={"seed": 4}, device="cam"))
    try:
        assert src.size == (1280, 720)
        assert fake.sessions()[1][0]["params"] == {"seed": 4} and fake.devices() == {"cam"}
    finally:
        src.close()
    assert fake.sessions()[1] == []


# ---------------------------------------------------------------- navegador de verdade
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakeCap:
    def read(self):
        time.sleep(0.02)
        img = np.zeros((90, 160, 3), np.uint8)
        img[..., 2] = 255  # BGR: vermelho puro
        return True, img

    def release(self):
        pass


def _wait(cond, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = cond()
        if v is not None and v is not False:
            return v
        time.sleep(0.05)
    return None


@pytest.fixture
def live_master(tmp_path, monkeypatch):
    from projmap.motion.browser import MotionBrowser, find_browser

    exe = find_browser()
    if exe is None:
        pytest.skip("sem Chromium/Chrome/Edge para rodar motions")
    if not (UI_OUT / "motion-host" / "index.html").is_file():
        pytest.skip("UI não compilada (cd projmap/ui && npm run build)")
    import uvicorn

    from projmap.core.state import ProjectState
    from projmap.core.store import ProjectStore
    from projmap.inputs import audio as audio_mod
    from projmap.inputs import video as vin
    from projmap.inputs.audio import AudioBus
    from projmap.master.app import create_app

    monkeypatch.setattr(vin, "_default_opener", lambda device: (_FakeCap(), f"Fake {device}"))
    lv = SimpleNamespace(grave=0.0, medio=0.0, agudo=0.0, geral=0.0, batidas=0, ativo=True)
    analyzer = SimpleNamespace(device="loopback", device_label="fake", start=lambda: None, stop=lambda: None,
                               get=lambda: lv)
    fake_bus = AudioBus(factory=lambda _d: analyzer)
    from projmap.core.project import AudioInput

    fake_bus.ensure(AudioInput())
    monkeypatch.setattr(audio_mod, "_BUS", fake_bus)

    store = ProjectStore.create(tmp_path / "show.projmap")
    item = store.add_media(FIXTURE, "teste.html")
    state = ProjectState(store)
    port = _free_port()
    profile = tmp_path / "browser-profile"
    owner = MotionHub(browser_factory=lambda url: MotionBrowser(url, exe=exe, profile=profile), idle_stop_s=60)
    app = create_app(state, UI_OUT, save_library_config=False, config_dir=tmp_path, motion_hub=owner)

    def media_ok(p):
        p.media[item.sha256] = item
        return p

    state.update(media_ok)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           ws_per_message_deflate=False))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    assert _wait(lambda: server.started, 10)
    owner.configure(f"http://127.0.0.1:{port}")
    try:
        yield owner, item, lv
    finally:
        owner.shutdown()
        server.should_exit = True
        th.join(timeout=5)


def test_motion_roda_no_navegador_recebe_video_e_audio_e_chega_ao_renderer(live_master):
    from projmap.motion.source import open_motion

    owner, item, lv = live_master
    src = open_motion(SourceSpec(kind="motion", media=item.sha256, device="fake-cam"), owner=owner)
    try:
        def frame_with_marker():
            key, img = src.frame_at(0)
            if key == 0 or img.shape[:2] != (720, 1280):
                return None
            r, g, b = (int(v) for v in img[20, 20, :3])
            return img if g > 200 and r < 60 and b < 60 else None  # verde (o JPEG mexe um pouco na cor)

        img = _wait(frame_with_marker, 45)
        assert img is not None, f"o motion não chegou: {owner.status()}"

        def video_in_center():
            _, im = src.frame_at(0)
            r, g, b = (int(v) for v in im[360, 640, :3])
            return im if r > 200 and g < 60 and b < 60 else None

        assert _wait(video_in_center, 15) is not None, "a entrada de vídeo não chegou ao motion"

        corner = lambda im: float(im[300:340, 20:60, :3].mean())  # noqa: E731 — fora do marcador/vídeo
        assert corner(src.frame_at(0)[1]) < 30  # sem batida: preto
        flashed: list = []
        for _ in range(10):  # algumas batidas (tolerante a máquina ocupada: precisa de 3 flashes)
            lv.batidas += 1
            got = _wait(lambda: (lambda im: corner(im) if corner(im) > 120 else None)(src.frame_at(0)[1]), 2)
            flashed.append(got)
            if sum(1 for f in flashed if f) >= 3:
                break
            time.sleep(0.3)
        assert sum(1 for f in flashed if f) >= 3, f"o motion não piscou com a batida: {flashed}"

        k1 = src.frame_at(0)[0]
        time.sleep(1.0)
        fps = src.frame_at(0)[0] - k1
        print(f"\nmotion: ~{fps} quadros/s chegando ao renderer")
        assert fps >= 5  # fumaça: o desempenho é medido à parte (docs/entregas/projmap-motion-html-superficie.md)
    finally:
        src.close()
