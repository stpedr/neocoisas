"""``python -m projmap.master`` — mestre da F1: UI web + saída local no mesmo processo.

Exemplos::

    # projeto novo (ou existente) e saída em tela cheia no projetor (achado sozinho)
    python -m projmap.master --project shows/teste.projmap

    # sem projetor: saída numa janela de preview
    python -m projmap.master --project shows/teste.projmap --windowed

    # expor na LAN para o remote no celular (token gerado e mostrado no log/QR)
    python -m projmap.master --project shows/teste.projmap --host 0.0.0.0

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
    parser.add_argument("--library", action="append", default=None, metavar="PASTA",
                        help="pasta de mídias para a galeria (pode repetir; ex.: a pasta do Google Drive). "
                             "Padrão: as salvas na UI (~/.projmap/library.json)")
    parser.add_argument("--token", default=None,
                        help="token de pareamento do remote (padrão: gerado a cada execução, se exposto na LAN)")
    parser.add_argument("--node", default=None, help="nó desta saída (padrão: o primeiro do projeto)")
    parser.add_argument("--display", default="auto",
                        help="tela da saída: auto (= a primeira que não é a principal, o projetor), "
                             "0 = principal, 1, 2… = as outras da esquerda p/ direita. Liste: python -m projmap.node.screens")
    parser.add_argument("--windowed", action="store_true", help="saída em janela (preview) em vez de tela cheia")
    parser.add_argument("--no-output", action="store_true", help="não abre a janela de saída")
    parser.add_argument("--open", action="store_true", help="abre a UI no navegador")
    parser.add_argument("--sensor", default="sim", choices=["sim", "osc", "webcam", "phone"],
                        help="camada interativa: de onde vêm as pessoas (sim = pessoa virtual; "
                             "phone = celular na parede via /sensor)")
    parser.add_argument("--adb", action="store_true",
                        help="celular por USB: adb reverse da porta e abre /sensor no celular")
    parser.add_argument("--sensor-port", type=int, default=7001, help="porta OSC do sensor 'osc' (Kinect via TD)")
    parser.add_argument("--camera", default="auto",
                        help="sensor webcam: 'auto' (prefere Logitech/C920, ignora câmeras virtuais), parte do nome "
                             "(ex.: C920) ou índice. Liste com: python -m projmap.interact.cameras")
    parser.add_argument("--camera-size", default="1280x720", help="resolução da webcam (C920: 1280x720 a 30 fps)")
    parser.add_argument("--osc-out", default=None, metavar="HOST:PORTA",
                        help="envia o estado da cena por OSC (ex.: 127.0.0.1:7000 para o TouchDesigner)")
    parser.add_argument("--no-interact", action="store_true", help="desliga a camada interativa")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    _load_dotenv()

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
    from .auth import new_token
    from .remote import remote_url

    runtime = None
    if not args.no_interact:
        from ..interact.runtime import build_runtime

        opts = {"port": args.sensor_port} if args.sensor == "osc" else {}
        if args.sensor == "webcam":
            opts = {"camera": args.camera, "size": args.camera_size}
        runtime = build_runtime(sensor=args.sensor, osc_out=args.osc_out, sensor_options=opts,
                                scene_file=store.root / "scenes" / "active.json")
        runtime.camera = args.camera  # efeitos do visual_frames usam a mesma câmera escolhida
        runtime = runtime.start()
        log.info("camada interativa: cena '%s', sensor %s%s", runtime.spec.title, args.sensor,
                 f", OSC → {args.osc_out}" if args.osc_out else "")
        # Transmissão RTSP da camada interativa (só se PROJMAP_RTSP_URL estiver
        # no .env). A URL carrega senha, por isso não vem por linha de comando.
        from ..interact.stream import publisher_from_env

        publisher = publisher_from_env()
        if publisher is not None:
            runtime.publisher = publisher.start(runtime.render)

    exposed = args.host not in ("127.0.0.1", "localhost")
    token = args.token or pairing_token_from_env() or (new_token() if exposed else None)
    app = create_app(state, UI_DIR, runtime=runtime, token=token, host=args.host, port=args.port,
                     library_roots=args.library)
    if exposed:
        log.info("remote no celular (mesma rede): %s", remote_url(args.host, args.port, token))
        log.info("ou abra o card 'Remote' no editor e escaneie o QR")
    url = f"http://{'localhost' if args.host in ('0.0.0.0', '127.0.0.1') else args.host}:{args.port}"
    log.info("UI/API: %s · projeto: %s", url, store.root)
    if not (UI_DIR / "index.html").is_file():
        log.warning("UI não compilada (%s). Rode: cd projmap/ui && npm ci && npm run build", UI_DIR)
    if args.open:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    if args.adb:
        def _adb() -> None:
            from ..tools.adb import AdbError, connect_phone

            try:
                dev = connect_phone(args.port)
                log.info("celular %s ligado por USB: abrindo http://localhost:%d/sensor/ nele",
                         dev.model or dev.serial, args.port)
            except AdbError as exc:
                log.error("ADB: %s", exc)

        threading.Timer(1.5, _adb).start()

    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="warning"))
    if args.no_output:
        try:
            server.run()
        finally:
            if runtime:
                runtime.stop()
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
        if runtime:
            runtime.stop()


def _load_dotenv() -> None:
    """Lê ``.env.projmap`` / ``.env`` da raiz do repositório sem dependências externas."""
    load_projmap_env()


from ..config import load_projmap_env, pairing_token_from_env  # noqa: E402


if __name__ == "__main__":
    main()
