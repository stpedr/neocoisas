"""``python -m projmap.master`` — mestre da F1: UI web + saída local no mesmo processo.

Exemplos::

    # projeto novo (ou existente) e saída em tela cheia no 2º monitor/projetor
    python -m projmap.master --project shows/teste.projmap --display 1

    # sem projetor: saída numa janela de preview
    python -m projmap.master --project shows/teste.projmap --windowed

    # só a UI/API (sem janela)
    python -m projmap.master --project shows/teste.projmap --no-output

    # abrir um pacote .pmz exportado (extrai num diretório novo)
    python -m projmap.master --import show.pmz --project shows/copia.projmap

A janela (pyglet) precisa da thread principal; o servidor (uvicorn) roda numa
thread de fundo. Na F2 a janela sai daqui e vira o processo do nó.
"""

from __future__ import annotations

import argparse
import logging
import threading
import webbrowser
from pathlib import Path

from ..core.state import ProjectState
from ..core.store import ProjectStore

UI_DIR = Path(__file__).resolve().parent.parent / "ui" / "out"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="projmap.master", description=__doc__.split("\n")[0])
    parser.add_argument("--project", required=True, help="diretório do projeto (.projmap); criado se não existir")
    parser.add_argument("--name", default="Novo projeto", help="nome ao criar um projeto novo")
    parser.add_argument("--import", dest="import_pmz", help="extrai este .pmz em --project antes de abrir")
    parser.add_argument("--host", default="127.0.0.1", help="interface do servidor (padrão: só esta máquina)")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--node", default=None, help="nó desta saída (padrão: o primeiro do projeto)")
    parser.add_argument("--display", type=int, default=0, help="índice do monitor/projetor para a saída")
    parser.add_argument("--windowed", action="store_true", help="saída em janela (preview) em vez de tela cheia")
    parser.add_argument("--no-output", action="store_true", help="não abre a janela de saída")
    parser.add_argument("--open", action="store_true", help="abre a UI no navegador")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("projmap.master")

    if args.import_pmz:
        store = ProjectStore.import_pmz(args.import_pmz, args.project)
        log.info("pacote importado em %s", store.root)
    else:
        store = ProjectStore.open_or_create(args.project, args.name)
    state = ProjectState(store)
    _, project = state.snapshot()
    node_id = args.node or project.nodes[0].id

    import uvicorn

    from .app import create_app

    app = create_app(state, UI_DIR)
    if args.host not in ("127.0.0.1", "localhost"):
        log.warning("servidor exposto em %s SEM autenticação (o token de pareamento chega na F2/F6)", args.host)
    url = f"http://{'localhost' if args.host in ('0.0.0.0', '127.0.0.1') else args.host}:{args.port}"
    log.info("UI/API: %s · projeto: %s", url, store.root)
    if not (UI_DIR / "index.html").is_file():
        log.warning("UI não compilada (%s). Rode: cd projmap/ui && npm ci && npm run build", UI_DIR)
    if args.open:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="warning"))
    if args.no_output:
        server.run()
        return

    thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    thread.start()

    from ..node.window import run_output

    def media_path(sha: str) -> Path:
        _, p = state.snapshot()
        return store.media_path(p.media[sha])

    try:
        run_output(state.snapshot, node_id, media_path, store.resolve, display=args.display,
                   windowed=args.windowed)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
