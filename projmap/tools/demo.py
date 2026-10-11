"""``python -m projmap.tools.demo`` — cria um projeto de exemplo para testar sem projetor.

Gera uma "foto" sintética de uma parede com caixas e uma coluna vista em
perspectiva, um vídeo de cores com contador de frames e um GIF, e monta 3
superfícies já mapeadas. Abra depois com::

    python -m projmap.master --project shows/demo.projmap --windowed --open
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..core.project import Surface
from ..core.store import ProjectStore

PHOTO_SIZE = (1600, 1000)
# Onde o quadro do projetor "aparece" na foto (normalizado), levemente trapezoidal.
BOUNDARY = [(0.08, 0.10), (0.93, 0.06), (0.95, 0.92), (0.06, 0.95)]


def make_photo() -> np.ndarray:
    w, h = PHOTO_SIZE
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (70, 78, 86)
    cv2.rectangle(img, (0, int(h * 0.78)), (w, h), (45, 50, 55), -1)  # piso
    # coluna
    cv2.fillPoly(img, [np.array([[1180, 120], [1290, 110], [1295, 790], [1185, 800]])], (150, 152, 156))
    # caixas
    cv2.fillPoly(img, [np.array([[260, 430], [640, 400], [655, 770], [250, 790]])], (120, 110, 98))
    cv2.fillPoly(img, [np.array([[700, 520], [960, 505], [968, 770], [705, 782]])], (132, 122, 108))
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 6, img.shape).astype(np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def make_video(path: Path, seconds: float = 4.0, fps: int = 30, size=(640, 360)) -> None:
    import av

    with av.open(str(path), "w") as out:
        try:
            stream = out.add_stream("libx264", rate=fps)
            stream.options = {"preset": "veryfast", "crf": "23"}
        except Exception:  # noqa: BLE001
            stream = out.add_stream("mpeg4", rate=fps)
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        n = int(seconds * fps)
        for i in range(n):
            hue = int(180 * i / n)
            hsv = np.full((size[1], size[0], 3), (hue, 200, 230), np.uint8)
            img = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
            x = int((size[0] - 60) * (0.5 + 0.5 * np.sin(2 * np.pi * i / n)))
            cv2.rectangle(img, (x, size[1] // 2 - 30), (x + 60, size[1] // 2 + 30), (255, 255, 255), -1)
            cv2.putText(img, f"frame {i:03d}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3, cv2.LINE_AA)
            for packet in stream.encode(av.VideoFrame.from_ndarray(img, format="rgb24")):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)


def make_gif(path: Path, n: int = 12) -> None:
    frames = []
    for i in range(n):
        img = np.zeros((200, 200, 3), np.uint8)
        a = 2 * np.pi * i / n
        cv2.circle(img, (100 + int(60 * np.cos(a)), 100 + int(60 * np.sin(a))), 28, (255, 210, 60), -1)
        frames.append(Image.fromarray(img))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=80, loop=0)


def build(root: Path) -> ProjectStore:
    store = ProjectStore.create(root, "Demo ProjMap")
    project = store.load()
    node = project.nodes[0]
    ok, jpg = cv2.imencode(".jpg", make_photo(), [cv2.IMWRITE_JPEG_QUALITY, 90])
    node.photo = store.set_photo(node.id, jpg.tobytes(), "parede.jpg")
    node.photo_boundary = BOUNDARY

    with tempfile.TemporaryDirectory() as tmp:
        video, gif = Path(tmp) / "cores.mp4", Path(tmp) / "bola.gif"
        make_video(video)
        make_gif(gif)
        v = store.add_media(video, video.name)
        g = store.add_media(gif, gif.name)
    project.media[v.sha256] = v
    project.media[g.sha256] = g

    # Superfícies desenhadas sobre a foto e levadas ao projetor pela homografia.
    from ..content.patterns import photo_to_projector
    from ..core.geometry import apply_homography

    h = photo_to_projector(PHOTO_SIZE, BOUNDARY, (node.output.width, node.output.height))

    def to_proj(poly):
        return [tuple(round(c, 2) for c in p) for p in apply_homography(h, poly)]

    project.surfaces = [
        Surface(id="caixa-grande", label="Caixa grande", node_id=node.id, z=0,
                warp={"base": to_proj([[260, 430], [640, 400], [655, 770], [250, 790]])},
                source={"kind": "video", "media": v.sha256, "fit": "cover"}),
        Surface(id="caixa-pequena", label="Caixa pequena", node_id=node.id, z=1,
                warp={"base": to_proj([[700, 520], [960, 505], [968, 770], [705, 782]])},
                source={"kind": "gif", "media": g.sha256, "fit": "contain"}),
        Surface(id="coluna", label="Coluna", node_id=node.id, z=2, feather=0.04,
                warp={"base": to_proj([[1180, 120], [1290, 110], [1295, 790], [1185, 800]])},
                source={"kind": "test"}),
    ]
    store.save(project)
    return store


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="projmap.tools.demo", description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="shows/demo.projmap")
    args = parser.parse_args(argv)
    store = build(Path(args.project))
    print(f"Projeto de exemplo criado em {store.root}")
    print(f"Abra com: python -m projmap.master --project {store.root} --windowed --open")


if __name__ == "__main__":
    main()
