"""E2E ao vivo: vídeo da webcam em tela cheia no projetor, com efeito movido pelo áudio.

Roda no PC do show, com o projetor ligado — por isso só com ``PROJMAP_LIVE=1``::

    $env:PROJMAP_LIVE=1; .\\.venv-projmap\\Scripts\\pytest.exe -q -s tests/projmap/test_e2e_live_av.py

O que ele faz, tudo pelo **servidor MCP** (o mesmo que um agente usaria):

1. copia o show em uso neste PC (``~/.projmap/launcher.json``: pasta + último
   show) para um diretório temporário — o mapeamento original não é tocado;
2. abre o mestre com a saída em tela cheia na tela do projetor do lançador;
3. MCP: confere as entradas, escolhe o áudio ``loopback``, mapeia a
   superfície do show em **tela cheia**, troca a fonte para a **entrada de
   vídeo** (webcam) e aplica ``strobe`` na batida + ``pulse`` nos graves;
4. toca um bumbo sintético a 120 BPM na saída de som padrão (≈6 s) — o
   loopback capta, o analisador acha as batidas e a parede pisca no tempo;
5. compara snapshots reais da janela do projetor: em silêncio × com música.

Variáveis: ``PROJMAP_LIVE_SHOW`` (outro show), ``PROJMAP_LIVE_DISPLAY``
(outra tela), ``PROJMAP_LIVE_OUT`` (onde salvar os PNGs de prova).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

if os.environ.get("PROJMAP_LIVE") != "1":
    pytest.skip("e2e ao vivo (projetor + webcam + som): rode com PROJMAP_LIVE=1", allow_module_level=True)

pytest.importorskip("mcp")
cv2 = pytest.importorskip("cv2")
sc = pytest.importorskip("soundcard")
httpx = pytest.importorskip("httpx")
from mcp import Client, StdioServerParameters  # noqa: E402

from .live_helpers import REPO, kick_track, live_master  # noqa: E402

RATE = 48000


def _dark_luma(png: bytes) -> float:
    """Percentil 10 da luma: as partes escuras da cena só ficam claras no flash do
    ``strobe`` (a média não serve — câmera com auto-exposição já deixa a cena clara)."""
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    return float(np.percentile(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 10))


@pytest.fixture(scope="module")
def master(tmp_path_factory):
    with live_master(tmp_path_factory.mktemp("live")) as (url, show):
        yield url, show


def test_webcam_em_tela_cheia_pisca_na_batida_do_audio(master):
    url, show = master
    out_dir = Path(os.environ.get("PROJMAP_LIVE_OUT") or show.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    params = StdioServerParameters(command=sys.executable, args=["-m", "projmap.mcp_server"], cwd=str(REPO),
                                   env={"PROJMAP_URL": url})

    async def run() -> dict:
        async with Client(params, read_timeout_seconds=30) as c:
            async def call(tool: str, args: dict | None = None):
                res = await c.call_tool(tool, args or {})
                assert not res.is_error, f"{tool}: {res.content[0].text}"
                return res

            async def data(tool: str, args: dict | None = None) -> dict:
                return json.loads((await call(tool, args)).content[0].text)

            async def snap() -> bytes:
                return base64.b64decode((await call("snapshot_output", {"max_width": 480})).content[0].data)

            inputs = await data("list_inputs")
            cams = [v for v in inputs["video"] if not v["virtual"]]
            assert cams, f"nenhuma câmera física: {inputs['video']}"
            print(f"\ncâmera: {cams[0]['name']} · áudio: {len(inputs['audio'])} dispositivos")

            await data("set_audio_input", {"device": "loopback", "gain": 1.0})
            status = await data("status")
            node = status["project"]["nodes"][0]
            surfaces = [s for s in status["project"]["surfaces"] if s["node_id"] == node["id"]]
            if surfaces:
                sid = surfaces[0]["id"]
                for other in surfaces[1:]:  # só a superfície da câmera na parede
                    await data("set_surface_source", {"surface_id": other["id"], "kind": "none", "visible": False})
            else:
                sid = (await data("create_surface", {"label": "Câmera", "node_id": node["id"]}))["surface_id"]
            quad = (await data("map_fullscreen", {"surface_id": sid}))["quad"]
            assert quad == [[0, 0], [node["width"], 0], [node["width"], node["height"]], [0, node["height"]]]
            await data("set_surface_source", {"surface_id": sid, "kind": "capture", "device": "auto",
                                              "fit": "cover", "visible": True})
            await data("set_output", {"blackout": False, "pattern": "none", "intensity": 1.0})
            await data("set_surface_fx", {"surface_id": sid, "fx": [
                {"type": "strobe", "band": "beat", "amount": 0.9},
                {"type": "pulse", "band": "bass", "amount": 0.6},
                {"type": "rgb_split", "band": "high", "amount": 0.5},
            ]})

            # a webcam precisa estar entregando quadros
            for _ in range(60):
                caps = (await data("audio_levels"))["captures"]
                if caps and caps[0]["frames"] > 15:
                    break
                await asyncio.sleep(0.25)
            assert caps and caps[0]["frames"] > 15, f"webcam sem quadros: {caps}"
            frames_before = caps[0]["frames"]

            await asyncio.sleep(1.5)  # deixa o envelope e o AGC assentarem no silêncio
            quiet = []
            for _ in range(8):
                quiet.append(await snap())
                await asyncio.sleep(0.1)

            track = kick_track(7.0)
            player = threading.Thread(target=lambda: sc.default_speaker().play(track, samplerate=RATE), daemon=True)
            player.start()
            await asyncio.sleep(1.5)  # histórico de ~1 s do detector de batida
            loud, levels = [], []
            t_end = time.monotonic() + 4.5
            while time.monotonic() < t_end:
                loud.append(await snap())
                levels.append(await data("audio_levels"))
            player.join(timeout=10)
            caps = (await data("audio_levels"))["captures"]
            return {"quiet": quiet, "loud": loud, "levels": levels, "frames": (frames_before, caps[0]["frames"]),
                    "camera": cams[0]["name"], "sid": sid}

    r = asyncio.run(run())
    q = [_dark_luma(p) for p in r["quiet"]]
    lo = [_dark_luma(p) for p in r["loud"]]
    peak = r["loud"][int(np.argmax(lo))]
    (out_dir / "e2e_silencio.png").write_bytes(r["quiet"][len(q) // 2])
    (out_dir / "e2e_batida.png").write_bytes(peak)
    beats = [lv["beats"] for lv in r["levels"]]
    bass = max(lv["levels"]["bass"] for lv in r["levels"])
    flashes = sum(v > np.median(q) + 60 for v in lo)
    print(f"luma p10 silencio: mediana {np.median(q):.1f} | com musica: mediana {np.median(lo):.1f}, "
          f"pico {max(lo):.1f}, {flashes}/{len(lo)} snapshots no flash | batidas {beats[0]}->{beats[-1]} | "
          f"grave max {bass:.2f} | quadros da webcam {r['frames'][0]}->{r['frames'][1]} | PNGs em {out_dir}")

    assert any(lv["active"] for lv in r["levels"]), "o loopback não captou o áudio tocado"
    assert beats[-1] - beats[0] >= 3, f"poucas batidas detectadas: {beats[0]}→{beats[-1]}"
    assert bass > 0.3
    assert r["frames"][1] > r["frames"][0] + 30, "a webcam parou durante o teste (vídeo não está ao vivo)"
    assert flashes >= 2, "a parede não piscou com a batida"
