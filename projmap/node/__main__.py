"""``python -m projmap.node`` — toca um projeto salvo, sem mestre.

Útil para deixar uma instalação fixa rodando (ex.: Pi ligado direto no
projetor, iniciado pelo systemd) e base do processo de nó da F2. Recarrega
sozinho quando o ``project.json`` muda no disco::

    python -m projmap.node --project shows/teste.projmap --display 0
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..core.store import ProjectStore
from .window import file_snapshot, run_output


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="projmap.node", description=__doc__.split("\n")[0])
    parser.add_argument("--project", required=True, help="diretório do projeto (.projmap)")
    parser.add_argument("--node", default=None, help="id do nó (padrão: o primeiro)")
    parser.add_argument("--display", default="auto", help="tela da saída: auto, 0 (principal), 1, 2…")
    parser.add_argument("--windowed", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    store = ProjectStore(args.project)
    if not store.exists():
        raise SystemExit(f"projeto não encontrado: {store.project_path}")
    snapshot = file_snapshot(store.project_path, store.load)
    _, project = snapshot()
    node_id = args.node or project.nodes[0].id

    def media_path(sha: str) -> Path:
        _, p = snapshot()
        return store.media_path(p.media[sha])

    run_output(snapshot, node_id, media_path, store.resolve, display=args.display, windowed=args.windowed)


if __name__ == "__main__":
    main()
