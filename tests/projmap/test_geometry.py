"""Homografia e validação de quads (aceite da F1)."""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from projmap.core.geometry import (  # noqa: E402
    UNIT_SQUARE,
    apply_homography,
    homography_from_points,
    order_quad,
    polygon_area,
    quad_to_unit_square,
    unit_square_to_quad,
    validate_quad,
)


def _cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


PERSPECTIVE_QUAD = [[312.0, 140.0], [1405.0, 210.0], [1520.0, 1010.0], [205.0, 930.0]]


def test_round_trip_de_pontos_abaixo_de_1e6_px():
    h = unit_square_to_quad(PERSPECTIVE_QUAD)
    rng = np.random.default_rng(42)
    uv = rng.random((500, 2))
    px = apply_homography(h, uv)
    back = apply_homography(np.linalg.inv(h), px)
    assert np.max(np.abs(back - uv)) * 1920 < 1e-6


def test_cantos_do_quadrado_unitario_vao_para_os_cantos_do_quad():
    h = unit_square_to_quad(PERSPECTIVE_QUAD)
    assert np.allclose(apply_homography(h, UNIT_SQUARE), PERSPECTIVE_QUAD, atol=1e-9)


def test_igual_ao_opencv_com_4_pontos():
    src = np.array([[10, 20], [900, 35], [870, 700], [40, 650]], dtype=np.float64)
    ours = homography_from_points(src, PERSPECTIVE_QUAD)
    ref = cv2.getPerspectiveTransform(src.astype(np.float32), np.float32(PERSPECTIVE_QUAD))
    assert np.allclose(ours, ref / ref[2, 2], atol=1e-6)


def test_minimos_quadrados_com_ruido_igual_ao_findhomography():
    rng = np.random.default_rng(7)
    h_true = unit_square_to_quad(PERSPECTIVE_QUAD)
    src = rng.random((60, 2))
    dst = apply_homography(h_true, src) + rng.normal(0, 0.3, (60, 2))
    ours = homography_from_points(src, dst)
    ref, _ = cv2.findHomography(src, dst, 0)
    probe = rng.random((20, 2))
    assert np.max(np.abs(apply_homography(ours, probe) - apply_homography(ref, probe))) < 0.05


def test_coordenadas_grandes_4k_sem_perda_de_precisao():
    quad = np.array(PERSPECTIVE_QUAD) * 4 + 5000
    h = unit_square_to_quad(quad)
    assert np.allclose(apply_homography(h, UNIT_SQUARE), quad, atol=1e-6)


def test_inversa_leva_pixel_a_uv():
    hinv = quad_to_unit_square(PERSPECTIVE_QUAD)
    assert np.allclose(apply_homography(hinv, PERSPECTIVE_QUAD), UNIT_SQUARE, atol=1e-9)


def test_perspectiva_nao_e_afim_a_dobra_diagonal():
    """O centro do quad em perspectiva NÃO é uv (0.5, 0.5) — é o que a interpolação
    afim dos 2 triângulos assumiria. A homografia acerta o ponto onde as diagonais
    se cruzam (centro projetivo)."""
    q = np.array(PERSPECTIVE_QUAD)
    h = unit_square_to_quad(q)
    center_projective = apply_homography(h, [[0.5, 0.5]])[0]
    # Interseção das diagonais TL-BR e TR-BL.
    p, r = q[0], q[2] - q[0]
    s_, t_ = q[1], q[3] - q[1]
    k = _cross2(s_ - p, t_) / _cross2(r, t_)
    diag = p + k * r
    assert np.allclose(center_projective, diag, atol=1e-6)
    centroid = q.mean(axis=0)
    assert np.linalg.norm(centroid - diag) > 5  # o atalho afim erraria por vários px


@pytest.mark.parametrize(
    "quad, trecho",
    [
        ([[0, 0], [10, 0], [10, 10]], "4 cantos"),
        ([[0, 0], [5, 0], [10, 0], [0, 10]], "colineares"),
        ([[0, 0], [30, 12], [30, 0], [0, 8]], "cruzado"),  # laço em X
        ([[0, 0], [10, 0], [3, 3], [0, 10]], "côncavo"),
        ([[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1]], "degenerado"),
        ([[0, 0], [float("nan"), 0], [10, 10], [0, 10]], "NaN"),
    ],
)
def test_validate_quad_recusa_casos_invalidos(quad, trecho):
    err = validate_quad(quad)
    assert err is not None and trecho.split()[0].lower() in err.lower()


def test_validate_quad_aceita_perspectiva_e_sentido_anti_horario():
    assert validate_quad(PERSPECTIVE_QUAD) is None
    assert validate_quad(PERSPECTIVE_QUAD[::-1]) is None  # espelhado é válido (flip intencional)


def test_homografia_recusa_pontos_colineares():
    with pytest.raises(ValueError):
        homography_from_points([[0, 0], [1, 1], [2, 2], [3, 3]], PERSPECTIVE_QUAD)


def test_order_quad_e_area():
    shuffled = [PERSPECTIVE_QUAD[i] for i in (2, 0, 3, 1)]
    assert np.allclose(order_quad(shuffled), PERSPECTIVE_QUAD)
    assert polygon_area(PERSPECTIVE_QUAD) > 0
