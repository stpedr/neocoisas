"""Servidor MCP do ProjMap: ferramentas → API real do mestre (em memória)."""

import asyncio
import base64
import json
import threading
import time

import numpy as np
import pytest

pytest.importorskip("mcp")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402
from mcp import Client  # noqa: E402

from projmap.core.state import ProjectState  # noqa: E402
from projmap.core.store import ProjectStore  # noqa: E402
from projmap.master.app import create_app  # noqa: E402
from projmap.mcp_server.client import ProjMapClient, ProjMapError  # noqa: E402
from projmap.mcp_server.server import build_server  # noqa: E402
from projmap.node.tap import OutputTap  # noqa: E402


@pytest.fixture
def env(tmp_path):
    store = ProjectStore.create(tmp_path / "show.projmap", "Show MCP")
    state = ProjectState(store)
    tap = OutputTap()
    app = create_app(state, output_tap=tap, save_library_config=False, config_dir=tmp_path)
    client = ProjMapClient(http=TestClient(app))
    return build_server(client), state, tap


def _call(server, tool, args=None):
    async def go():
        async with Client(server) as c:
            return await c.call_tool(tool, args or {})

    return asyncio.run(go())


def _data(result):
    assert not result.is_error, result.content
    text = result.content[0].text
    return json.loads(text)


def test_lista_as_ferramentas(env):
    server, _, _ = env

    async def go():
        async with Client(server) as c:
            return {t.name for t in (await c.list_tools()).tools}

    assert {"status", "list_inputs", "audio_levels", "set_audio_input", "create_surface", "map_fullscreen",
            "set_surface_source", "set_surface_fx", "set_output", "snapshot_output"} <= asyncio.run(go())


def test_fluxo_video_ao_vivo_com_efeito_de_audio_em_tela_cheia(env):
    server, state, _ = env
    assert _data(_call(server, "set_audio_input", {"device": "loopback", "gain": 1.5})) == {
        "device": "loopback", "gain": 1.5}
    created = _data(_call(server, "create_surface", {"label": "Câmera", "fullscreen": False}))
    sid = created["surface_id"]
    assert created["node_id"] == "proj-1"
    assert _data(_call(server, "map_fullscreen", {"surface_id": sid}))["quad"][2] == [1920, 1080]
    src = _data(_call(server, "set_surface_source", {"surface_id": sid, "kind": "capture", "device": "auto"}))
    assert src["source"]["kind"] == "capture" and src["source"]["device"] == "auto"
    fx = [{"type": "strobe", "band": "beat", "amount": 0.8}, {"type": "pulse", "band": "bass", "amount": 0.6}]
    assert len(_data(_call(server, "set_surface_fx", {"surface_id": sid, "fx": fx}))["fx"]) == 2

    surf = state.snapshot()[1].surfaces[0]
    assert surf.source.kind == "capture" and [f.type for f in surf.fx] == ["strobe", "pulse"]
    st = _data(_call(server, "status"))
    assert st["project"]["surfaces"][0]["fx"][0]["band"] == "beat"
    assert st["project"]["audio"]["gain"] == 1.5


def test_erro_da_api_vira_mensagem_para_o_modelo(env):
    server, _, _ = env
    res = _call(server, "map_fullscreen", {"surface_id": "nao-existe"})
    assert res.is_error and "não existe" in res.content[0].text
    res = _call(server, "set_surface_fx", {"surface_id": "x", "fx": [{"type": "pulse", "amount": 5}]})
    assert res.is_error  # schema da ferramenta recusa amount > 1


def test_snapshot_volta_imagem_png(env):
    server, _, tap = env
    tap.attached = True
    stop = threading.Event()

    def window():
        while not stop.is_set():
            tap.service(lambda: np.full((90, 160, 3), 80, np.uint8))
            time.sleep(0.005)

    th = threading.Thread(target=window, daemon=True)
    th.start()
    try:
        res = _call(server, "snapshot_output", {"max_width": 80})
    finally:
        stop.set()
        th.join()
    assert not res.is_error
    img = res.content[0]
    assert img.type == "image" and img.mime_type == "image/png"
    assert base64.b64decode(img.data)[:8] == b"\x89PNG\r\n\x1a\n"


def test_mestre_fora_do_ar_da_erro_claro():
    client = ProjMapClient(url="http://127.0.0.1:9", timeout=0.5)
    with pytest.raises(ProjMapError, match="inacessível"):
        client.health()
