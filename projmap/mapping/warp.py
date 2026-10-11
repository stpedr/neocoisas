"""Warp de superfície: o que o shader recebe e a referência em CPU.

Como o shader mapeia (BLUEPRINT §5.3)
------------------------------------
Desenhar o quad como dois triângulos e interpolar ``uv`` por vértice dá a
"dobra" diagonal clássica: a interpolação de triângulo é **afim**, e a
perspectiva não é. Em vez de corrigir com coordenadas ``q`` por vértice, o
fragment shader avalia a homografia inversa **por pixel**::

    uv = H⁻¹ · (x, y, 1)      (projetor → textura)

Isso é exato para qualquer quad convexo, custa uma multiplicação 3×3 por pixel
e já é a forma que recebe correções de grade/Bézier e o LUT de calibração
(offset somado ao ``uv``) nas fases seguintes.

``render_surface_cpu`` reproduz o shader em NumPy. Serve de oráculo nos testes
(GPU vs. CPU) e de base para o modo *baked* (render offline por nó, F2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..core.geometry import as_points, quad_to_unit_square


@dataclass(frozen=True)
class UvTransform:
    """``tex = uv * scale + offset``; fora de [0,1] fica transparente (contain)."""

    scale: tuple[float, float] = (1.0, 1.0)
    offset: tuple[float, float] = (0.0, 0.0)


def quad_aspect(quad: Sequence[Sequence[float]]) -> float:
    """Proporção aparente do quad (média das arestas opostas).

    É uma estimativa — o aspecto "real" da superfície física exigiria a pose da
    câmera —, mas é o que um operador espera ao escolher cover/contain.
    """
    q = as_points(quad)
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    return float(w / h) if h > 1e-9 else 1.0


def fit_transform(fit: str, source_size: tuple[int, int], quad: Sequence[Sequence[float]]) -> UvTransform:
    sw, sh = source_size
    if fit == "stretch" or sw <= 0 or sh <= 0:
        return UvTransform()
    a_src = sw / sh
    a_dst = quad_aspect(quad)
    if fit == "cover":
        if a_src > a_dst:  # fonte mais larga: corta as laterais
            f = a_dst / a_src
            return UvTransform((f, 1.0), ((1 - f) / 2, 0.0))
        f = a_src / a_dst  # fonte mais alta: corta topo/base
        return UvTransform((1.0, f), (0.0, (1 - f) / 2))
    if fit == "contain":
        if a_src > a_dst:  # tarjas em cima/embaixo
            f = a_src / a_dst
            return UvTransform((1.0, f), (0.0, (1 - f) / 2))
        f = a_dst / a_src  # tarjas nas laterais
        return UvTransform((f, 1.0), ((1 - f) / 2, 0.0))
    raise ValueError(f"fit desconhecido: {fit}")


def hinv_for(quad: Sequence[Sequence[float]]) -> np.ndarray:
    """Matriz que o shader recebe como ``u_hinv`` (pixel do projetor → uv)."""
    return quad_to_unit_square(quad)


def _sample_bilinear(rgba: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Amostragem igual a ``GL_LINEAR`` + ``CLAMP_TO_EDGE`` (centros de texel em +0,5)."""
    th, tw = rgba.shape[:2]
    img = rgba.astype(np.float32) / 255.0
    x = np.clip(u * tw - 0.5, 0, tw - 1)
    y = np.clip(v * th - 0.5, 0, th - 1)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, tw - 1)
    y1 = np.minimum(y0 + 1, th - 1)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    top = img[y0, x0] * (1 - fx) + img[y0, x1] * fx
    bottom = img[y1, x0] * (1 - fx) + img[y1, x1] * fx
    return top * (1 - fy) + bottom * fy


def render_surface_cpu(
    out_size: tuple[int, int],
    quad: Sequence[Sequence[float]],
    rgba: np.ndarray,
    uvx: UvTransform = UvTransform(),
    feather: float = 0.0,
    opacity: float = 1.0,
) -> np.ndarray:
    """Renderiza uma superfície sobre preto, igual ao shader (bilinear, borda grudada).

    Devolve ``float32 (h, w, 4)`` com RGB já multiplicado pelo alfa final.
    """
    w, h = out_size
    hinv = hinv_for(quad)
    xs, ys = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    p = np.stack([xs, ys, np.ones_like(xs)], axis=-1) @ hinv.T
    with np.errstate(divide="ignore", invalid="ignore"):
        u = p[..., 0] / p[..., 2]
        v = p[..., 1] / p[..., 2]
    inside = (p[..., 2] > 0) & (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1)

    tu = u * uvx.scale[0] + uvx.offset[0]
    tv = v * uvx.scale[1] + uvx.offset[1]
    in_tex = (tu >= 0) & (tu <= 1) & (tv >= 0) & (tv <= 1)

    color = _sample_bilinear(rgba, np.nan_to_num(tu), np.nan_to_num(tv))

    alpha = color[..., 3] * opacity
    if feather > 0:
        edge = np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v))
        t = np.clip(np.nan_to_num(edge) / feather, 0, 1)
        alpha = alpha * (t * t * (3 - 2 * t))  # smoothstep, igual ao GLSL
    alpha = np.where(inside & in_tex, alpha, 0.0)

    out = np.zeros((h, w, 4), dtype=np.float32)
    out[..., :3] = color[..., :3] * alpha[..., None]
    out[..., 3] = alpha
    return out
