"""Efeitos importados do visual_frames: importador, visão, áudio, motor e API."""

import math

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from projmap.effects import config as C  # noqa: E402
from projmap.effects.audio import AudioAnalyzer  # noqa: E402
from projmap.effects.importar import extract_fragment_shader, import_from, is_imported  # noqa: E402
from projmap.effects.tracker import Detection, OneEuro, Tracker, iou  # noqa: E402
from projmap.effects.vision import VisionResult, guided_filter, stylize_comic  # noqa: E402


# ---------------------------------------------------------------- importador
FAKE_CPP = '''const std::string VERTEX_SHADER = R"(
#version 150
void main() {}
)";
const std::string FRAGMENT_SHADER = R"(
#version 150
out vec4 corFinal;
void main() { corFinal = vec4(1.0); }
)";'''


def test_extrai_o_fragment_shader():
    src = extract_fragment_shader(FAKE_CPP)
    assert src.startswith("#version 150") and "corFinal = vec4(1.0)" in src and "VERTEX" not in src
    with pytest.raises(ValueError):
        extract_fragment_shader("int main() {}")


def test_importa_de_uma_pasta(tmp_path):
    repo = tmp_path / "visual_frames"
    (repo / "of_void_cloud" / "src").mkdir(parents=True)
    (repo / "of_void_cloud" / "src" / "ofApp.cpp").write_text(FAKE_CPP)
    (repo / "modelos").mkdir()
    for m in ("yolo26n-seg.onnx", "yolo26s-pose.onnx"):
        (repo / "modelos" / m).write_bytes(b"onnx")
    dest = tmp_path / "dest"
    assert not is_imported(dest)
    import_from(str(repo), dest)
    assert is_imported(dest) and "Adriel" in (dest / "ORIGEM.txt").read_text()
    with pytest.raises(FileNotFoundError):
        import_from(str(tmp_path / "nada"), dest)


# ---------------------------------------------------------------- rastreador
def test_one_euro_suaviza_parado_e_acompanha_movimento():
    f = OneEuro(1.0, 0.02, 1.0)
    rng = np.random.RandomState(0)
    out = [f(100 + rng.randn() * 2, 1 / 30) for _ in range(60)]
    assert np.std(out[20:]) < 1.0  # ruído de ±2 px vira < 1 px
    for i in range(30):
        y = f(100 + i * 10, 1 / 30)
    assert y > 300  # segue o movimento


def _det(x, conf=0.9, w=200, h=500):
    return Detection(np.array([x, 100, x + w, 100 + h], np.float32), conf, has_pose=True,
                     points=np.tile(np.array([[x + w / 2, 200, 0.9]], np.float32), (17, 1)))


def test_rastreador_mantem_id_e_slot_e_esquece_depois():
    tr = Tracker()
    tr.update([_det(100), _det(700)], 1 / 30)
    ids = {t.slot: t.id for t in tr.tracks}
    for k in range(10):  # andando devagar
        tr.update([_det(100 + 5 * k), _det(700 - 5 * k)], 1 / 30)
    assert {t.slot: t.id for t in tr.tracks} == ids
    for _ in range(C.QUADROS_MEMORIA_PERDIDA + 2):
        tr.update([], 1 / 30)
    assert tr.tracks == []


def test_rastreador_ignora_duplicata_contida():
    tr = Tracker()
    tr.update([_det(100), Detection(np.array([120, 150, 280, 550], np.float32), 0.8)], 1 / 30)
    assert len(tr.tracks) == 1


def test_iou():
    a = np.array([0, 0, 10, 10], np.float32)
    assert iou(a, a) == pytest.approx(1.0) and iou(a, a + 20) == 0.0


# ---------------------------------------------------------------- detector (saídas sintéticas)
def test_leitura_das_saidas_do_yolo():
    from projmap.effects.detector import PersonDetector

    d = PersonDetector.__new__(PersonDetector)
    d.scale = min(C.ENTRADA_LARGURA / C.CAMERA_LARGURA, C.ENTRADA_ALTURA / C.CAMERA_ALTURA)
    d.cw, d.ch = round(C.CAMERA_LARGURA * d.scale), round(C.CAMERA_ALTURA * d.scale)
    d.bx, d.by = (C.ENTRADA_LARGURA - d.cw) // 2, (C.ENTRADA_ALTURA - d.ch) // 2
    # pessoa ocupando x 200..400, y 60..340 na entrada letterbox
    pose = np.zeros((300, 57), np.float32)
    pose[0, :6] = [200, 60, 400, 340, 0.9, 0]
    pose[0, 6:] = np.tile([300, 100, 0.95], 17)
    people = d.read_pose(pose)
    assert len(people) == 1 and people[0].has_pose
    assert people[0].box[0] == pytest.approx(400) and people[0].box[1] == pytest.approx((60 - 12) * 2)
    seg = np.zeros((300, 38), np.float32)
    seg[0, :6] = [200, 60, 400, 340, 0.8, 0]
    seg[0, 6] = 1.0  # um coeficiente: máscara = protótipo 0
    seg[1, :6] = [10, 10, 50, 50, 0.7, 5]  # outra classe: ignorada
    proto = np.full((32, 96, 160), -5.0, np.float32)
    proto[0, 15:85, 50:100] = 5.0  # "pessoa" no protótipo
    masks = d.read_seg(seg, proto)
    assert len(masks) == 1
    x, y, w, h = masks[0].mask_region
    assert (masks[0].mask_logits > 0).mean() > 0.3


