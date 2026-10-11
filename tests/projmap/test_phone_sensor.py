"""Celular-sensor: pontos do rosto → pessoa, WebSocket /api/interact/phone e ADB."""

import json
import math
import subprocess

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from projmap.interact.scene import PRESETS  # noqa: E402
from projmap.interact.sensors import FACE_MODEL_3D, PhoneSensor, apply_face  # noqa: E402
from projmap.interact.world import Player  # noqa: E402

W, H = 640, 480
A = 16 / 9


def face_points(yaw_deg: float, nose_px=(320.0, 240.0), dist_mm: float = 600.0):
    """6 pontos normalizados de um rosto sintético (mesma ordem de FACE_LANDMARKS)."""
    cam = np.array([[W, 0, W / 2], [0, W, H / 2], [0, 0, 1]], dtype=np.float64)
    flip = cv2.Rodrigues(np.array([math.pi, 0.0, 0.0]))[0]
    rot = cv2.Rodrigues(np.array([0.0, math.radians(yaw_deg), 0.0]))[0] @ flip
    tx = (nose_px[0] - W / 2) * dist_mm / W
    ty = (nose_px[1] - H / 2) * dist_mm / W
    pts, _ = cv2.projectPoints(FACE_MODEL_3D, cv2.Rodrigues(rot)[0], np.array([tx, ty, dist_mm]), cam, None)
    return [(float(x) / W, float(y) / H) for x, y in pts.reshape(-1, 2)]


# Pontos REAIS do MediaPipe FaceLandmarker (navegador, página /sensor) para um rosto
# de frente (foto pública da NASA, scikit-image ``astronaut``), 640×480. Regressão do
# bug em que o modelo 3D com esquerda/direita trocadas fazia "de frente" virar
# "de costas" (yaw ≈ 180°).
REAL_FRONTAL = [[0.4510660767555237, 0.45192450284957886], [0.44577425718307495, 0.568498969078064],
                [0.50993812084198, 0.3851526379585266], [0.3979831337928772, 0.37795698642730713],
                [0.4894922375679016, 0.47731369733810425], [0.4107537269592285, 0.47344958782196045]]


def test_landmarks_reais_de_frente_dao_olhando_a_parede():
    p = Player(tracked=False)
    apply_face(p, REAL_FRONTAL, W, H, A, mirror=True)
    assert p.facing_wall
    assert abs(math.degrees(p.yaw)) < 20


def test_modelo_3d_tem_o_lado_do_mediapipe():
    """De frente para a câmera, o olho esquerdo da pessoa (263) fica à direita da imagem."""
    pts = face_points(0)
    assert pts[2][0] > pts[3][0]  # 263 à direita de 33
    assert pts[4][0] > pts[5][0]  # 291 à direita de 61
    real = REAL_FRONTAL
    assert real[2][0] > real[3][0] and real[4][0] > real[5][0]


def test_rosto_de_frente_no_centro_vira_pessoa_olhando_o_centro_da_parede():
    p = Player(tracked=False)
    apply_face(p, face_points(0), W, H, A, mirror=True)
    assert p.tracked and p.face_visible and p.facing_wall
    assert p.x == pytest.approx(A / 2, abs=0.02)
    assert math.degrees(p.yaw) == pytest.approx(0, abs=3)


def test_espelhamento_posicao_e_rotacao():
    """Câmera na parede olhando o público: a esquerda da imagem é a direita da parede."""
    p = Player()
    apply_face(p, face_points(0, nose_px=(160.0, 240.0)), W, H, A, mirror=True)  # 1/4 da imagem
    assert p.x == pytest.approx(0.75 * A, abs=0.03)
    a, b = Player(), Player()
    apply_face(a, face_points(25), W, H, A, mirror=True)
    apply_face(b, face_points(25), W, H, A, mirror=False)
    assert abs(math.degrees(a.yaw)) == pytest.approx(25, abs=3)
    assert a.yaw == pytest.approx(-b.yaw)


def test_mais_longe_da_camera_da_distancia_maior():
    near, far = Player(), Player()
    apply_face(near, face_points(0, dist_mm=500), W, H, A)
    apply_face(far, face_points(0, dist_mm=1500), W, H, A)
    assert far.distance > near.distance * 2


def test_piscada_da_deteccao_nao_vira_de_costas():
    import time

    s = PhoneSensor(aspect=A, face_lost_after=0.2)
    s.update({"face": True, "pts": face_points(0), "w": W, "h": H})
    s.update({"face": False})  # um frame perdido
    assert s.players()[0].facing_wall
    s.update({"face": True, "pts": face_points(0), "w": W, "h": H})
    s.update({"face": False})
    time.sleep(0.25)
    s.update({"face": False})  # sem rosto por mais que o limite
    assert not s.players()[0].facing_wall


def test_phone_sensor_rosto_sem_rosto_timeout_e_mensagem_invalida():
    s = PhoneSensor(aspect=A, timeout=0.2, face_lost_after=0.0)
    assert s.players()[0].tracked is False  # nunca falou
    s.update({"face": True, "pts": face_points(0), "w": W, "h": H})
    p = s.players()[0]
    assert p.tracked and p.facing_wall
    s.update({"face": False})
    p = s.players()[0]
    assert p.tracked and not p.facing_wall and p.x == pytest.approx(A / 2, abs=0.02)  # mantém posição
    with pytest.raises(ValueError):
        s.update({"face": True, "pts": [[0.5, 0.5]], "w": W, "h": H})
    import time

    time.sleep(0.25)
    assert s.players()[0].tracked is False  # celular calou ⇒ ninguém


