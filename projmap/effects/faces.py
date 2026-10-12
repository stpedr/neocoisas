"""Recorte de rostos — tradução de ``recortarRostos()`` do ``ofApp.cpp`` do
visual_frames.

Recorta o rosto de cada pessoa do quadro da câmera numa imagem 256×256:
centrado entre os olhos e o nariz, tamanho pela distância entre os olhos,
girado para ficar reto, luz corrigida (CLAHE no canal L do Lab, bom para rosto
escuro ou contraluz) e uma leve nitidez. É o rosto que vai na cabeça dos
paraquedistas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from . import config as C
from .tracker import NARIZ, OLHO_D, OLHO_E

LADO = 256
L, A = float(C.CAMERA_LARGURA), float(C.CAMERA_ALTURA)


@dataclass
class FaceCrop:
    """Rosto de uma pessoa, já recortado, endireitado e com a luz corrigida
    (imagem quadrada RGB com o rosto centralizado)."""

    slot: int
    presenca: float
    imagem: np.ndarray  # (256, 256, 3) RGB
    de_frente: bool  # olhando para a câmera agora


class _Enquadramento:
    """Enquadramento suavizado de um slot, para o rosto não tremer no recorte."""

    def __init__(self) -> None:
        self.iniciado = False
        self.de_frente = False
        self.centro = np.zeros(2, np.float32)
        self.lado = 0.0
        self.angulo = 0.0
        self.imagem: Optional[np.ndarray] = None  # último rosto bom


class FaceCropper:
    def __init__(self) -> None:
        self._clahe = cv2.createCLAHE(2.5, (4, 4))
        self._slots: dict[int, _Enquadramento] = {}

    def forget(self, slot: int) -> None:
        self._slots.pop(slot, None)

    def crop(self, frame_bgr: np.ndarray, slot: int, pontos: np.ndarray,
             cabeca_centro: np.ndarray, cabeca_raio: float, cabeca_dir: np.ndarray) -> None:
        """Atualiza o rosto do slot a partir de um quadro BGR da câmera.

        ``pontos``: (17, 3) em uv + confiança. Só o rosto **de frente** (olhos e
        nariz visíveis) é atualizado; de lado ou de costas o recorte pegaria
        nuca/cabelo, então fica o último rosto bom.
        """
        est = self._slots.setdefault(slot, _Enquadramento())

        def ponto(k: int) -> np.ndarray:
            return np.array([pontos[k, 0] * L, pontos[k, 1] * A], np.float32)

        def visivel(k: int) -> bool:
            return float(pontos[k, 2]) > 0.3

        est.de_frente = (float(pontos[OLHO_E, 2]) > 0.5 and float(pontos[OLHO_D, 2]) > 0.5
                         and float(pontos[NARIZ, 2]) > 0.5)
        if not est.de_frente:
            return

        if visivel(OLHO_E) and visivel(OLHO_D):
            meio_olhos = 0.5 * (ponto(OLHO_E) + ponto(OLHO_D))
            d = ponto(OLHO_D) - ponto(OLHO_E)
            distancia = max(float(np.hypot(d[0], d[1])), 6.0)
            baixo = np.array([-cabeca_dir[1], cabeca_dir[0]], np.float32)  # perpendicular aos olhos, para o queixo
            centro = (meio_olhos + (ponto(NARIZ) - meio_olhos) * 0.45 if visivel(NARIZ)
                      else meio_olhos + baixo * distancia * 0.35)
            lado = 3.4 * distancia
        else:
            centro = np.array([cabeca_centro[0] * L, cabeca_centro[1] * A], np.float32)
            lado = cabeca_raio * A * 2.6
        lado = max(lado, 24.0)
        angulo = math.degrees(math.atan2(float(cabeca_dir[1]), float(cabeca_dir[0])))

        if not est.iniciado:
            est.iniciado = True
            est.centro, est.lado, est.angulo = centro, lado, angulo
        else:
            est.centro = est.centro + (centro - est.centro) * 0.5
            est.lado += (lado - est.lado) * 0.3
            est.angulo += (angulo - est.angulo) * 0.4

        m = cv2.getRotationMatrix2D((float(est.centro[0]), float(est.centro[1])), est.angulo, LADO / est.lado)
        m[0, 2] += LADO / 2.0 - float(est.centro[0])
        m[1, 2] += LADO / 2.0 - float(est.centro[1])
        rosto = cv2.warpAffine(frame_bgr, m, (LADO, LADO), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

        lab = cv2.cvtColor(rosto, cv2.COLOR_BGR2Lab)
        canais = list(cv2.split(lab))
        canais[0] = self._clahe.apply(canais[0])
        rosto = cv2.cvtColor(cv2.merge(canais), cv2.COLOR_Lab2BGR)
        borrado = cv2.GaussianBlur(rosto, (0, 0), 1.2)
        rosto = cv2.addWeighted(rosto, 1.5, borrado, -0.5, 0)
        est.imagem = cv2.cvtColor(rosto, cv2.COLOR_BGR2RGB)

    def ready(self, slot: int) -> bool:
        est = self._slots.get(slot)
        return est is not None and est.imagem is not None

    def face(self, slot: int, presenca: float) -> Optional[FaceCrop]:
        est = self._slots.get(slot)
        if est is None or est.imagem is None:
            return None
        return FaceCrop(slot, presenca, est.imagem, est.de_frente)
