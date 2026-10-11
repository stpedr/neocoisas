"""Fontes de conteúdo: GIF respeita atrasos, vídeo segue o relógio e faz loop."""

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("cv2")  # deps do ProjMap: requirements-projmap-master.txt

from projmap.content.base import loop_time  # noqa: E402
from projmap.content.factory import get_source  # noqa: E402
from projmap.content.gif import GifSource  # noqa: E402
from projmap.core.project import SourceSpec  # noqa: E402
from projmap.mapping.warp import fit_transform  # noqa: E402

QUAD_16x9 = [[0, 0], [160, 0], [160, 90], [0, 90]]


def _colors(n):
    return [((i * 53) % 256, (i * 97) % 256, (i * 151) % 256) for i in range(n)]


def test_gif_respeita_atraso_de_cada_frame(tmp_path):
    path = tmp_path / "anim.gif"
    frames = [Image.new("RGB", (8, 8), c) for c in _colors(3)]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[100, 300, 50], loop=0)
    gif = GifSource(path)
    assert gif.frame_count == 3
    assert gif.duration == pytest.approx(0.45)
    # Fronteiras: [0,0.1) → 0, [0.1,0.4) → 1, [0.4,0.45) → 2, depois loop.
    for t, idx in [(0.0, 0), (0.099, 0), (0.1, 1), (0.39, 1), (0.41, 2), (0.46, 0), (1.05, 1)]:
        assert gif.index_at(t) == idx, t
    key, img = gif.frame_at(0.2)
    assert key == 1 and img.shape == (8, 8, 4)


def test_gif_atraso_zero_vira_100ms_como_no_navegador(tmp_path):
    path = tmp_path / "zero.gif"
    frames = [Image.new("RGB", (4, 4), c) for c in _colors(2)]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=0, loop=0)
    assert GifSource(path).delays == [0.1, 0.1]


def test_loop_time_sem_loop_para_no_fim():
    assert loop_time(5.5, 2.0, loop=True) == pytest.approx(1.5)
    assert loop_time(5.5, 2.0, loop=False) < 2.0
    assert loop_time(-1, 2.0, loop=False) == 0.0


def _make_video(path, n=12, fps=10, size=(64, 48)):
    av = pytest.importorskip("av")
    colors = _colors(n)
    with av.open(str(path), "w") as out:
        try:
            stream = out.add_stream("libx264", rate=fps)
            stream.options = {"preset": "ultrafast", "crf": "1"}
        except Exception:  # noqa: BLE001 — FFmpeg sem x264: usa mpeg4
            stream = out.add_stream("mpeg4", rate=fps)
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        for c in colors:
            img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
            img[:] = c
            for packet in stream.encode(av.VideoFrame.from_ndarray(img, format="rgb24")):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return colors


def _closest(colors, rgba):
    px = rgba[rgba.shape[0] // 2, rgba.shape[1] // 2, :3].astype(int)
    return int(np.argmin([np.abs(px - np.array(c)).sum() for c in colors]))


def test_video_segue_o_relogio_e_faz_loop(tmp_path):
    from projmap.content.video import VideoSource

    path = tmp_path / "cores.mp4"
    colors = _make_video(path)
    src = VideoSource(path, loop=True)
    try:
        assert src.size == (64, 48)
        assert src.duration == pytest.approx(1.2, abs=0.11)
        for t, idx in [(0.0, 0), (0.25, 2), (0.55, 5), (1.15, 11), (1.25, 0), (1.55, 3), (0.35, 3)]:
            _, img = src.frame_at(t, block_timeout=3.0)
            assert _closest(colors, img) == idx, t
        assert img.shape == (48, 64, 4) and img[..., 3].min() == 255
    finally:
        src.close()


def test_video_sem_loop_congela_no_ultimo_frame(tmp_path):
    from projmap.content.video import VideoSource

    path = tmp_path / "curto.mp4"
    colors = _make_video(path, n=5)
    src = VideoSource(path, loop=False)
    try:
        _, img = src.frame_at(10.0, block_timeout=3.0)
        assert _closest(colors, img) == 4
    finally:
        src.close()


def test_factory_escolhe_por_kind_e_aplica_velocidade(tmp_path):
    path = tmp_path / "a.gif"
    frames = [Image.new("RGB", (4, 4), c) for c in _colors(4)]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
    spec = SourceSpec(kind="gif", media="b" * 64, speed=2.0)
    src = get_source(spec, lambda sha: path)
    assert src.frame_at(0.15)[0] == 3  # 0.15 s × 2 = 0.3 s → frame 3 (fronteira exata)
    assert get_source(SourceSpec(kind="none")) is None
    assert get_source(SourceSpec(kind="color", color=(1, 2, 3))).frame_at(0)[1][0, 0, :3].tolist() == [1, 2, 3]
    assert get_source(SourceSpec(kind="test")).size == (1024, 576)
    with pytest.raises(ValueError):
        get_source(SourceSpec.model_construct(kind="video", media=None, speed=1.0, offset_s=0.0))


def test_fit_cover_e_contain():
    wide = fit_transform("cover", (320, 90), QUAD_16x9)  # fonte 32:9 num quad 16:9
    assert wide.scale == pytest.approx((0.5, 1.0)) and wide.offset == pytest.approx((0.25, 0.0))
    tall = fit_transform("contain", (320, 90), QUAD_16x9)
    assert tall.scale == pytest.approx((1.0, 2.0)) and tall.offset == pytest.approx((0.0, -0.5))
    assert fit_transform("stretch", (1, 1), QUAD_16x9).scale == (1.0, 1.0)