def test_websocket_do_celular_troca_sensor_e_alimenta_a_cena(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from projmap.core.state import ProjectState
    from projmap.core.store import ProjectStore
    from projmap.interact.runtime import InteractionRuntime
    from projmap.interact.sensors import SimSensor
    from projmap.master.app import create_app

    rt = InteractionRuntime(PRESETS["fantasmas-timidos"], SimSensor(script=None))
    c = TestClient(create_app(ProjectState(ProjectStore.create(tmp_path / "p")), runtime=rt,
                              nlp_client_factory=lambda: None))
    with c.websocket_connect("/api/interact/phone") as ws:
        assert rt.sensor.kind == "phone"
        for _ in range(4):
            ws.send_text(json.dumps({"face": True, "pts": face_points(0), "w": W, "h": H, "fps": 24}))
        rt.step(1 / 30)
        ws.send_text(json.dumps({"face": True, "pts": face_points(0), "w": W, "h": H, "fps": 24}))
        fb = ws.receive_json()  # retorno a cada 5 mensagens
        assert fb["tracked"] is True and fb["watching"] is True and fb["scene"] == "Fantasmas tímidos"
        st = c.get("/api/interact/state").json()
        assert st["sensor"] == "phone" and st["phone"]["connected"] == 1 and st["phone"]["fps"] == 24
        assert st["players"][0]["watching"] is True

        ws.send_text(json.dumps({"face": True, "pts": [[0, 0]], "w": W, "h": H}))  # lixo
        assert "error" in ws.receive_json()
        # virou de costas: sem rosto por mais que a histerese (0,35 s)
        ws.send_text(json.dumps({"face": False}))
        import time

        time.sleep(0.4)
        ws.send_text(json.dumps({"face": False}))
        deadline = time.time() + 2
        while time.time() < deadline and rt.sensor.players()[0].facing_wall:
            time.sleep(0.02)
        rt.step(1 / 30)
        assert c.get("/api/interact/state").json()["players"][0]["watching"] is False
    assert c.get("/api/interact/state").json()["phone"]["connected"] == 0


def test_modelo_local_do_rosto(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from projmap.core.state import ProjectState
    from projmap.core.store import ProjectStore
    from projmap.interact.runtime import InteractionRuntime
    from projmap.master.app import create_app

    c = TestClient(create_app(ProjectState(ProjectStore.create(tmp_path / "p")),
                              runtime=InteractionRuntime(), nlp_client_factory=lambda: None))
    monkeypatch.setenv("PROJMAP_FACE_MODEL", str(tmp_path / "nao-existe.task"))
    assert c.get("/api/interact/face-model").status_code == 404
    model = tmp_path / "face.task"
    model.write_bytes(b"modelo")
    monkeypatch.setenv("PROJMAP_FACE_MODEL", str(model))
    assert c.get("/api/interact/face-model").content == b"modelo"
    assert c.head("/api/interact/face-model").status_code == 200  # a página testa com HEAD


# ----------------------------------------------------------------------- ADB
class FakeRun:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        key = " ".join(cmd[1:])
        for prefix, (code, out) in self.outputs.items():
            if key.startswith(prefix):
                return subprocess.CompletedProcess(cmd, code, out, "erro" if code else "")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_adb_reverse_e_abre_a_pagina(monkeypatch):
    from projmap.tools import adb

    fake = FakeRun({"devices": (0, "List of devices attached\nR58N1234 device usb:1-1 product:x model:SM_A525M\n")})
    monkeypatch.setattr(adb.subprocess, "run", fake)
    monkeypatch.setenv("ADB", "/opt/adb")
    dev = adb.connect_phone(8100)
    assert dev.model == "SM_A525M"
    assert ["/opt/adb", "-s", "R58N1234", "reverse", "tcp:8100", "tcp:8100"] in fake.calls
    assert fake.calls[-1][-1] == "http://localhost:8100/sensor/"


@pytest.mark.parametrize("listing, trecho", [
    ("List of devices attached\n", "nenhum celular"),
    ("List of devices attached\nABC unauthorized usb:1\n", "aceite o aviso"),
    ("List of devices attached\nA device\nB device\n", "mais de um"),
])
def test_adb_erros_com_mensagem_util(monkeypatch, listing, trecho):
    from projmap.tools import adb

    monkeypatch.setattr(adb.subprocess, "run", FakeRun({"devices": (0, listing)}))
    monkeypatch.setenv("ADB", "/opt/adb")
    with pytest.raises(adb.AdbError, match=trecho):
        adb.connect_phone(8100)


def test_adb_ausente(monkeypatch):
    from projmap.tools import adb

    monkeypatch.delenv("ADB", raising=False)
    monkeypatch.setattr(adb.shutil, "which", lambda _: None)
    with pytest.raises(adb.AdbError, match="Platform Tools"):
        adb.find_adb()
