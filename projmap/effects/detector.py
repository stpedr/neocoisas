"""Detector de pessoas — tradução de ``DetectorPessoas.cpp`` do visual_frames.

Dois modelos YOLO26 em paralelo sobre o mesmo tensor: segmentação
(``yolo26n-seg``) e pose (``yolo26s-pose``). No Windows roda na GPU via
DirectML (NVIDIA/AMD/Intel); sem GPU cai para CPU (lento: ~350 ms/quadro).

Saídas end-to-end (nms=False): ``[x1,y1,x2,y2,conf,cls,…extras]`` por linha,
ordenadas por confiança; extras = 17×(x,y,vis) na pose, 32 coeficientes na seg
(+ protótipo ``(32, 96, 160)``).
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from . import config as C
from .tracker import NUM_KEYPOINTS, Detection, iou

log = logging.getLogger(__name__)

CAMPOS_BASE = 6
COEFICIENTES_MASCARA = 32


def _session(path: Path):
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = ["CPUExecutionProvider"]
    if "DmlExecutionProvider" in ort.get_available_providers():
        so.enable_mem_pattern = False  # exigido pelo DirectML
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # Notebook com duas placas (Intel + NVIDIA): sem isso o DirectML pode cair
        # na integrada (61,9 ms vs 4,6 ms na RTX 4060 medidos). "high_performance"
        # escolhe a placa dedicada.
        providers = [("DmlExecutionProvider", {"performance_preference": "high_performance", "device_filter": "gpu"}),
                     "CPUExecutionProvider"]
    elif "CUDAExecutionProvider" in ort.get_available_providers():
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    s = ort.InferenceSession(str(path), so, providers=providers)
    return s, s.get_providers()[0]


class PersonDetector:
    def __init__(self, seg_model: Path, pose_model: Path):
        self.seg, p1 = _session(seg_model)
        self.pose, p2 = _session(pose_model)
        self.gpu = p1 != "CPUExecutionProvider" and p2 != "CPUExecutionProvider"
        self.provider = p1
        log.info("detector visual_frames em %s", p1)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pose")
        # transformação câmera -> letterbox
        self.scale = min(C.ENTRADA_LARGURA / C.CAMERA_LARGURA, C.ENTRADA_ALTURA / C.CAMERA_ALTURA)
        self.cw = round(C.CAMERA_LARGURA * self.scale)
        self.ch = round(C.CAMERA_ALTURA * self.scale)
        self.bx = (C.ENTRADA_LARGURA - self.cw) // 2
        self.by = (C.ENTRADA_ALTURA - self.ch) // 2

    # ------------------------------------------------------------------ entrada
    def preprocess(self, frame_bgr: np.ndarray) -> np.ndarray:
        small = cv2.resize(frame_bgr, (self.cw, self.ch), interpolation=cv2.INTER_LINEAR)
        padded = cv2.copyMakeBorder(small, self.by, C.ENTRADA_ALTURA - self.ch - self.by,
                                    self.bx, C.ENTRADA_LARGURA - self.cw - self.bx,
                                    cv2.BORDER_CONSTANT, value=(114, 114, 114))
        rgb = padded[..., ::-1].astype(np.float32) * (1.0 / 255.0)
        return np.ascontiguousarray(rgb.transpose(2, 0, 1)[None])

    def _to_camera(self, d: np.ndarray) -> np.ndarray:
        return np.array([(d[0] - self.bx) / self.scale, (d[1] - self.by) / self.scale,
                         (d[2] - self.bx) / self.scale, (d[3] - self.by) / self.scale], np.float32)

    def _valid(self, box: np.ndarray) -> bool:
        return (box[3] - box[1]) >= C.ALTURA_MINIMA_PESSOA * C.CAMERA_ALTURA

    @staticmethod
    def _duplicate(kept: list[Detection], box: np.ndarray) -> bool:
        return any(iou(o.box, box) > C.IOU_DUPLICATA for o in kept)

    # ------------------------------------------------------------- saídas seg
    def read_seg(self, det: np.ndarray, proto: np.ndarray) -> list[Detection]:
        out: list[Detection] = []
        ph, pw = proto.shape[1:]
        ps = pw / C.ENTRADA_LARGURA
        rx, ry = round(self.bx * ps), round(self.by * ps)
        rw, rh = round(self.cw * ps), round(self.ch * ps)
        mscale = C.MASCARA_LARGURA / C.CAMERA_LARGURA
        for d in det:
            if len(out) >= 2 * C.MAX_PESSOAS or d[4] < C.LIMIAR_DETECCAO_BAIXO:
                break  # ordenado por confiança
            if int(d[5]) != 0:
                continue
            box = self._to_camera(d)
            if not self._valid(box) or self._duplicate(out, box):
                continue
            m = C.MASCARA_MARGEM_CAIXA / self.scale
            x0 = max(0, math.floor((box[0] - m) * mscale))
            y0 = max(0, math.floor((box[1] - m) * mscale))
            x1 = min(C.MASCARA_LARGURA, math.ceil((box[2] + m) * mscale))
            y1 = min(C.MASCARA_ALTURA, math.ceil((box[3] + m) * mscale))
            if x1 <= x0 or y1 <= y0:
                continue
            sx, sy = rw / C.MASCARA_LARGURA, rh / C.MASCARA_ALTURA
            ox, oy = (x0 + 0.5) * sx - 0.5 + rx, (y0 + 0.5) * sy - 0.5 + ry
            px0, py0 = max(0, math.floor(ox) - 1), max(0, math.floor(oy) - 1)
            px1 = min(pw, math.ceil(ox + (x1 - x0) * sx) + 2)
            py1 = min(ph, math.ceil(oy + (y1 - y0) * sy) + 2)
            coef = d[CAMPOS_BASE:CAMPOS_BASE + COEFICIENTES_MASCARA]
            logits = np.tensordot(coef, proto[:, py0:py1, px0:px1], axes=1).astype(np.float32)
            M = np.array([[sx, 0, ox - px0], [0, sy, oy - py0]], np.float64)
            warped = cv2.warpAffine(logits, M, (x1 - x0, y1 - y0),
                                    flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
            out.append(Detection(box, float(d[4]), mask_logits=warped, mask_region=(x0, y0, x1 - x0, y1 - y0)))
        return out

    # ------------------------------------------------------------ saídas pose
    def read_pose(self, det: np.ndarray) -> list[Detection]:
        out: list[Detection] = []
        for d in det:
            if len(out) >= 2 * C.MAX_PESSOAS or d[4] < C.LIMIAR_DETECCAO_BAIXO:
                break
            box = self._to_camera(d)
            if not self._valid(box) or self._duplicate(out, box):
                continue
            kp = d[CAMPOS_BASE:CAMPOS_BASE + 3 * NUM_KEYPOINTS].reshape(NUM_KEYPOINTS, 3).copy()
            kp[:, 0] = (kp[:, 0] - self.bx) / self.scale
            kp[:, 1] = (kp[:, 1] - self.by) / self.scale
            out.append(Detection(box, float(d[4]), has_pose=True, points=kp.astype(np.float32)))
        return out

    # -------------------------------------------------------------------- passo
    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        x = self.preprocess(frame_bgr)
        pose_feed = {self.pose.get_inputs()[0].name: x}
        seg_feed = {self.seg.get_inputs()[0].name: x}
        if self.provider == "DmlExecutionProvider":
            # O DirectML não aceita duas sessões rodando ao mesmo tempo no mesmo
            # dispositivo (o CUDA do original aceita). Em sequência dá ~10 ms
            # numa RTX 4060, bem dentro dos 33 ms de um quadro.
            seg_out = self.seg.run(None, seg_feed)
            pose_out = self.pose.run(None, pose_feed)
        else:
            fut = self._pool.submit(self.pose.run, None, pose_feed)
            seg_out = self.seg.run(None, seg_feed)
            pose_out = fut.result()
        people = self.read_seg(seg_out[0][0], seg_out[1][0])
        poses = self.read_pose(pose_out[0][0])
        used = [False] * len(poses)
        for p in people:  # casamento guloso pose <-> máscara por IoU
            best, best_iou = -1, C.IOU_POSE_SEGMENTACAO
            for j, q in enumerate(poses):
                if not used[j]:
                    v = iou(p.box, q.box)
                    if v > best_iou:
                        best, best_iou = j, v
            if best >= 0:
                used[best] = True
                p.has_pose, p.points = True, poses[best].points
                p.conf = max(p.conf, poses[best].conf)
        people += [q for j, q in enumerate(poses) if not used[j]]
        people.sort(key=lambda d: -d.conf)
        return people
