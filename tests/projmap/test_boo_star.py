"""Castelo dos Boos: sprites de imagem, fundo, estrela de poder; e escolha de câmera (C920)."""

import math

import numpy as np
import pytest

from projmap.interact import scene as scene_mod
from projmap.interact.cameras import CameraInfo, choose_camera, parse_dshow_list, parse_size
from projmap.interact.scene import PRESETS, EntityGroup, SceneSpec, Skin, StarSpec, ChasePlayer, FreezeWhenWatched
from projmap.interact.sim import Simulation
from projmap.interact.world import Player


# ---------------------------------------------------------------- esquema
@pytest.mark.parametrize("bad", ["C:/x.png", "../x.png", "/etc/x.png", "boo/x.exe", " "])
def test_imagens_so_da_pasta_de_cenas(bad):
    with pytest.raises(ValueError):
        Skin(image=bad)
    with pytest.raises(ValueError):
        SceneSpec(groups=[EntityGroup()], background_image=bad)


def test_preset_castelo_boo():
    s = PRESETS["castelo-boo"]
    assert s.background_image == "boo/castelo.png" and s.star is not None
    g = s.groups[0]
    assert g.sprite == "image" and all(k.shy_image for k in g.skins)


# ---------------------------------------------------------------- render
@pytest.fixture
def assets(tmp_path, monkeypatch):
    cv2 = pytest.importorskip("cv2")
    from projmap.interact import render

    monkeypatch.setattr(scene_mod, "ASSET_DIR", tmp_path)
    render._load_rgba.cache_clear(), render._scaled.cache_clear(), render._background.cache_clear()
    (tmp_path / "t").mkdir()
    red = np.zeros((10, 10, 4), np.uint8); red[..., 2] = 255; red[..., 3] = 255  # BGRA vermelho opaco
    blue = np.zeros((10, 10, 4), np.uint8); blue[..., 0] = 255; blue[..., 3] = 255
    bg = np.full((9, 16, 3), (0, 255, 0), np.uint8)  # fundo verde (BGR)
    for name, im in (("normal.png", red), ("shy.png", blue), ("bg.png", bg)):
        cv2.imwrite(str(tmp_path / "t" / name), im)
    yield tmp_path
    render._load_rgba.cache_clear(), render._scaled.cache_clear(), render._background.cache_clear()


def _spec(**kw):
    g = EntityGroup(name="b", sprite="image", count=1, size=0.3, spawn="center", shy_alpha=0.25,
                    skins=[Skin(image="t/normal.png", shy_image="t/shy.png")],
                    behaviors=[ChasePlayer(speed=0.1), FreezeWhenWatched(shy=True)])
    return SceneSpec(groups=[g], background_image="t/bg.png", **kw)


def test_fundo_e_sprite_opaco_quando_nao_olham(assets):
    from projmap.interact.render import render_snapshot

    sim = Simulation(_spec())
    snap = sim.step(1 / 30, [Player(x=0.2, yaw=math.pi)])  # de costas: persegue
    img = render_snapshot(snap, (320, 180))
    assert tuple(img[2, 2, :3]) == (0, 255, 0)  # fundo verde (RGB)
    e = snap.entities[0]
    cx, cy = int(e.x * 180), int(e.y * 180)
    assert img[cy, cx, 0] > 240 and img[cy, cx, 2] < 15  # vermelho, opaco


def test_olhado_troca_imagem_e_fica_translucido(assets):
    from projmap.interact.render import render_snapshot

    sim = Simulation(_spec())
    snap = sim.step(1 / 30, [Player(x=16 / 9 / 2, yaw=0.0)])  # olhando para o centro
    assert snap.entities[0].state == "shy"
    img = render_snapshot(snap, (320, 180))
    e = snap.entities[0]
    px = img[int(e.y * 180), int(e.x * 180), :3].astype(int)
    assert px[2] > 40 and px[1] > 150  # azul com 25% sobre o verde
    assert px[0] < 30


