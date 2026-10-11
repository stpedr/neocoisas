"""Ajustes de imagem (brilho, contraste, saturação, gama, temperatura) e espelhamento."""

import numpy as np
import pytest

from projmap.core.project import ColorAdjust, Project
from projmap.mapping.color import adjust

W, H = 200, 120
QUAD = [[20.0, 10.0], [150.0, 20.0], [160.0, 100.0], [30.0, 110.0]]  # assimétrico: espelhar muda


def test_neutro_nao_muda_nada():
    rgb = np.random.RandomState(0).rand(10, 3).astype(np.float32)
    assert np.allclose(adjust(rgb), rgb, atol=1e-6)
    assert ColorAdjust().is_neutral()


def test_formulas():
    c = np.array([0.2, 0.5, 0.8], np.float32)
    assert np.allclose(adjust(c, brightness=2.0), [0.4, 1.0, 1.0])  # ganho com corte no branco
    assert np.allclose(adjust(c, contrast=0.0), [0.5, 0.5, 0.5])  # contraste 0 = cinza médio
    gray = adjust(c, saturation=0.0)
    assert np.allclose(gray, gray[0])  # saturação 0 = cinza
    assert adjust(c, gamma=2.0)[0] > c[0]  # gama > 1 clareia os escuros
    assert np.allclose(adjust(np.ones(3), gamma=2.0), 1.0)  # ...sem mexer no branco
    warm = adjust(c, temperature=1.0)
    assert warm[0] > c[0] and warm[2] < c[2]


@pytest.mark.parametrize("field, value", [("brightness", 0.6), ("contrast", 1.6), ("saturation", 0.3),
                                           ("gamma", 1.8), ("temperature", -0.8)])
def test_rejeita_fora_da_faixa(field, value):
    ColorAdjust(**{field: value})  # dentro: ok
    with pytest.raises(ValueError):
        ColorAdjust(**{field: 99})


# ---------------------------------------------------------------- GPU
def _project(color_out=None, color_surf=None, **out):
    surf = {"id": "s1", "node_id": "p1", "warp": {"base": QUAD}, "source": {"kind": "color", "color": [200, 90, 40]}}
    if color_surf:
        surf["color"] = color_surf
    output = {"width": W, "height": H, **out}
    if color_out:
        output["color"] = color_out
    return Project.model_validate({"nodes": [{"id": "p1", "output": output}], "surfaces": [surf]})


def _render(gl_ctx, project):
    from projmap.node.renderer import render_offscreen

    return render_offscreen(project, "p1", lambda s: None, lambda r: None, ctx=gl_ctx).astype(int)


def _center(img):
    cy, cx = np.array(QUAD).mean(axis=0)[::-1].astype(int)
    return img[cy, cx]


def test_gpu_igual_a_cpu_projetor_e_superficie(gl_ctx):
    base = np.array([200, 90, 40]) / 255
    out_c = {"brightness": 1.3, "contrast": 1.2, "saturation": 1.4, "gamma": 0.9, "temperature": 0.4}
    surf_c = {"brightness": 0.8, "contrast": 0.9, "saturation": 0.7, "gamma": 1.3, "temperature": -0.5}
    gpu = _center(_render(gl_ctx, _project(out_c, surf_c)))
    cpu = adjust(adjust(base, **surf_c), **out_c) * 255
    assert np.abs(gpu - cpu).max() <= 2, (gpu, cpu)


def _same(a, b):
    """Iguais a menos de pixels exatamente sobre as arestas (a regra de
    rasterização da GPU decide esses pixels de forma diferente quando espelha)."""
    return (np.abs(a - b).max(axis=-1) > 0).mean() < 0.005


def test_espelhar_horizontal_e_vertical(gl_ctx):
    normal = _render(gl_ctx, _project())
    assert _same(_render(gl_ctx, _project(flip_h=True)), normal[:, ::-1])
    assert _same(_render(gl_ctx, _project(flip_v=True)), normal[::-1, :])
    assert _same(_render(gl_ctx, _project(flip_h=True, flip_v=True)), normal[::-1, ::-1])
    assert not _same(_render(gl_ctx, _project(flip_h=True)), normal)  # e de fato mudou


def test_padrao_de_alinhamento_ignora_ajuste_de_cor(gl_ctx):
    img = _render(gl_ctx, _project({"brightness": 0.3, "temperature": 1.0}, pattern="white"))
    assert img.min() == 255  # branco puro, mesmo com o projetor "escurecido"
