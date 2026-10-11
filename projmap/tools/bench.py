"""``python -m projmap.tools.bench`` — mede o renderer (aceite F1: 1080p30 com 4 superfícies).

Renderiza offscreen N superfícies de vídeo, cada uma com seu próprio decoder,
avançando o relógio a 30 fps. Mede o tempo de parede por frame (decodificação
+ upload de textura + desenho + ``finish``). Não mede o vsync da janela: isso o
log da janela de saída mostra (fps a cada 5 s).

    python -m projmap.tools.bench --surfaces 4 --seconds 10
"""

from __future__ import annotations

import argparse
import statistics
import tempfile
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="projmap.tools.bench")
    parser.add_argument("--surfaces", type=int, default=4)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--video-size", default="1280x720", help="resolução de cada vídeo de teste")
    args = parser.parse_args(argv)

    import moderngl

    from ..core.geometry import rect_quad
    from ..core.project import Node, Project, Surface
    from ..core.store import ProjectStore
    from ..node.renderer import Renderer
    from .demo import make_video

    vw, vh = (int(v) for v in args.video_size.split("x"))
    with tempfile.TemporaryDirectory() as tmp:
        store = ProjectStore.create(Path(tmp) / "bench.projmap")
        project = store.load()
        surfaces = []
        cols = 2
        for i in range(args.surfaces):
            video = Path(tmp) / f"v{i}.mp4"
            make_video(video, seconds=4.0, fps=args.fps, size=(vw, vh))
            item = store.add_media(video, video.name)
            project.media[item.sha256] = item
            x, y = (i % cols) * 960 + 40, (i // cols) * 540 + 30
            q = rect_quad(x, y, 880, 480)
            q[1][1] += 25
            q[2][0] -= 30  # um pouco de perspectiva
            surfaces.append(Surface(id=f"s{i}", node_id="proj-1", warp={"base": q},
                                    source={"kind": "video", "media": item.sha256, "fit": "cover"}))
        project = Project(nodes=[Node(id="proj-1")], surfaces=surfaces, media=project.media)

        ctx = moderngl.create_standalone_context()
        fbo = ctx.simple_framebuffer((1920, 1080), components=4)
        renderer = Renderer(ctx, lambda sha: store.media_path(project.media[sha]), store.resolve)
        renderer.sync(project, "proj-1")
        # aquece decoders
        for item in renderer._items:  # noqa: SLF001
            item.source.frame_at(0.0, block_timeout=5.0)

        frames = int(args.seconds * args.fps)
        times = []
        t0 = time.perf_counter()
        for i in range(frames):
            start = time.perf_counter()
            renderer.render(fbo, i / args.fps)
            ctx.finish()
            times.append(time.perf_counter() - start)
            # Simula o relógio real: não adianta renderizar à frente do tempo.
            target = t0 + (i + 1) / args.fps
            delay = target - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        renderer.release()

    gl = ctx.info.get("GL_RENDERER")
    times_ms = sorted(t * 1000 for t in times)
    budget = 1000 / args.fps
    p95 = times_ms[int(len(times_ms) * 0.95) - 1]
    over = sum(t > budget for t in times_ms)
    print(f"GL: {gl}")
    print(f"{args.surfaces} superfícies de vídeo {vw}x{vh} → saída 1920x1080, {frames} frames a {args.fps} fps")
    print(f"tempo por frame: mediana {statistics.median(times_ms):.1f} ms · p95 {p95:.1f} ms · "
          f"máx {times_ms[-1]:.1f} ms (orçamento {budget:.1f} ms)")
    print(f"frames acima do orçamento: {over}/{frames} → {'OK' if p95 <= budget else 'ACIMA DO ORÇAMENTO'}")


if __name__ == "__main__":
    main()
