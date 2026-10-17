"""Rastreamento multi-pessoa — tradução de ``FiltroUmEuro.h`` e
``RastreadorPessoas.cpp`` do visual_frames (estilo ByteTrack, sem Kalman)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import config as C

NUM_KEYPOINTS = 17
# Mesma ordem do ``enum`` de ``DetectorPessoas.h`` (COCO): "E"/"D" são os lados
# que o modelo rotula pela aparência, não os lados da tela.
NARIZ, OLHO_E, OLHO_D, ORELHA_E, ORELHA_D = 0, 1, 2, 3, 4
OMBRO_E, OMBRO_D, COTOVELO_E, COTOVELO_D, PULSO_E, PULSO_D = 5, 6, 7, 8, 9, 10
QUADRIL_E, QUADRIL_D, JOELHO_E, JOELHO_D, TORNOZELO_E, TORNOZELO_D = 11, 12, 13, 14, 15, 16


class OneEuro:
    """One Euro Filter (Casiez, Roussel, Vogel — CHI 2012)."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.0, d_cutoff: float = 1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.started = False
        self.prev = 0.0
        self.deriv = 0.0

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, value: float, dt: float) -> float:
        if not self.started or dt <= 0:
            self.started, self.prev, self.deriv = True, value, 0.0
            return value
        raw = (value - self.prev) / dt
        self.deriv += self._alpha(self.d_cutoff, dt) * (raw - self.deriv)
        cutoff = self.min_cutoff + self.beta * abs(self.deriv)
        self.prev += self._alpha(cutoff, dt) * (value - self.prev)
        return self.prev

    def reset(self) -> None:
        self.started = False

    @property
    def velocity(self) -> float:
        return self.deriv


@dataclass
class Detection:
    box: np.ndarray  # x1, y1, x2, y2 (pixels da câmera)
    conf: float
    has_pose: bool = False
    points: np.ndarray = field(default_factory=lambda: np.zeros((NUM_KEYPOINTS, 3), np.float32))  # x, y, vis
    mask_logits: np.ndarray | None = None  # logits só na região (coordenadas da máscara)
    mask_region: tuple[int, int, int, int] | None = None  # x, y, w, h na máscara


def iou(a: np.ndarray, b: np.ndarray) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _area(b: np.ndarray) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a: np.ndarray, b: np.ndarray) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


@dataclass
class Track:
    id: int
    slot: int
    box: np.ndarray
    vel: np.ndarray = field(default_factory=lambda: np.zeros(2, np.float32))  # px/quadro
    conf: float = 0.0
    lost: int = 0
    age: int = 0
    detection: int = -1
    points: np.ndarray = field(default_factory=lambda: np.zeros((NUM_KEYPOINTS, 3), np.float32))
    unseen: np.ndarray = field(default_factory=lambda: np.full(NUM_KEYPOINTS, C.KEYPOINT_DECAIMENTO_S, np.float32))
    fx: list = field(default_factory=list)
    fy: list = field(default_factory=list)
    wrist_speed_l: float = 0.0
    wrist_speed_r: float = 0.0

    def __post_init__(self) -> None:
        if not self.fx:
            self.fx = [OneEuro(C.EURO_MIN_CUTOFF, C.EURO_BETA, C.EURO_D_CUTOFF) for _ in range(NUM_KEYPOINTS)]
            self.fy = [OneEuro(C.EURO_MIN_CUTOFF, C.EURO_BETA, C.EURO_D_CUTOFF) for _ in range(NUM_KEYPOINTS)]


def _match(tracks: list[Track], t_idx: list[int], dets: list[Detection], d_idx: list[int], min_iou: float):
    cands = [(iou(tracks[t].box, dets[d].box), t, d) for t in t_idx for d in d_idx]
    cands = sorted((c for c in cands if c[0] >= min_iou), reverse=True)
    used_t, used_d, pairs = set(), set(), []
    for v, t, d in cands:
        if t in used_t or d in used_d:
            continue
        used_t.add(t), used_d.add(d)
        pairs.append((t, d))
    return pairs


