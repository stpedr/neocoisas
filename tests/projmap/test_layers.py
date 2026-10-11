"""F9: várias mídias por superfície (camadas) — esquema, matemática e render."""

import numpy as np
import pytest

from projmap.core.project import Layer, Project, parse_project
from projmap.mapping.warp import UvTransform, compose, layer_uvx

SHA = "a" * 64
QUAD = [[0.0, 0.0], [400.0, 0.0], [400.0, 200.0], [0.0, 200.0]]  # proporção 2:1


def _project_dict(layers):
    return {
        "nodes": [{"id": "p1"}],
        "media": {SHA: {"sha256": SHA, "filename": "x.png", "ext": ".png", "kind": "image"}},
        "surfaces": [{"id": "s1", "node_id": "p1", "warp": {"base": QUAD}, "layers": layers}],
    }


# ---------------------------------------------------------------- esquema
def test_projeto_antigo_sem_camadas_continua_valido():
    p = parse_project({"nodes": [{"id": "p1"}], "surfaces": [{"id": "s1", "node_id": "p1", "warp": {"base": QUAD}}]})
    assert p.surfaces[0].layers == []


def test_camada_valida():
    p = parse_project(_project_dict([{"id": "l1", "source": {"kind": "image", "media": SHA}, "rect": [0.1, 0.2, 0.5, 0.5]}]))
    assert p.surfaces[0].layers[0].rect == (0.1, 0.2, 0.5, 0.5)


@pytest.mark.parametrize("layers, msg", [
    ([{"id": "l1", "source": {"kind": "image", "media": "b" * 64}}], "mídia desconhecida"),
    ([{"id": "l1", "source": {"kind": "video", "media": SHA}}], "não combina"),
    ([{"id": "l1", "source": {"kind": "test"}}, {"id": "l1", "source": {"kind": "test"}}], "duplicados"),
    ([{"id": "l1", "source": {"kind": "test"}, "rect": [0, 0, 0, 1]}], "positivas"),
])
def test_camada_invalida(layers, msg):
    with pytest.raises(ValueError, match=msg):
        parse_project(_project_dict(layers))


# ---------------------------------------------------------------- matemática
def _apply(t: UvTransform, uv):
    return (uv[0] * t.scale[0] + t.offset[0], uv[1] * t.scale[1] + t.offset[1])


def test_compose():
    a = UvTransform((2.0, 3.0), (0.5, -1.0))
    b = UvTransform((0.5, 0.25), (0.1, 0.2))
    uv = (0.3, 0.7)
    assert np.allclose(_apply(compose(a, b), uv), _apply(b, _apply(a, uv)))


def test_layer_stretch_mapeia_o_retangulo_para_a_textura_inteira():
    t = layer_uvx((0.25, 0.5, 0.5, 0.25), "stretch", (100, 100), QUAD)
    assert np.allclose(_apply(t, (0.25, 0.5)), (0, 0))
    assert np.allclose(_apply(t, (0.75, 0.75)), (1, 1))
    tu, tv = _apply(t, (0.1, 0.1))  # fora do retângulo → fora de [0,1] (o shader descarta)
    assert tu < 0 or tv < 0


def test_layer_contain_respeita_a_proporcao_do_retangulo():
    # Retângulo = metade esquerda da superfície 2:1 → região quadrada; mídia 2:1 em "caber"
    # ocupa a largura toda e metade da altura, centralizada.
    t = layer_uvx((0.0, 0.0, 0.5, 1.0), "contain", (200, 100), QUAD)
    assert np.allclose(_apply(t, (0.0, 0.25)), (0, 0))
    assert np.allclose(_apply(t, (0.5, 0.75)), (1, 1))


# ---------------------------------------------------------------- render (GPU vs. CPU)
def test_render_camada_sobre_o_fundo_bate_com_cpu(gl_ctx, tmp_path, checker):
    cv2 = pytest.importorskip("cv2")
    from projmap.mapping.warp import render_surface_cpu
    from projmap.node.renderer import render_offscreen

    w, h = 400, 200
    path = tmp_path / "checker.png"
    cv2.imwrite(str(path), cv2.cvtColor(checker, cv2.COLOR_RGBA2BGRA))
    rect = (0.5, 0.25, 0.4, 0.5)
    project = Project.model_validate({
        "nodes": [{"id": "p1", "output": {"width": w, "height": h}}],
        "media": {SHA: {"sha256": SHA, "filename": "c.png", "ext": ".png", "kind": "image"}},
        "surfaces": [{
            "id": "s1", "node_id": "p1", "warp": {"base": QUAD},
            "source": {"kind": "color", "color": [0, 0, 255]},
            "layers": [Layer(id="l1", source={"kind": "image", "media": SHA}, rect=rect).model_dump()],
        }],
    })
    gpu = render_offscreen(project, "p1", lambda _s: path, lambda r: None, ctx=gl_ctx).astype(int)

    blue = np.zeros((4, 4, 4), np.uint8)
    blue[...] = (0, 0, 255, 255)
    base = render_surface_cpu((w, h), QUAD, blue)
    top = render_surface_cpu((w, h), QUAD, checker, uvx=layer_uvx(rect, "stretch", (64, 64), QUAD))
    ref = top[..., :3] + base[..., :3] * (1 - top[..., 3:4])  # "over" pré-multiplicado
    ref = (np.clip(ref, 0, 1) * 255).round().astype(int)

    agree = (np.abs(gpu - ref).max(axis=-1) <= 12).mean()
    assert agree > 0.99
    # fora do retângulo, só o fundo azul
    assert tuple(gpu[20, 20]) == (0, 0, 255)


def test_camada_invisivel_nao_desenha(gl_ctx, tmp_path):
    from projmap.node.renderer import render_offscreen

    project = Project.model_validate({
        "nodes": [{"id": "p1", "output": {"width": 400, "height": 200}}],
        "surfaces": [{
            "id": "s1", "node_id": "p1", "warp": {"base": QUAD}, "source": {"kind": "none"},
            "layers": [{"id": "l1", "visible": False, "source": {"kind": "color", "color": [255, 0, 0]}}],
        }],
    })
    assert render_offscreen(project, "p1", lambda s: None, lambda r: None, ctx=gl_ctx).max() == 0
