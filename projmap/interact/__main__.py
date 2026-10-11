"""``python -m projmap.interact`` — motor interativo standalone (ex.: só com o TouchDesigner).

Exemplos::

    # descreve a cena em texto (LLM do repo; sem LLM usa palavras-chave)
    python -m projmap.interact --text "5 fantasmas que param quando eu olho e me perseguem quando viro" \\
        --osc-out 127.0.0.1:7000 --preview

    # preset + Kinect vindo do TouchDesigner por OSC (porta 7001)
    python -m projmap.interact --preset fantasmas-timidos --sensor osc --osc-out 127.0.0.1:7000

    # webcam na parede (MediaPipe; ver projmap/interact/README.md)
    python -m projmap.interact --preset fantasmas-timidos --sensor webcam --preview --debug

``--preview`` abre uma janela com o renderer nativo; sem ela o motor só envia
OSC (o TouchDesigner desenha). Ctrl+C encerra.
"""

from __future__ import annotations

import argparse
import logging
import time

from .nlp import default_client, scene_from_text
from .scene import PRESETS
from .runtime import build_runtime


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="projmap.interact", description=__doc__.split("\n")[0])
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--text", help="descrição em linguagem natural da cena")
    src.add_argument("--preset", choices=sorted(PRESETS), help="cena pronta")
    parser.add_argument("--no-llm", action="store_true", help="não usa LLM (só palavras-chave)")
    parser.add_argument("--sensor", default="sim", choices=["sim", "osc", "webcam"])
    parser.add_argument("--sensor-port", type=int, default=7001)
    parser.add_argument("--camera", type=int, default=0, help="índice da webcam (sensor webcam)")
    parser.add_argument("--osc-out", default=None, metavar="HOST:PORTA", help="ex.: 127.0.0.1:7000 (TouchDesigner)")
    parser.add_argument("--preview", action="store_true", help="janela com o renderer nativo")
    parser.add_argument("--windowed", action="store_true", help="preview em janela (senão tela cheia)")
    parser.add_argument("--display", type=int, default=0)
    parser.add_argument("--debug", action="store_true", help="mostra pessoa e região do olhar")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("projmap.interact")

    spec = PRESETS[args.preset] if args.preset else None
    if args.text:
        result = scene_from_text(args.text, None if args.no_llm else default_client(), use_llm=not args.no_llm)
        spec = result.spec
        log.info("cena '%s' gerada via %s %s", spec.title, result.source, "; ".join(result.notes))
    opts: dict = {}
    if args.sensor == "osc":
        opts = {"port": args.sensor_port}
    elif args.sensor == "webcam":
        opts = {"camera": args.camera}
    rt = build_runtime(spec, sensor=args.sensor, osc_out=args.osc_out, sensor_options=opts).start()
    rt.debug_overlay = args.debug
    log.info("rodando '%s' · sensor %s%s", rt.spec.title, args.sensor,
             f" · OSC → {args.osc_out}" if args.osc_out else "")
    try:
        if args.preview:
            _preview(args)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        rt.stop()


def _preview(args) -> None:
    """Reusa a janela de saída do ProjMap com uma superfície cheia de fonte ``interactive``."""
    from ..core.geometry import rect_quad
    from ..core.project import Node, Project, Surface
    from ..node.window import run_output

    w, h = 1280, 720
    project = Project(
        name="Preview interativo",
        nodes=[Node(id="preview", name="Preview", output={"width": w, "height": h})],
        surfaces=[Surface(id="cena", node_id="preview", warp={"base": rect_quad(0, 0, w, h)},
                          source={"kind": "interactive"})],
    )
    run_output(lambda: (1, project), "preview", lambda sha: None, lambda rel: None,  # type: ignore[arg-type,return-value]
               display=args.display, windowed=args.windowed)


if __name__ == "__main__":
    main()
