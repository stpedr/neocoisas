"""Padrões de teste e de alinhamento, gerados localmente (sem IA, sem rede).

- ``grid``: grade com numeração, cruz central e círculo, para checar foco,
  keystone e geometria na parede.
- ``edges``: as bordas da foto tirada da posição do projetor, levadas ao espaço
  do projetor pela homografia foto→projetor. Projetadas, elas caem sobre as
  quinas reais da parede quando a calibração está certa. É a "Alignment Image"
  do fluxo do ifnull, mas por Canny local em vez de gerada por IA
  (BLUEPRINT §3, E7).
"""

from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

from ..core.geometry import homography_from_points, rect_quad


def grid_pattern(width: int, height: int, cells: int = 16) -> np.ndarray:
    img = np.zeros((height, width, 4), dtype=np.uint8)
    img[..., 3] = 255
    step = max(8, min(width, height) // max(cells // 2, 1))
    color = (255, 255, 255, 255)
    for x in range(0, width, step):
        cv2.line(img, (x, 0), (x, height - 1), color, 1)
    for y in range(0, height, step):
        cv2.line(img, (0, y), (width - 1, y), color, 1)
    cv2.rectangle(img, (0, 0), (width - 1, height - 1), (255, 64, 64, 255), 3)
    cx, cy = width // 2, height // 2
    cv2.line(img, (cx, 0), (cx, height - 1), (64, 255, 64, 255), 2)
    cv2.line(img, (0, cy), (width - 1, cy), (64, 255, 64, 255), 2)
    cv2.circle(img, (cx, cy), min(width, height) // 3, (64, 160, 255, 255), 2)
    scale = max(0.4, min(width, height) / 1400)
    for i, x in enumerate(range(0, width, step)):
        for j, y in enumerate(range(0, height, step)):
            if (i + j) % 2 == 0:
                cv2.putText(img, f"{i},{j}", (x + 4, y + int(18 * scale) + 2), cv2.FONT_HERSHEY_SIMPLEX,
                            scale * 0.6, (200, 200, 200, 255), 1, cv2.LINE_AA)
    return img


def solid(width: int, height: int, rgb: Sequence[int] = (255, 255, 255)) -> np.ndarray:
    img = np.empty((height, width, 4), dtype=np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = rgb[0], rgb[1], rgb[2]
    img[..., 3] = 255
    return img


def photo_to_projector(photo_size: tuple[int, int], boundary_norm: Sequence[Sequence[float]],
                       out_size: tuple[int, int]) -> np.ndarray:
    """Homografia pixel da foto → pixel do projetor.

    ``boundary_norm`` é onde o quadro inteiro do projetor aparece na foto
    (TL, TR, BR, BL, normalizado). Ele é levado aos cantos da saída.
    """
    pw, ph = photo_size
    ow, oh = out_size
    src = [[x * pw, y * ph] for x, y in boundary_norm]
    return homography_from_points(src, rect_quad(0, 0, ow, oh))


def edges_pattern(photo_bgr: np.ndarray, boundary_norm: Sequence[Sequence[float]],
                  out_size: tuple[int, int], thickness: int = 2) -> np.ndarray:
    """Bordas da foto no espaço do projetor (RGBA: bordas brancas sobre preto)."""
    gray = cv2.cvtColor(photo_bgr, cv2.COLOR_BGR2GRAY) if photo_bgr.ndim == 3 else photo_bgr
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    # Limiares automáticos pela mediana: funciona em foto escura e clara sem ajuste.
    med = float(np.median(gray))
    edges = cv2.Canny(gray, int(max(0, 0.66 * med)), int(min(255, 1.33 * med) or 50))
    if thickness > 1:
        edges = cv2.dilate(edges, np.ones((thickness, thickness), np.uint8))
    h = photo_to_projector((gray.shape[1], gray.shape[0]), boundary_norm, out_size)
    warped = cv2.warpPerspective(edges, h, out_size, flags=cv2.INTER_LINEAR)
    rgba = np.zeros((out_size[1], out_size[0], 4), dtype=np.uint8)
    rgba[..., :3] = warped[..., None]
    rgba[..., 3] = 255
    return rgba


def make_test_card(width: int = 1024, height: int = 576) -> np.ndarray:
    """Cartela de teste para a fonte ``test`` de uma superfície (cores + grade + seta 'cima')."""
    img = grid_pattern(width, height, cells=12)
    bars = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0), (255, 0, 255), (255, 0, 0), (0, 0, 255)]
    bw = width // len(bars)
    for i, c in enumerate(bars):
        img[height // 3: height // 3 + height // 6, i * bw:(i + 1) * bw, :3] = c
    pts = np.array([[width // 2, height // 12], [width // 2 - width // 20, height // 5],
                    [width // 2 + width // 20, height // 5]], np.int32)
    cv2.fillPoly(img, [pts], (255, 255, 255, 255))
    cv2.putText(img, "TOPO", (width // 2 - 40, height // 5 + 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                (255, 255, 255, 255), 2, cv2.LINE_AA)
    return img
