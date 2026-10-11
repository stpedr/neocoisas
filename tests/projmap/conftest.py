import numpy as np
import pytest


@pytest.fixture(scope="session")
def gl_ctx():
    """Contexto OpenGL headless; os testes de GPU são pulados sem um.

    No CI roda sob ``xvfb-run`` (Mesa llvmpipe). Localmente, qualquer GPU serve.
    """
    moderngl = pytest.importorskip("moderngl")
    ctx = None
    for kwargs in ({}, {"backend": "egl"}):
        try:
            ctx = moderngl.create_standalone_context(**kwargs)
            break
        except Exception:  # noqa: BLE001
            continue
    if ctx is None:
        pytest.skip("sem contexto OpenGL (rode com xvfb-run ou numa máquina com GPU)")
    yield ctx
    ctx.release()


@pytest.fixture
def checker():
    """Textura xadrez 64×64 (8 casas) em RGBA, com cantos coloridos p/ orientação."""
    img = np.zeros((64, 64, 4), dtype=np.uint8)
    yy, xx = np.mgrid[0:64, 0:64]
    on = ((xx // 8) + (yy // 8)) % 2 == 0
    img[on] = (230, 230, 230, 255)
    img[~on] = (30, 30, 30, 255)
    img[:8, :8] = (255, 0, 0, 255)  # TL vermelho
    img[:8, -8:] = (0, 255, 0, 255)  # TR verde
    img[-8:, -8:] = (0, 0, 255, 255)  # BR azul
    img[-8:, :8] = (255, 255, 0, 255)  # BL amarelo
    return img