def test_sem_imagem_cai_no_fantasma_desenhado(tmp_path, monkeypatch):
    from projmap.interact import render

    monkeypatch.setattr(scene_mod, "ASSET_DIR", tmp_path)
    render._load_rgba.cache_clear()
    spec = SceneSpec(groups=[EntityGroup(sprite="image", count=1, skins=[Skin(image="nao/existe.png")])],
                     background_image="nao/fundo.png")
    img = render.render_snapshot(Simulation(spec).step(0.03, []), (160, 90))
    assert img[..., :3].max() > 100  # desenhou algo (fantasma procedural)


# ---------------------------------------------------------------- estrela
def _star_sim(**star):
    spec = SceneSpec(groups=[EntityGroup(sprite="ghost", count=3, size=0.12, spawn="edges",
                                         behaviors=[ChasePlayer(speed=0.1)])],
                     star=StarSpec(interval_s=1, duration_s=3, respawn_s=1, **star), on_caught=[])
    return Simulation(spec)


def test_estrela_aparece_e_anda_em_senoide():
    sim = _star_sim(speed=0.3, amplitude=0.2, frequency=1.0)
    p = Player(x=0.1, yaw=math.pi, tracked=False)  # ninguém para pegar
    ys, events = [], []
    for _ in range(90):
        snap = sim.step(1 / 30, [p])
        events += [e.name for e in snap.events]
        if snap.star:
            ys.append(snap.star.y)
    assert "star_appeared" in events
    assert max(ys) - min(ys) > 0.3  # oscila ~±0.2


def test_pegar_estrela_da_poder_e_derrota_fantasma():
    sim = _star_sim(speed=0.3)
    p = Player(x=16 / 9 / 2, yaw=math.pi)
    got = defeated = respawned = False
    for _ in range(30 * 20):
        if sim.star is not None:
            p.x = sim.star.x  # fica na frente da estrela
        elif sim.t < sim.power_until:
            alive = [e for e in sim.entities if e.respawn_t < 0]
            if alive:
                p.x = alive[0].x
                p.eye_y = alive[0].y
        snap = sim.step(1 / 30, [p])
        names = [e.name for e in snap.events]
        got |= "star_caught" in names
        if got and not defeated and snap.power > 0:
            assert all(e.state in ("scared", "defeated") for e in snap.entities)
        defeated |= "defeated" in names
        if defeated and any(e.respawn_t < 0 and e.defeated_t < 0 for e in sim.entities):
            respawned = True
        if got and defeated and respawned:
            break
    assert got and defeated and respawned


def test_poder_acaba_e_fantasmas_voltam_a_perseguir():
    sim = _star_sim()
    sim.power_until = sim.t + 0.2
    p = Player(x=0.2, yaw=math.pi)
    for _ in range(15):
        snap = sim.step(1 / 30, [p])
    assert snap.power == 0 and any(e.state == "move" for e in snap.entities)


# ---------------------------------------------------------------- câmeras
DSHOW = '''[in#0 @ 0x1] "HD Webcam" (video)
[in#0 @ 0x1]   Alternative name "@device_pnp_..."
[in#0 @ 0x1] "OBS Virtual Camera" (video)
[in#0 @ 0x1] "HD Pro Webcam C920" (video)
[in#0 @ 0x1] "Microfone (C920)" (audio)
[in#0 @ 0x1] "Streamfog VirtualCam" (none)'''


def test_lista_dshow_so_video_na_ordem():
    assert parse_dshow_list(DSHOW) == ["HD Webcam", "OBS Virtual Camera", "HD Pro Webcam C920"]


def test_auto_prefere_c920_e_ignora_virtuais():
    cams = [CameraInfo(i, n) for i, n in enumerate(parse_dshow_list(DSHOW))]
    assert choose_camera(cams, "auto").name == "HD Pro Webcam C920"
    assert choose_camera(cams[:2], "auto").name == "HD Webcam"  # sem C920: a física
    assert choose_camera([CameraInfo(0, "OBS Virtual Camera")], "auto").index == 0  # só virtual: usa
    assert choose_camera(cams, "c920").index == 2 and choose_camera(cams, "1").index == 1
    assert choose_camera(cams, "brio") is None and choose_camera([], "auto") is None


def test_parse_size():
    assert parse_size("1280x720") == (1280, 720) and parse_size(" 1920 × 1080 ") == (1920, 1080)
    with pytest.raises(ValueError):
        parse_size("grande")
