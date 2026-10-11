"""Geometria projetiva do mapeamento.

Convenções (valem para o projeto inteiro):

- Pontos são ``(x, y)`` em pixels, origem no canto superior esquerdo, y para baixo
  (mesma convenção de imagens/OpenCV). Para o projetor, o espaço é o da saída
  (ex.: 1920×1080).
- Um *quad* de superfície tem os cantos na ordem **TL, TR, BR, BL** e corresponde
  ao quadrado unitário de textura ``(0,0) (1,0) (1,1) (0,1)`` — ``v`` cresce para
  baixo, como as linhas de uma imagem.
- Homografias são matrizes 3×3 ``H`` que levam ``[x, y, 1]`` de origem para destino
  (coordenadas homogêneas), normalizadas com ``H[2,2] = 1`` quando possível.

Decisão de engenharia (BLUEPRINT E1): a base de todo warp é a homografia exata dos
4 cantos. Um interpolador genérico (spline/malha) pelos 4 cantos entorta retas numa
parede em perspectiva; correções locais (grade/Bézier) entram *por cima* da base.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

import numpy as np

UNIT_SQUARE = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])


def as_points(pts: Iterable[Sequence[float]]) -> np.ndarray:
    """Converte para array ``(N, 2)`` float64, validando a forma."""
    arr = np.asarray(pts, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"esperado array (N, 2) de pontos, recebido {arr.shape}")
    return arr


def _normalization(pts: np.ndarray) -> np.ndarray:
    """Matriz de normalização de Hartley: centróide na origem, distância média √2.

    Sem isso a DLT fica mal condicionada com coordenadas em pixels (valores ~1e3
    misturados com 1 na mesma matriz) — o erro cresce visivelmente em 4K.
    """
    centroid = pts.mean(axis=0)
    dist = np.sqrt(((pts - centroid) ** 2).sum(axis=1)).mean()
    if dist < 1e-12:
        raise ValueError("pontos degenerados (todos coincidentes)")
    s = np.sqrt(2.0) / dist
    return np.array(
        [[s, 0.0, -s * centroid[0]], [0.0, s, -s * centroid[1]], [0.0, 0.0, 1.0]]
    )


def homography_from_points(src: Iterable, dst: Iterable) -> np.ndarray:
    """Homografia ``src → dst`` por DLT normalizada (mínimos quadrados, N ≥ 4).

    Com 4 pontos a solução é exata. Com mais, é a de menor erro algébrico — para
    robustez a outliers (calibração), usar RANSAC por cima (F4).
    """
    src = as_points(src)
    dst = as_points(dst)
    if src.shape != dst.shape:
        raise ValueError("src e dst precisam ter o mesmo número de pontos")
    if len(src) < 4:
        raise ValueError("são necessários pelo menos 4 pares de pontos")

    t_src = _normalization(src)
    t_dst = _normalization(dst)
    s = apply_homography(t_src, src)
    d = apply_homography(t_dst, dst)

    rows = []
    for (x, y), (u, v) in zip(s, d):
        rows.append([-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u])
        rows.append([0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v])
    a = np.asarray(rows)
    _, sv, vt = np.linalg.svd(a)
    # Posto < 8 ⇒ configuração degenerada (ex.: 3 pontos colineares entre 4).
    if sv[7] < 1e-10 * max(sv[0], 1.0):
        raise ValueError("configuração degenerada: pontos colineares ou repetidos")
    h_norm = vt[-1].reshape(3, 3)

    h = np.linalg.inv(t_dst) @ h_norm @ t_src
    if abs(h[2, 2]) > 1e-12:
        h = h / h[2, 2]
    return h


def apply_homography(h: np.ndarray, pts: Iterable) -> np.ndarray:
    """Aplica ``H`` a pontos ``(N, 2)``, devolvendo ``(N, 2)``."""
    p = as_points(pts)
    homog = np.hstack([p, np.ones((len(p), 1))]) @ np.asarray(h, dtype=np.float64).T
    w = homog[:, 2:3]
    if np.any(np.abs(w) < 1e-15):
        raise ValueError("ponto mapeado para o infinito (w = 0)")
    return homog[:, :2] / w


def unit_square_to_quad(quad: Iterable) -> np.ndarray:
    """Homografia do quadrado unitário de textura para o quad (TL, TR, BR, BL)."""
    q = as_points(quad)
    if len(q) != 4:
        raise ValueError("um quad tem exatamente 4 cantos")
    return homography_from_points(UNIT_SQUARE, q)


def quad_to_unit_square(quad: Iterable) -> np.ndarray:
    """Inversa de :func:`unit_square_to_quad` — pixel do projetor → uv da fonte.

    É exatamente o que o fragment shader avalia por pixel (``u_hinv``).
    """
    return np.linalg.inv(unit_square_to_quad(quad))


def _cross(o: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def polygon_area(pts: Iterable) -> float:
    """Área com sinal (shoelace). Positiva = sentido horário na tela (y para baixo)."""
    p = as_points(pts)
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def validate_quad(quad: Iterable, min_area: float = 1.0) -> Optional[str]:
    """Valida um quad de superfície; devolve a mensagem de erro ou ``None``.

    Exige 4 cantos finitos, área mínima, polígono **convexo** e sem
    auto-interseção (o "laço" em X que aparece ao arrastar um canto por cima de
    outro). Quads côncavos não admitem homografia que preserve a ordem dos cantos
    — o resultado espelharia a textura.
    """
    try:
        q = as_points(quad)
    except ValueError as exc:
        return str(exc)
    if len(q) != 4:
        return "um quad precisa de exatamente 4 cantos"
    if not np.all(np.isfinite(q)):
        return "coordenadas inválidas (NaN/inf)"
    if abs(polygon_area(q)) < min_area:
        return "quad degenerado (área ~0)"
    signs = [_cross(q[i], q[(i + 1) % 4], q[(i + 2) % 4]) for i in range(4)]
    if any(abs(s) < 1e-9 for s in signs):
        return "três cantos colineares"
    if not (all(s > 0 for s in signs) or all(s < 0 for s in signs)):
        return "quad côncavo ou cruzado — arraste os cantos de volta para a ordem TL, TR, BR, BL"
    return None


def order_quad(pts: Iterable) -> np.ndarray:
    """Ordena 4 pontos quaisquer como TL, TR, BR, BL (para detecções automáticas)."""
    p = as_points(pts)
    if len(p) != 4:
        raise ValueError("order_quad espera 4 pontos")
    c = p.mean(axis=0)
    ang = np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0])
    p = p[np.argsort(ang)]  # sentido horário na tela (y para baixo), começando em ~-180°
    tl = int(np.argmin(p.sum(axis=1)))
    return np.roll(p, -tl, axis=0)


def rect_quad(x: float, y: float, w: float, h: float) -> list[list[float]]:
    """Quad retangular TL, TR, BR, BL."""
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
