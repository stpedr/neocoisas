"""Janela de saída do projetor (pyglet + moderngl).

- Tela cheia sem bordas no monitor escolhido (``--display``: ``auto`` = projetor,
  ``0`` = principal, ``1``… = as outras; ver ``screens.py``), com vsync.
- A cada frame compara a revisão do projeto (um inteiro) e só reconstrói a lista
  de desenho quando ela muda — arrastar um canto na UI aparece na parede no
  frame seguinte.
- Atalhos: ``F`` alterna tela cheia, ``Ctrl+Q`` fecha. ``Esc`` *não* fecha (num
  show, um esbarrão no teclado não pode apagar a projeção).
- Loga fps médio e pior frame a cada 5 s — é a medição do aceite "1080p30".
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Optional

from ..core.project import Project
from .renderer import MediaResolver, PathResolver, Renderer

log = logging.getLogger(__name__)

Snapshot = Callable[[], tuple[int, Project]]


def run_output(
    snapshot: Snapshot,
    node_id: str,
    media_path: MediaResolver,
    resolve_path: PathResolver,
    display: "int | str" = "auto",
    windowed: bool = False,
    window_size: tuple[int, int] = (960, 540),
    on_frame: Optional[Callable[[], None]] = None,
) -> None:
    import moderngl
    import pyglet

    from .screens import choose_screen, list_screens

    _guard_dpi_event(pyglet)

    screens = list_screens()
    chosen = choose_screen(screens, display)
    if chosen is None:  # número além das telas existentes
        chosen = choose_screen(screens, "auto")
        log.warning("tela %s não existe (%d disponíveis); usando %s", display, len(screens), chosen.label)
    screen = chosen.handle
    log.info("saída na tela %s em (%d, %d)", chosen.label, chosen.x, chosen.y)
    if len(screens) == 1 and not windowed:
        log.warning("só uma tela detectada: o projetor está em modo Duplicar? Use Windows+P -> Estender")

    config = pyglet.gl.Config(double_buffer=True, major_version=3, minor_version=3, forward_compatible=True)
    rev, project = snapshot()
    caption = f"ProjMap · {project.node(node_id).name or node_id}"
    if windowed:
        window = pyglet.window.Window(*window_size, caption=caption, resizable=True, vsync=True,
                                      screen=screen, config=config)
    else:
        window = pyglet.window.Window(fullscreen=True, screen=screen, caption=caption, vsync=True, config=config)
        window.set_mouse_visible(False)

    ctx = moderngl.create_context()
    log.info("GL: %s · %s", ctx.info.get("GL_RENDERER"), ctx.info.get("GL_VERSION"))
    renderer = Renderer(ctx, media_path, resolve_path)
    renderer.sync(project, node_id)
    current_rev = rev
    t0 = time.perf_counter()
    stats = {"frames": 0, "worst": 0.0, "since": t0, "last": t0}

    @window.event
    def on_draw():  # noqa: ANN202
        nonlocal current_rev
        rev_now, proj = snapshot()
        if rev_now != current_rev:
            try:
                renderer.sync(proj, node_id)
            except KeyError:
                log.error("nó '%s' removido do projeto", node_id)
            current_rev = rev_now
        fb_w, fb_h = window.get_framebuffer_size()
        ctx.screen.viewport = (0, 0, fb_w, fb_h)
        now = time.perf_counter()
        renderer.render(ctx.screen, now - t0)
        dt = now - stats["last"]
        stats["last"] = now
        stats["frames"] += 1
        stats["worst"] = max(stats["worst"], dt)
        if now - stats["since"] >= 5.0:
            fps = stats["frames"] / (now - stats["since"])
            log.info("saída %s: %.1f fps · pior frame %.1f ms", node_id, fps, stats["worst"] * 1000)
            stats.update(frames=0, worst=0.0, since=now)
        if on_frame:
            on_frame()

    @window.event
    def on_key_press(symbol, modifiers):  # noqa: ANN001, ANN202
        key = pyglet.window.key
        if symbol == key.F:
            window.set_fullscreen(not window.fullscreen)
            window.set_mouse_visible(not window.fullscreen)
        elif symbol == key.Q and modifiers & key.MOD_CTRL:
            window.close()
        elif symbol == key.ESCAPE:
            return pyglet.event.EVENT_HANDLED  # não fecha
        return None

    @window.event
    def on_close():  # noqa: ANN202
        renderer.release()

    pyglet.app.run(interval=0)  # redesenha o mais rápido possível; o vsync limita ao refresh


def file_snapshot(project_file: Path, load: Callable[[], Project]) -> Snapshot:
    """Snapshot que recarrega o projeto quando o arquivo muda (nó standalone)."""
    state = {"rev": 0, "mtime": None, "project": None, "checked": 0.0}

    def snap() -> tuple[int, Project]:
        now = time.monotonic()
        if state["project"] is None or now - state["checked"] > 0.5:
            state["checked"] = now
            mtime = project_file.stat().st_mtime_ns
            if mtime != state["mtime"]:
                try:
                    state["project"] = load()
                    state["mtime"] = mtime
                    state["rev"] += 1
                except Exception as exc:  # noqa: BLE001 — arquivo no meio de uma edição manual
                    log.error("project.json inválido, mantendo o anterior: %s", exc)
                    if state["project"] is None:
                        raise
        return state["rev"], state["project"]

    return snap


def _guard_dpi_event(pyglet) -> None:
    """Ao abrir a janela num projetor com outra escala (ex.: notebook 150%,
    projetor 100%), o Windows manda WM_DPICHANGED antes de o contexto GL existir
    e o pyglet levanta "Canvas has not been attached". Ignorar esse evento
    inicial é seguro: o tamanho real é lido a cada quadro."""
    try:
        from pyglet.window.win32 import Win32Window
    except ImportError:  # não é Windows
        return
    original = getattr(Win32Window, "_event_dpi_change", None)
    if original is None or getattr(original, "_projmap_guard", False):
        return

    import functools

    @functools.wraps(original)  # copia o _platform_event_data que o pyglet usa para registrar o evento
    def guarded(self, msg, wParam, lParam):
        try:
            return original(self, msg, wParam, lParam)
        except RuntimeError as exc:
            if "not been attached" not in str(exc):
                raise
            return 0

    guarded._projmap_guard = True
    Win32Window._event_dpi_change = guarded