# ---------------------------------------------------------------- máscara / HQ
def test_filtro_guiado_preserva_borda_e_tira_ruido():
    guide = np.zeros((60, 80), np.float32)
    guide[:, 40:] = 1.0  # borda real em x=40
    rng = np.random.RandomState(1)
    src = np.clip(guide + rng.normal(0, 0.15, guide.shape), 0, 1).astype(np.float32)  # máscara ruidosa
    out = guided_filter(guide, src, 4, 0.01)
    boxed = cv2.boxFilter(src, cv2.CV_32F, (9, 9), borderType=cv2.BORDER_REFLECT)
    edge = lambda im: float(im[:, 41].mean() - im[:, 38].mean())  # noqa: E731 — salto na borda
    assert edge(out) > 0.8 > edge(boxed)  # borda continua nítida (o desfoque a espalha)
    assert out[:, 5:30].std() < src[:, 5:30].std() * 0.5  # ruído some nas regiões lisas


def test_estilo_quadrinho_tem_cor_e_traco():
    img = np.zeros((720, 1280, 3), np.uint8)
    cv2.circle(img, (640, 360), 200, (40, 90, 200), -1)
    hq = stylize_comic(img)
    assert hq.shape == (360, 640, 4) and hq[..., 3].max() > 200  # traço na borda do círculo


# ---------------------------------------------------------------- áudio
def test_batidas_de_um_bumbo_a_120_bpm():
    au = AudioAnalyzer()
    sr, hop = C.AUDIO_TAXA, C.AUDIO_SALTO
    t = 0.0
    for _ in range(int(8 * sr / hop)):  # 8 s
        tt = t + np.arange(hop) / sr
        kick = np.exp(-((tt % 0.5) * 25)) * np.sin(2 * np.pi * 60 * tt) * 0.6
        pad = 0.05 * np.sin(2 * np.pi * 880 * tt)  # música nunca fica em silêncio absoluto
        au.feed((kick + pad).astype(np.float32))
        t += hop / sr
    lv = au.get()
    assert lv.ativo and 12 <= lv.batidas <= 16  # ~2 por segundo, depois de ~1 s de histórico
    for _ in range(30):
        au.feed(np.zeros(hop, np.float32))
    assert not au.get().ativo


# ---------------------------------------------------------------- motor
STUB_FRAG = """#version 150
uniform sampler2D mascara;
uniform vec4 musica;
in vec2 uv;
out vec4 corFinal;
void main() { corFinal = vec4(texture(mascara, uv).r, musica.x, 0.0, 1.0); }
"""


@pytest.fixture
def stub_base(tmp_path):
    (tmp_path / "modelos").mkdir()
    (tmp_path / "efeitos.frag").write_text(STUB_FRAG)
    for m in ("yolo26n-seg.onnx", "yolo26s-pose.onnx"):
        (tmp_path / "modelos" / m).write_bytes(b"x")
    return tmp_path


class _NoVision:
    status = ""
    want_comic = want_frame = False

    def latest(self, seq):
        return None

    def stop(self):
        pass


class _NoAudio:
    def get(self):
        from projmap.effects.audio import AudioLevels

        return AudioLevels(grave=1.0, ativo=True)

    def stop(self):
        pass


def test_motor_roda_o_shader_com_a_mascara_na_orientacao_certa(stub_base):
    pytest.importorskip("moderngl")
    from projmap.effects.engine import EffectsEngine

    try:
        eng = EffectsEngine((320, 180), stub_base, vision=_NoVision(), audio=_NoAudio(), threaded=False).start()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sem OpenGL: {exc}")
    mask = np.zeros((C.MASCARA_ALTURA, C.MASCARA_LARGURA, 2), np.uint8)
    mask[: C.MASCARA_ALTURA // 4, :, 0] = 255  # pessoa só no topo
    eng.set_effect("vf-luz")
    img = eng.step(1 / 60, vision=VisionResult(seq=1, mask=mask))
    assert img.shape == (180, 320, 4)
    assert img[5, 160, 0] > 200 and img[170, 160, 0] < 30  # topo da máscara = topo da imagem
    assert img[90, 160, 1] > 200  # música (grave) chegou ao shader
    assert eng.effect == "luz"


def test_api_de_efeitos_com_motor_falso(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from projmap.core.state import ProjectState
    from projmap.core.store import ProjectStore
    from projmap.interact.runtime import InteractionRuntime
    from projmap.master.app import create_app

    class FakeEngine:
        def __init__(self):
            from projmap.effects.engine import EffectParams

            self.params, self.status, self.key = EffectParams(), "", None
            self.stopped = False

        def start(self):
            return self

        def set_effect(self, key):
            self.key = key

        def stop(self):
            self.stopped = True

        def frame(self):
            return 1, np.full((90, 160, 4), 7, np.uint8)

    rt = InteractionRuntime()
    eng = FakeEngine()
    rt.engine_factory = lambda: eng
    c = TestClient(create_app(ProjectState(ProjectStore.create(tmp_path / "s.projmap", "T")), runtime=rt))
    assert set(c.get("/api/interact/effects").json()["effects"]) == {"vf-luz", "vf-lego", "vf-ecos"}
    assert c.post("/api/interact/effects/nada").status_code == 404
    st = c.post("/api/interact/effects/vf-lego").json()
    assert st["effect"] == "vf-lego" and eng.key == "vf-lego"
    assert rt.render((320, 180))[1].shape == (180, 320, 4)  # superfície recebe o quadro do efeito
    assert c.patch("/api/interact/effects/params", json={"tamanho_peca": 22}).json()["effect_params"]["tamanho_peca"] == 22
    assert c.patch("/api/interact/effects/params", json={"x": 1}).status_code == 422
    c.post("/api/interact/presets/castelo-boo")  # voltar a uma cena desliga o efeito
    assert rt.effect is None and eng.stopped
