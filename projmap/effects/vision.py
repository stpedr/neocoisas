"""Thread de visão — tradução de ``ProcessadorVisao.cpp`` do visual_frames.

câmera (C920, MJPG 720p) → detector YOLO → rastreador → máscara composta
(cada pixel fica com a pessoa de maior logit; sigmoid; filtro guiado; mistura
temporal) → ``VisionResult`` publicado sob trava.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from . import config as C
from .detector import PersonDetector
from .tracker import NUM_KEYPOINTS, Tracker

log = logging.getLogger(__name__)
LOGIT_VAZIO = -20.0


@dataclass
class VisiblePerson:
    id: int
    slot: int
    active: bool
    box: np.ndarray  # pixels da câmera
    points: np.ndarray  # (17, 3): x, y (pixels), frescor 0..1
    wrist_speed_l: float
    wrist_speed_r: float


@dataclass
class VisionResult:
    seq: int = 0
    mask: Optional[np.ndarray] = None  # (360, 640, 2) uint8: [alpha, slot+1]
    people: list[VisiblePerson] = field(default_factory=list)
    frame: Optional[np.ndarray] = None  # BGR espelhado (LEGO/paraquedas)
    comic: Optional[np.ndarray] = None  # (360, 640, 4) RGBA: cor chapada + A = tinta
    frame_ms: float = 0.0
    gpu: bool = False


def guided_filter(guide: np.ndarray, src: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Filtro guiado (He, Sun, Tang — 2010), guia em cinza [0,1]. Equivale ao
    ``cv::ximgproc::guidedFilter`` usado no original (que não existe no
    OpenCV sem contrib)."""
    k = (2 * r + 1, 2 * r + 1)
    box = lambda a: cv2.boxFilter(a, cv2.CV_32F, k, borderType=cv2.BORDER_REFLECT)  # noqa: E731
    mean_i, mean_p = box(guide), box(src)
    cov_ip = box(guide * src) - mean_i * mean_p
    var_i = box(guide * guide) - mean_i * mean_i
    a = cov_ip / (var_i + eps)
    b = mean_p - a * mean_i
    return box(a) * guide + box(b)