class Tracker:
    def __init__(self) -> None:
        self.tracks: list[Track] = []
        self._next_id = 1

    def update(self, dets: list[Detection], dt: float) -> None:
        for tr in self.tracks:  # predição: caixa anda com a velocidade estimada
            tr.box = tr.box + np.array([tr.vel[0], tr.vel[1], tr.vel[0], tr.vel[1]], np.float32)
            tr.detection = -1
        high = [i for i, d in enumerate(dets) if d.conf >= C.LIMIAR_DETECCAO_ALTO]
        low = [i for i, d in enumerate(dets) if d.conf < C.LIMIAR_DETECCAO_ALTO]
        pending = list(range(len(self.tracks)))
        for t, d in _match(self.tracks, pending, dets, high, C.IOU_MINIMO_ASSOCIACAO):
            self._apply(self.tracks[t], dets[d], d, dt)
            pending.remove(t), high.remove(d)
        active = [t for t in pending if self.tracks[t].lost == 0]
        for t, d in _match(self.tracks, active, dets, low, C.IOU_MINIMO_SEGUNDA_ETAPA):
            self._apply(self.tracks[t], dets[d], d, dt)
            pending.remove(t)
        for t in pending:
            tr = self.tracks[t]
            tr.lost += 1
            tr.vel *= 0.8
            tr.unseen += dt
            tr.wrist_speed_l *= 0.8
            tr.wrist_speed_r *= 0.8
        self.tracks = [tr for tr in self.tracks if tr.lost <= C.QUADROS_MEMORIA_PERDIDA]
        for d in high:
            box = dets[d].box
            contained = any(tr.lost == 0 and _inter(tr.box, box) > C.CONTENCAO_DUPLICATA * min(_area(tr.box), _area(box))
                            for tr in self.tracks)
            if dets[d].conf < C.LIMIAR_NOVA_PESSOA or contained:
                continue
            slot = self._free_slot()
            if slot < 0:
                break
            tr = Track(self._next_id, slot, box.copy())
            self._next_id += 1
            self.tracks.append(tr)
            self._apply(tr, dets[d], d, dt)

    def _apply(self, tr: Track, det: Detection, idx: int, dt: float) -> None:
        if tr.age > 0:
            c_new = (det.box[:2] + det.box[2:]) * 0.5
            c_old = (tr.box[:2] + tr.box[2:]) * 0.5
            disp = c_new - c_old + tr.vel  # caixa já foi movida pela predição
            tr.vel = tr.vel * 0.6 + disp * 0.4
        tr.box = det.box.copy()
        tr.conf = det.conf
        tr.lost = 0
        tr.age += 1
        tr.detection = idx
        body_h = max(det.box[3] - det.box[1], 1.0)
        for k in range(NUM_KEYPOINTS):
            x, y, vis = det.points[k]
            if not det.has_pose or vis < C.LIMIAR_KEYPOINT:
                tr.unseen[k] += dt
                continue
            if tr.unseen[k] >= C.KEYPOINT_DECAIMENTO_S:  # sumiu demais: reaparece sem deslizar
                tr.fx[k].reset(), tr.fy[k].reset()
            tr.points[k] = (tr.fx[k](float(x), dt), tr.fy[k](float(y), dt), vis)
            tr.unseen[k] = 0.0

        def speed(k: int) -> float:
            if tr.unseen[k] > 0:
                return 0.0
            return math.hypot(tr.fx[k].velocity, tr.fy[k].velocity) / body_h

        tr.wrist_speed_l, tr.wrist_speed_r = speed(PULSO_E), speed(PULSO_D)

    def _free_slot(self) -> int:
        used = {tr.slot for tr in self.tracks}
        return next((s for s in range(C.MAX_PESSOAS) if s not in used), -1)
