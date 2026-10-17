"""E2E ao vivo: motion HTML adicionado pela UI, com a webcam como entrada, em tela cheia no projetor.

Roda no PC do show — só com ``PROJMAP_LIVE=1``::

    $env:PROJMAP_LIVE=1; .\\.venv-projmap\\Scripts\\pytest.exe -q -s tests/projmap/test_e2e_live_motion.py

1. copia o show em uso neste PC e abre o mestre na tela do projetor;
2. **UI de verdade** (Playwright, sem mocks — ``projmap/ui/e2e-live``): seleciona
   a superfície, ``+ Motion`` com ``fixtures/motion_test_av.html``, "Entrada de
   vídeo do motion" = ``auto`` e "Tela cheia";
3. confere no snapshot real da janela do projetor: o marcador verde do motion no
   canto, a webcam ao vivo no centro (o motion recebeu ``motion:video``);
4. toca ~7 s de bumbo na saída de som (o loopback capta) e confere a barra de
   graves e o flash da batida desenhados pelo motion.

``PROJMAP_LIVE_OUT``: pasta para os PNGs de prova.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import pytest

if os.environ.get("PROJMAP_LIVE") != "1":
    pytest.skip("e2e ao vivo (projetor + webcam + som): rode com PROJMAP_LIVE=1", allow_module_level=True)

cv2 = pytest.importorskip("cv2")
sc = pytest.importorskip("soundcard")
httpx = pytest.importorskip("httpx")

from .live_helpers import RATE, REPO, kick_track, live_master  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "motion_test_av.html"
UI = REPO / "projmap" / "ui"
SNAP_W = 960


def _snap(url: str, node: str) -> np.ndarray:
    r = httpx.get(f"{url}/api/nodes/{node}/snapshot", params={"max_width": SNAP_W}, timeout=10)
    r.raise_for_status()
    return cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)  # BGR


def _say(text: str) -> None:
    """print que não quebra no console cp1252 do Windows."""
    print(text.encode("ascii", "replace").decode("ascii"))


def _is_green(px: np.ndarray) -> bool:
    b, g, r = (int(v) for v in px)
    return g > 180 and r < 90 and b < 90


@pytest.fixture(scope="module")
def master(tmp_path_factory):
    with live_master(tmp_path_factory.mktemp("live-motion")) as (url, show):
        yield url, show


def test_motion_html_pela_ui_com_webcam_em_tela_cheia_reage_ao_audio(master):
    url, show = master
    out_dir = Path(os.environ.get("PROJMAP_LIVE_OUT") or show.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    project = httpx.get(f"{url}/api/project").json()["project"]
    node = project["nodes"][0]
    surfaces = [s for s in project["surfaces"] if s["node_id"] == node["id"]]
    assert surfaces, "o show não tem superfície neste projetor"
    target = max(surfaces, key=lambda s: s["z"])  # a de cima, para nada cobrir o motion
    for other in surfaces:
        if other["id"] != target["id"]:  # só o motion na parede
            httpx.patch(f"{url}/api/surfaces/{other['id']}", json={"visible": False}).raise_for_status()
    httpx.patch(f"{url}/api/nodes/{node['id']}/output",
                json={"blackout": False, "pattern": "none", "intensity": 1.0}).raise_for_status()
    httpx.patch(f"{url}/api/audio", json={"device": "loopback", "gain": 1.0}).raise_for_status()

    # 2. UI de verdade
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    assert npx, "npx não encontrado (Node.js)"
    env = {**os.environ, "PROJMAP_LIVE_URL": url, "PROJMAP_LIVE_SURFACE_LABEL": target["label"] or target["id"],
           "PROJMAP_LIVE_MOTION_FILE": str(FIXTURE)}
    ui = subprocess.run([npx, "playwright", "test", "-c", "playwright.live.config.mts"], cwd=UI, env=env,
                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    _say(ui.stdout[-1500:])
    assert ui.returncode == 0, f"passo de UI falhou:\n{ui.stdout[-3000:]}\n{ui.stderr[-2000:]}"

    surf = next(s for s in httpx.get(f"{url}/api/project").json()["project"]["surfaces"] if s["id"] == target["id"])
    w, h = node["output"]["width"], node["output"]["height"]
    assert surf["source"]["kind"] == "motion" and surf["source"]["device"] == "auto"
    assert surf["warp"]["base"] == [[0, 0], [w, 0], [w, h], [0, h]]

    # 3. o motion está na parede (o navegador sobe e o motion começa a mandar quadros)
    k = SNAP_W / w
    marker = (int(30 * k * w / 1280), int(30 * k * h / 720))  # dentro do quadrado verde (80x80 em 1280x720)
    end = time.monotonic() + 60
    img = _snap(url, node["id"])
    while not _is_green(img[marker[1], marker[0]]) and time.monotonic() < end:
        time.sleep(0.5)
        img = _snap(url, node["id"])
    status = httpx.get(f"{url}/api/motions/host").json()
    assert _is_green(img[marker[1], marker[0]]), f"motion não apareceu na saída: {status}"
    print(f"\nnavegador dos motions: {status['browser_exe']} · host {status['host_stats']}")

    sh, sw = img.shape[:2]
    center = (slice(int(sh * 0.3), int(sh * 0.7)), slice(int(sw * 0.3), int(sw * 0.7)))
    flash_box = (slice(int(sh * 0.42), int(sh * 0.47)), slice(int(sw * 0.02), int(sw * 0.045)))
    bass_px = (int(sh * 0.97), int(sw * 0.01))

    def center_is_webcam(im: np.ndarray) -> bool:
        c = im[center].astype(np.float32)
        return float(c.std()) > 12 and abs(float(c.mean()) - 40) > 8  # não é o cinza 40 de "sem vídeo"

    end = time.monotonic() + 20
    while not center_is_webcam(img) and time.monotonic() < end:
        time.sleep(0.5)
        img = _snap(url, node["id"])
    assert center_is_webcam(img), "a webcam não chegou ao motion (centro ainda é o cinza de 'sem vídeo')"
    cam0 = sum(c["frames"] for c in httpx.get(f"{url}/api/inputs/audio").json()["captures"])
    quiet = [img] + [_snap(url, node["id"]) for _ in range(5)]
    (out_dir / "e2e_motion_silencio.png").write_bytes(cv2.imencode(".png", quiet[0])[1].tobytes())

    # 4. música
    track = kick_track(7.0)
    player = threading.Thread(target=lambda: sc.default_speaker().play(track, samplerate=RATE), daemon=True)
    player.start()
    time.sleep(1.5)  # histórico do detector de batida
    loud = []
    t_end = time.monotonic() + 4.5
    while time.monotonic() < t_end:
        loud.append(_snap(url, node["id"]))
    player.join(timeout=10)
    levels = httpx.get(f"{url}/api/inputs/audio").json()
    cam1 = sum(c["frames"] for c in levels["captures"])

    flash_q = [float(cv2.cvtColor(q[flash_box], cv2.COLOR_BGR2GRAY).mean()) for q in quiet]
    flash_l = [float(cv2.cvtColor(q[flash_box], cv2.COLOR_BGR2GRAY).mean()) for q in loud]
    bass_red = sum(1 for q in loud if (lambda b, g, r: r > 150 and g < 100 and b < 100)(*q[bass_px]))
    peak = loud[int(np.argmax(flash_l))]
    (out_dir / "e2e_motion_batida.png").write_bytes(cv2.imencode(".png", peak)[1].tobytes())
    flashes = sum(v > max(flash_q) + 60 for v in flash_l)
    _say(f"webcam: quadros {cam0}->{cam1} | flash silencio max {max(flash_q):.0f}, com musica "
          f"{flashes}/{len(loud)} snapshots no flash | barra de graves em {bass_red}/{len(loud)} | "
          f"audio {levels['device_label']!r} ativo={levels['active']} batidas={levels['beats']} | PNGs em {out_dir}")

    assert cam1 > cam0 + 60, "a webcam parou: o vídeo do motion não está ao vivo"
    assert flashes >= 2, "o motion não piscou com a batida da música"
    assert bass_red >= 2, "a barra de graves do motion não reagiu"
