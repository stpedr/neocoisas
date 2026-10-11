"""Sensores de pessoas — contrato + factory (``get_sensor``), padrão do repo.

Todo sensor responde ``players() -> list[Player]`` no espaço da parede
(ver ``world.py``). Providers:

``sim``     pessoa virtual: controlada pela UI/API ou por um roteiro automático
            ("turning": vira de costas e de frente periodicamente) — testa a
            experiência inteira sem hardware.
``osc``     recebe pose por OSC. É o caminho do **Kinect**: o TouchDesigner já lê
            Kinect v2/Azure/Orbbec nativamente (Kinect CHOP) e repassa a cabeça
            por OSC — sem driver nem SDK no nosso processo. Serve também para
            NI mate, ZIG, um script com OpenPose etc.
``phone``   celular na parede, ligado por USB (ADB): a página ``/sensor`` roda a
            detecção de rosto no navegador e manda os pontos por WebSocket.
``webcam``  câmera comum na parede (centro, apontada para o público) + MediaPipe
            FaceLandmarker: posição do rosto → ``x``/``distance``; pose da cabeça
            (solvePnP) → ``yaw``. Rosto não detectado ⇒ pessoa de costas.

Mensagem OSC aceita (porta padrão 7001)::

    /player  id:int  x:float[0..1]  distance:float  yaw_deg:float  tracked:int  [face:int]
    /player/<id>/x | /distance | /yaw | /tracked | /face   (canais avulsos, ex.: CHOP)

``face`` (opcional) diz se o rosto está visível para uma câmera na parede. O
esqueleto do Kinect não distingue bem "de frente" de "de costas"; combinar o
Kinect (posição) com detecção de rosto (ex.: plugin MediaPipe do TouchDesigner)
resolve: ``face = 0`` ⇒ de costas.

``x`` é a posição ao longo da parede (0 = esquerda, 1 = direita), ``distance`` em
alturas de parede, ``yaw`` em graus (0 = olhando a parede, 180 = de costas).
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Optional, Protocol

import numpy as np

from .world import Player

log = logging.getLogger(__name__)


class Sensor(Protocol):
    kind: str

    def players(self) -> list[Player]: ...

    def close(self) -> None: ...


# --------------------------------------------------------------------- sim
class SimSensor:
    """Pessoa virtual. ``script="turning"`` alterna de frente/de costas sozinha."""

    kind = "sim"

    def __init__(self, aspect: float = 16 / 9, script: Optional[str] = "turning", period: float = 8.0):
        self.aspect = aspect
        self.script = script
        self.period = period
        self._player = Player(x=aspect / 2, distance=1.0, yaw=0.0)
        self._t0 = time.monotonic()
        self._lock = threading.Lock()

    def set(self, x: Optional[float] = None, distance: Optional[float] = None, yaw_deg: Optional[float] = None,
            tracked: Optional[bool] = None) -> None:
        """Controle manual (desliga o roteiro). ``x`` em 0..1 da largura da parede."""
        with self._lock:
            self.script = None
            p = self._player
            if x is not None:
                p.x = max(0.0, min(1.0, x)) * self.aspect
            if distance is not None:
                p.distance = max(0.05, distance)
            if yaw_deg is not None:
                p.yaw = math.radians(yaw_deg)
            if tracked is not None:
                p.tracked = tracked

    def players(self) -> list[Player]:
        with self._lock:
            p = self._player
            if self.script == "turning":
                # metade do período de frente (olhando e varrendo a parede), metade de costas
                ph = ((time.monotonic() - self._t0) % self.period) / self.period
                if ph < 0.5:
                    p.yaw = math.radians(35 * math.sin(ph * 4 * math.pi))
                else:
                    p.yaw = math.pi
            return [Player(p.id, p.x, p.distance, p.yaw, p.eye_y, p.tracked, p.face_visible)]

    def close(self) -> None:
        pass


# --------------------------------------------------------------------- osc
class OscSensor:
    kind = "osc"

    def __init__(self, aspect: float = 16 / 9, host: str = "0.0.0.0", port: int = 7001, timeout: float = 1.0):
        from pythonosc.dispatcher import Dispatcher
        from pythonosc.osc_server import ThreadingOSCUDPServer

        self.aspect = aspect
        self.timeout = timeout  # sem mensagens por mais que isso ⇒ pessoa não rastreada
        self._players: dict[int, Player] = {}
        self._seen: dict[int, float] = {}
        self._lock = threading.Lock()
        disp = Dispatcher()
        disp.map("/player", self._on_player)
        disp.map("/player/*", self._on_channel)
        self._server = ThreadingOSCUDPServer((host, port), disp)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, name="osc-sensor", daemon=True)
        self._thread.start()

    def _get(self, pid: int) -> Player:
        if pid not in self._players:
            self._players[pid] = Player(id=pid, x=self.aspect / 2)
        self._seen[pid] = time.monotonic()
        return self._players[pid]

    def _on_player(self, _addr: str, *args) -> None:
        if len(args) < 4:
            return
        pid, x, dist, yaw = int(args[0]), float(args[1]), float(args[2]), float(args[3])
        tracked = bool(int(args[4])) if len(args) > 4 else True
        with self._lock:
            p = self._get(pid)
            p.x, p.distance, p.yaw, p.tracked = x * self.aspect, max(0.05, dist), math.radians(yaw), tracked
            if len(args) > 5:
                p.face_visible = bool(int(args[5]))

    def _on_channel(self, addr: str, *args) -> None:
        parts = addr.strip("/").split("/")
        if len(parts) != 3 or not args:
            return
        try:
            pid, field, value = int(parts[1]), parts[2], float(args[0])
        except ValueError:
            return
        with self._lock:
            p = self._get(pid)
            if field == "x":
                p.x = value * self.aspect
            elif field == "distance":
                p.distance = max(0.05, value)
            elif field == "yaw":
                p.yaw = math.radians(value)
            elif field == "tracked":
                p.tracked = value >= 0.5
            elif field == "face":
                p.face_visible = value >= 0.5

    def players(self) -> list[Player]:
        now = time.monotonic()
        with self._lock:
            out = []
            for pid, p in self._players.items():
                fresh = now - self._seen.get(pid, 0) <= self.timeout
                out.append(Player(p.id, p.x, p.distance, p.yaw, p.eye_y, p.tracked and fresh, p.face_visible))
            return out

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


# ------------------------------------------------------------------ webcam
# Modelo 3D genérico de rosto (mm; x para a ESQUERDA DA PESSOA, y para cima, z para
# fora do rosto) e índices da malha de 468 pontos do MediaPipe. Atenção ao lado: o
# ponto 263 (olho esquerdo da pessoa) aparece à DIREITA da imagem quando a pessoa
# encara a câmera. Com o lado trocado, o solvePnP só "encaixa" girando o rosto 180°
# — e uma pessoa de frente vira "de costas" (bug pego com landmarks reais).
FACE_MODEL_3D = np.array([
    (0.0, 0.0, 0.0),        # 1   ponta do nariz
    (0.0, -63.6, -12.5),    # 152 queixo
    (43.3, 32.7, -26.0),    # 263 canto externo do olho esquerdo (da pessoa)
    (-43.3, 32.7, -26.0),   # 33  canto externo do olho direito
    (28.9, -28.9, -24.1),   # 291 canto esquerdo da boca
    (-28.9, -28.9, -24.1),  # 61  canto direito da boca
], dtype=np.float64)
FACE_LANDMARKS = [1, 152, 263, 33, 291, 61]


def head_yaw_from_points(image_points: np.ndarray, width: int, height: int) -> Optional[float]:
    """Yaw da cabeça (rad) a partir dos 6 pontos 2D (px), via solvePnP.

    0 = olhando para a câmera; positivo = cabeça girada para a direita da
    imagem. A câmera fica na parede, então "olhando a câmera" ≈ olhando a parede.
    """
    import cv2

    f = float(width)  # focal aproximada: suficiente para o ângulo
    cam = np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1]], dtype=np.float64)
    ok, rvec, _ = cv2.solvePnP(FACE_MODEL_3D, image_points.astype(np.float64), cam, None,
                               flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return None
    rot, _ = cv2.Rodrigues(rvec)
    # Direção para onde o rosto aponta (eixo +z do modelo) no referencial da câmera.
    forward = rot @ np.array([0.0, 0.0, 1.0])
    # Olhando a câmera, o rosto aponta para -z da câmera; yaw = desvio horizontal.
    return math.atan2(forward[0], -forward[2])


def apply_face(p: Player, norm_pts, width: int, height: int, aspect: float, mirror: bool = True,
               distance_scale: float = 0.18) -> None:
    """Atualiza a pessoa a partir dos 6 pontos do rosto (normalizados 0..1, ordem de
    ``FACE_LANDMARKS``: nariz, queixo, olho esq., olho dir., boca esq., boca dir.).

    Usado pela webcam local e pelo celular (que manda só esses pontos). Supõe a
    câmera **na parede, olhando o público**: a esquerda da imagem é a direita de
    quem olha a parede, daí ``mirror`` (x e yaw invertidos).
    """
    pts = np.array([(x * width, y * height) for x, y in norm_pts], dtype=np.float64)
    yaw = head_yaw_from_points(pts, width, height)
    nose_x = norm_pts[0][0]
    iod = math.dist(pts[2], pts[3]) / width  # distância entre os olhos, fração da largura
    p.x = ((1 - nose_x) if mirror else nose_x) * aspect
    p.distance = max(0.2, distance_scale / max(iod, 1e-3))
    if yaw is not None:
        p.yaw = -yaw if mirror else yaw
    p.tracked, p.face_visible = True, True


# -------------------------------------------------------------------- phone
class PhoneSensor:
    """Celular como sensor: a página ``/sensor`` roda o MediaPipe no navegador e
    manda os 6 pontos do rosto por WebSocket (``/api/interact/phone``).

    Com o celular ligado por USB e ``adb reverse tcp:8100 tcp:8100``, a página abre
    em ``http://localhost:8100/sensor`` — ``localhost`` é contexto seguro, então o
    navegador libera a câmera sem HTTPS, e o tráfego vai pelo cabo (sem Wi-Fi).
    O processamento pesado (rede neural do rosto) fica no celular; o PC só faz o
    ``solvePnP`` (mesma função testada da webcam).
    """

    kind = "phone"

    def __init__(self, aspect: float = 16 / 9, mirror: bool = True, distance_scale: float = 0.18,
                 timeout: float = 2.0, face_lost_after: float = 0.35):
        self.aspect, self.mirror, self.distance_scale, self.timeout = aspect, mirror, distance_scale, timeout
        # Histerese: a detecção "pisca" (frame sem rosto no meio de vários com rosto).
        # Só declaramos "de costas" depois de um tempo contínuo sem rosto — senão cada
        # piscada faria os fantasmas darem um tranco para a frente.
        self.face_lost_after = face_lost_after
        self._player = Player(x=aspect / 2, tracked=False)
        self._last = 0.0
        self._noface_since: Optional[float] = None
        self._lock = threading.Lock()
        self.fps = 0.0
        self.connected = 0

    def update(self, msg: dict) -> None:
        """Mensagem da página: ``{face: bool, pts: [[x,y]×6], w, h, mirror?, fps?}``."""
        with self._lock:
            p = self._player
            self._last = time.monotonic()
            self.fps = float(msg.get("fps") or 0.0)
            mirror = bool(msg.get("mirror", self.mirror))
            if not msg.get("face"):
                now = self._last
                if self._noface_since is None:
                    self._noface_since = now
                if now - self._noface_since >= self.face_lost_after or p.face_visible is None:
                    p.face_visible = False  # sem rosto por um tempo: de costas (mantém a posição)
                p.tracked = True
                return
            self._noface_since = None
            pts = msg.get("pts") or []
            w, h = int(msg.get("w") or 0), int(msg.get("h") or 0)
            if len(pts) != len(FACE_LANDMARKS) or w <= 0 or h <= 0:
                raise ValueError("mensagem do celular inválida: esperado pts com 6 pontos, w e h")
            apply_face(p, [(float(x), float(y)) for x, y in pts], w, h, self.aspect, mirror, self.distance_scale)

    def players(self) -> list[Player]:
        with self._lock:
            p = self._player
            fresh = time.monotonic() - self._last <= self.timeout
            return [Player(p.id, p.x, p.distance, p.yaw, p.eye_y, p.tracked and fresh, p.face_visible)]

    def close(self) -> None:
        pass


class WebcamSensor:
    kind = "webcam"

    def __init__(self, aspect: float = 16 / 9, camera: int = 0, model_path: Optional[str] = None,
                 mirror: bool = True, distance_scale: float = 0.18):
        import os

        import cv2

        try:
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python import vision
            import mediapipe as mp
        except ImportError as exc:  # pragma: no cover — depende do ambiente
            raise RuntimeError("sensor webcam requer: pip install mediapipe") from exc
        model_path = model_path or os.environ.get("PROJMAP_FACE_MODEL", "models/face_landmarker.task")
        if not os.path.isfile(model_path):
            raise RuntimeError(
                f"modelo do MediaPipe não encontrado em {model_path}. Baixe 'face_landmarker.task' "
                "(MediaPipe Face Landmarker) e aponte PROJMAP_FACE_MODEL para ele."
            )
        self._mp = mp
        self._landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO, num_faces=1))
        self._cap = cv2.VideoCapture(camera)
        if not self._cap.isOpened():
            raise RuntimeError(f"não abriu a câmera {camera}")
        self.aspect, self.mirror, self.distance_scale = aspect, mirror, distance_scale
        self._player = Player(x=aspect / 2, tracked=False)
        self._lock = threading.Lock()
        self._stop = False
        self._thread = threading.Thread(target=self._run, name="webcam-sensor", daemon=True)
        self._thread.start()

    def _run(self) -> None:  # pragma: no cover — precisa de câmera
        import cv2

        t0 = time.monotonic()
        while not self._stop:
            ok, frame = self._cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
            result = self._landmarker.detect_for_video(image, int((time.monotonic() - t0) * 1000))
            with self._lock:
                p = self._player
                if not result.face_landmarks:
                    p.face_visible = False  # sem rosto: de costas (ou saiu) — mantém a última posição
                    continue
                lm = result.face_landmarks[0]
                norm = [(lm[i].x, lm[i].y) for i in FACE_LANDMARKS]
                apply_face(p, norm, w, h, self.aspect, self.mirror, self.distance_scale)

    def players(self) -> list[Player]:
        with self._lock:
            p = self._player
            return [Player(p.id, p.x, p.distance, p.yaw, p.eye_y, p.tracked, p.face_visible)]

    def close(self) -> None:
        self._stop = True
        self._thread.join(timeout=2)
        self._cap.release()


def get_sensor(kind: str = "sim", aspect: float = 16 / 9, **options) -> Sensor:
    if kind == "sim":
        return SimSensor(aspect=aspect, **options)
    if kind == "osc":
        return OscSensor(aspect=aspect, **options)
    if kind == "webcam":
        return WebcamSensor(aspect=aspect, **options)
    if kind == "phone":
        return PhoneSensor(aspect=aspect, **options)
    raise ValueError(f"sensor desconhecido: {kind} (sim | osc | webcam | phone)")
