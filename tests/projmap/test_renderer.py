"""Renderer GLSL vs. referência em CPU (NumPy) — prova o mapeamento sem "dobra"."""

import numpy as np
import pytest

pytest.importorskip("moderngl")
cv2 = pytest.importorskip("cv2")

from projmap.core.project import Node, Project, Surface  # noqa: E402
from projmap.mapping.warp import fit_transform, render_surface_cpu  # noqa: E402
from projmap.node.renderer import render_offscreen  # noqa: E402

W, H = 320, 180
QUAD = [[40.0, 20.0], [262.0, 44.0], [281.0, 165.0], [28.0, 151.0]]


def _project(tmp_path, checker, **surface_kw):
    path = tmp_path / "checker.png"
    cv2.imwrite(str(path), cv2.cvtColor(checker, cv2.COLOR_RGBA2BGRA))
    sha = "a" * 64
    surf = {"id": "s1", "node_id": "p1", "warp": {"base": QUAD},
            "source": {"kind": "image", "media": sha}}
    surf.update(surface_kw)
    project = Project(
        nodes=[Node(id="p1", output={"width": W, "height": H})],
        surfaces=[Surface.model_validate(surf)],
        media={sha: {"sha256": sha, "filename": "checker.png", "ext": ".png", "kind": "image"}},
    )
    return project, (lambda _sha: path)


def _cpu(checker, **kw):
    ref = render_surface_cpu((W, H), QUAD, checker, **kw)
    return (np.clip(ref[..., :3], 0, 1) * 255).round().astype(np.uint8)


def _agreement(gpu, cpu, tol=12):
    """Fração de pixels onde GPU e referência CPU (ambas bilineares) concordam.

    Sobra só arredondamento de float32 vs float64 nas bordas do quad.
    """
    diff = np.abs(gpu.astype(int) - cpu.astype(int)).max(axis=-1)
    return float((diff <= tol).mean())


def test_gpu_igual_a_referencia_cpu_em_quad_em_perspectiva(gl_ctx, tmp_path, checker):
    project, media = _project(tmp_path, checker)
    gpu = render_offscreen(project, "p1", media, lambda r: None, ctx=gl_ctx)
    assert gpu.shape == (H, W, 3)
    assert _agreement(gpu, _cpu(checker)) > 0.99


def test_cantos_coloridos_caem_nos_cantos_certos(gl_ctx, tmp_path, checker):
    """Orientação: TL vermelho, TR verde, BR azul, BL amarelo (v cresce para baixo)."""
    project, media = _project(tmp_path, checker)
    img = render_offscreen(project, "p1", media, lambda r: None, ctx=gl_ctx).astype(int)
    q = np.array(QUAD)
    center = q.mean(axis=0)
    expected = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    for corner, color in zip(q, expected):
        x, y = (corner + (center - corner) * 0.03).round().astype(int)
        assert np.abs(img[y, x] - np.array(color)).max() < 60, (corner, img[y, x])


def test_fora_do_quad_fica_preto(gl_ctx, tmp_path, checker):
    project, media = _project(tmp_path, checker)
    img = render_offscreen(project, "p1", media, lambda r: None, ctx=gl_ctx)
    assert img[2, 2].max() == 0 and img[H - 2, W - 2].max() == 0


def test_contain_cover_e_feather_batem_com_cpu(gl_ctx, tmp_path, checker):
    wide = np.ascontiguousarray(np.concatenate([checker, checker], axis=1))  # 128×64
    for fit in ("contain", "cover"):
        project, media = _project(tmp_path, wide, source={"kind": "image", "media": "a" * 64, "fit": fit},
                                  feather=0.08)
        gpu = render_offscreen(project, "p1", media, lambda r: None, ctx=gl_ctx)
        uvx = fit_transform(fit, (128, 64), QUAD)
        assert _agreement(gpu, _cpu(wide, uvx=uvx, feather=0.08)) > 0.99, fit


def test_blackout_e_padrao_branco(gl_ctx, tmp_path, checker):
    project, media = _project(tmp_path, checker)
    project.nodes[0].output.blackout = True
    assert render_offscreen(project, "p1", media, lambda r: None, ctx=gl_ctx).max() == 0
    project.nodes[0].output.blackout = False
    project.nodes[0].output.pattern = "white"
    project.nodes[0].output.intensity = 0.5
    img = render_offscreen(project, "p1", media, lambda r: None, ctx=gl_ctx)
    assert abs(int(img.mean()) - 128) <= 2  # dimmer master aplicado ao padrão


def test_janela_de_preview_menor_mantem_o_mapeamento(gl_ctx, tmp_path, checker):
    """Framebuffer menor que o espaço do projeto (preview): mesma imagem, escalada."""
    project, media = _project(tmp_path, checker)
    full = render_offscreen(project, "p1", media, lambda r: None, ctx=gl_ctx)
    half = render_offscreen(project, "p1", media, lambda r: None, ctx=gl_ctx, size=(W // 2, H // 2))
    down = cv2.resize(full, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    assert np.abs(half.astype(int) - down.astype(int)).mean() < 25


def test_midia_quebrada_vira_magenta_sem_derrubar(gl_ctx, tmp_path, checker):
    project, _ = _project(tmp_path, checker)
    missing = tmp_path / "nao-existe.png"
    img = render_offscreen(project, "p1", lambda _s: missing, lambda r: None, ctx=gl_ctx)
    cy, cx = np.array(QUAD).mean(axis=0)[::-1].astype(int)
    assert tuple(img[cy, cx]) == (255, 0, 255)