def _flatten_colors(small_bgr: np.ndarray) -> np.ndarray:
    """Suavização que preserva bordas, para a cor chapada da HQ.

    O original roda ``bilateralFilter(7, 60, 7)`` na resolução da máscara, que
    custa 10 ms dos 33 ms de um quadro. Em metade da resolução o mesmo filtro
    custa 0,9 ms e, como o resultado ainda passa pela posterização em 3 tons
    logo abaixo, só ~4% dos pixels mudam de tom (diferença média 0,2/255).
    """
    h, w = small_bgr.shape[:2]
    half = cv2.resize(small_bgr, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    half = cv2.bilateralFilter(half, 5, 60, 5)
    return cv2.resize(half, (w, h), interpolation=cv2.INTER_LINEAR)


def stylize_comic(frame_bgr: np.ndarray) -> np.ndarray:
    """Estilo HQ em 640x360: traço XDoG (Winnemöller 2012) + cor chapada em 3 tons."""
    small = cv2.resize(frame_bgr, (C.MASCARA_LARGURA, C.MASCARA_ALTURA), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    g1 = cv2.GaussianBlur(gray, (0, 0), C.XDOG_SIGMA)
    g2 = cv2.GaussianBlur(gray, (0, 0), C.XDOG_SIGMA * C.XDOG_K)
    d = g1 - C.XDOG_TAU * g2
    t = np.where(d >= C.XDOG_EPS, 1.0, 1.0 + np.tanh(C.XDOG_PHI * (d - C.XDOG_EPS)))
    ink = np.clip((1.0 - t) * 255.0, 0, 255).astype(np.uint8)
    hsv = cv2.cvtColor(_flatten_colors(small), cv2.COLOR_BGR2HSV)
    hsv[..., 1] = np.clip(hsv[..., 1].astype(np.float32) * 1.6 + 25, 0, 255).astype(np.uint8)
    v = hsv[..., 2]
    hsv[..., 2] = np.where(v < 85, 70, np.where(v < 170, 165, 245)).astype(np.uint8)
    flat = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    return np.dstack([flat, ink])


class VisionProcessor:
    def __init__(self, models_dir: Path, camera: "int | str" = "auto",
                 open_camera: Optional[Callable] = None):
        self.models_dir = Path(models_dir)
        self.camera = camera
        self._open_camera = open_camera
        self._lock = threading.Lock()
        self._last = VisionResult()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.status = "iniciando…"
        self.want_comic = False
        self.want_frame = False
        self.detector: Optional[PersonDetector] = None
        self.tracker = Tracker()
        size = (C.MASCARA_ALTURA, C.MASCARA_LARGURA)
        self._best = np.empty(size, np.float32)
        self._slot = np.zeros(size, np.uint8)
        self._slot_prev = np.zeros(size, np.uint8)
        self._alpha_smooth = np.zeros(size, np.float32)

    # ------------------------------------------------------------------ vida
    def start(self) -> "VisionProcessor":
        self._thread = threading.Thread(target=self._loop, name="vf-visao", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def latest(self, known_seq: int) -> Optional[VisionResult]:
        with self._lock:
            return self._last if self._last.seq > known_seq else None

    # ---------------------------------------------------------------- câmera
    def _open(self):
        if self._open_camera:
            return self._open_camera()
        from ..interact.cameras import choose_camera, list_cameras, open_camera

        cam = choose_camera(list_cameras(), self.camera)
        if cam is None:
            raise RuntimeError(f"câmera '{self.camera}' não encontrada")
        cap, got = open_camera(cam.index, C.CAMERA_LARGURA, C.CAMERA_ALTURA, C.CAMERA_FPS)
        log.info("visual_frames: câmera %s em %dx%d", cam.name, got[0], got[1])
        return cap

    def _loop(self) -> None:
        try:
            self.detector = PersonDetector(self.models_dir / "yolo26n-seg.onnx", self.models_dir / "yolo26s-pose.onnx")
        except Exception as exc:  # noqa: BLE001
            self.status = f"falha ao carregar os modelos: {exc}"
            log.error(self.status)
            return
        cap = None
        prev = time.perf_counter()
        while not self._stop.is_set():
            if cap is None:
                try:
                    cap = self._open()
                    self.status = ""
                except Exception as exc:  # noqa: BLE001
                    self.status = f"câmera indisponível: {exc}"
                    time.sleep(1.0)
                    continue
            ok, raw = cap.read()
            if not ok or raw is None:
                cap.release()
                cap = None
                self.status = "sem quadros da câmera, tentando de novo…"
                time.sleep(0.5)
                continue
            t0 = time.perf_counter()
            if raw.shape[1] != C.CAMERA_LARGURA or raw.shape[0] != C.CAMERA_ALTURA:
                raw = cv2.resize(raw, (C.CAMERA_LARGURA, C.CAMERA_ALTURA))
            frame = cv2.flip(raw, 1) if C.CAMERA_ESPELHAR else raw
            dt, prev = t0 - prev, t0
            self.process(frame, min(dt, 0.25), t0)
        if cap is not None:
            cap.release()

    # --------------------------------------------------------------- um quadro
    def process(self, frame: np.ndarray, dt: float, t0: Optional[float] = None) -> VisionResult:
        """Processa um quadro BGR 1280x720 já espelhado (público para testes)."""
        t0 = t0 or time.perf_counter()
        dets = self.detector.detect(frame)
        self.tracker.update(dets, dt)
        self._compose(dets, frame)
        return self._publish(frame, (time.perf_counter() - t0) * 1000)

    def _compose(self, dets, frame: np.ndarray) -> None:
        self._best.fill(LOGIT_VAZIO)
        self._slot.fill(0)
        for tr in self.tracker.tracks:
            if tr.detection < 0:
                continue
            d = dets[tr.detection]
            if d.mask_logits is None:
                continue
            x, y, w, h = d.mask_region
            region = self._best[y:y + h, x:x + w]
            bigger = d.mask_logits > region
            region[bigger] = d.mask_logits[bigger]
            self._slot[y:y + h, x:x + w][bigger] = tr.slot + 1
        alpha = 1.0 / (1.0 + np.exp(-self._best))
        if C.MASCARA_FILTRO_GUIADO:
            small = cv2.resize(frame, (C.MASCARA_LARGURA, C.MASCARA_ALTURA), interpolation=cv2.INTER_AREA)
            guide = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            alpha = np.clip(guided_filter(guide, alpha.astype(np.float32), C.FILTRO_GUIADO_RAIO, C.FILTRO_GUIADO_EPS), 0, 1)
        w = C.MASCARA_PESO_QUADRO_ATUAL
        self._alpha_smooth = alpha * w + self._alpha_smooth * (1 - w)
        np.copyto(self._slot_prev, self._slot, where=self._slot > 0)

    def _publish(self, frame: np.ndarray, frame_ms: float) -> VisionResult:
        alpha8 = np.clip(self._alpha_smooth * 255.0, 0, 255).astype(np.uint8)
        res = VisionResult(mask=np.dstack([alpha8, self._slot_prev.copy()]), frame_ms=frame_ms,
                           gpu=bool(self.detector and self.detector.gpu))
        for tr in self.tracker.tracks:
            pts = tr.points.copy()
            pts[:, 2] = np.maximum(0.0, 1.0 - tr.unseen / C.KEYPOINT_DECAIMENTO_S)
            res.people.append(VisiblePerson(tr.id, tr.slot, tr.lost == 0, tr.box.copy(), pts,
                                            tr.wrist_speed_l, tr.wrist_speed_r))
        if self.want_frame:
            res.frame = frame.copy()
        if self.want_comic:
            res.comic = stylize_comic(frame)
        with self._lock:
            res.seq = self._last.seq + 1
            self._last = res
        return res
