"""Testes de regressão para as correções de segurança P0 (FASE 4 — Passo A)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from projmap.core.state import ProjectState
from projmap.core.store import ProjectStore
from projmap.interact.runtime import InteractionRuntime
from projmap.interact.sensors import MAX_OSC_PLAYERS, OscSensor, get_sensor
from projmap.interact.stream import esconder_senha
from projmap.master import app as master_app
from projmap.master.app import create_app


def test_loopback_blocks_dns_rebinding_and_cross_origin_csrf_cswsh(tmp_path: Path) -> None:
    store = ProjectStore.create(tmp_path / "sec", name="Show Seguro")
    state = ProjectState(store)
    runtime = InteractionRuntime()
    app = create_app(
        state,
        runtime=runtime,
        token="segredo-forte",
        host="0.0.0.0",
        port=8100,
        library_roots=[],
        save_library_config=False,
        config_dir=tmp_path / "cfg",
    )
    client = TestClient(app, client=("127.0.0.1", 54000))

    # 1. Pedido legítimo de loopback (Host: localhost:8100, Origin: http://localhost:8100) passa
    assert (
        client.get(
            "/api/project",
            headers={"Host": "localhost:8100", "Origin": "http://localhost:8100"},
        ).status_code
        == 200
    )

    # 2. DNS Rebinding: IP de origem é 127.0.0.1, mas Host é um domínio externo
    assert (
        client.get(
            "/api/project",
            headers={"Host": "evil.rebind.attacker.com:8100"},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/remote/pair",
            headers={"Host": "evil.rebind.attacker.com:8100"},
        ).status_code
        == 401
    )

    # 3. Cross-Origin CSRF: IP é 127.0.0.1, Host é 127.0.0.1:8100, mas Origin é site externo
    assert (
        client.post(
            "/api/interact/presets/vaga-lumes",
            headers={"Host": "127.0.0.1:8100", "Origin": "https://site-malicioso.example"},
        ).status_code
        == 401
    )

    # 4. Cross-Site WebSocket Hijacking (CSWSH) em /api/interact/phone sem token
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/api/interact/phone",
            headers={"Host": "127.0.0.1:8100", "Origin": "https://site-malicioso.example"},
        ):
            pass
    assert exc_info.value.code == 4401


def test_export_pmz_cleans_up_temp_directory(tmp_path: Path) -> None:
    store = ProjectStore.create(tmp_path / "exp", name="Show Export")
    state = ProjectState(store)
    app = create_app(state, library_roots=[], save_library_config=False, config_dir=tmp_path / "cfg")
    client = TestClient(app)

    tmp_root = Path(tempfile.gettempdir())
    before = set(tmp_root.glob("projmap-export-*"))
    res = client.get("/api/project/export")
    assert res.status_code == 200
    after = set(tmp_root.glob("projmap-export-*"))
    assert after - before == set()


def test_photo_upload_enforces_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(master_app, "MAX_PHOTO_BYTES", 1024)
    store = ProjectStore.create(tmp_path / "photo", name="Show Foto")
    state = ProjectState(store)
    app = create_app(state, library_roots=[], save_library_config=False, config_dir=tmp_path / "cfg")
    client = TestClient(app)

    oversized = b"x" * 2048
    res = client.post(
        "/api/nodes/proj-1/photo",
        files={"file": ("grande.jpg", oversized, "image/jpeg")},
    )
    assert res.status_code == 413


def test_sensor_options_whitelist_and_osc_hardening(tmp_path: Path) -> None:
    store = ProjectStore.create(tmp_path / "sens", name="Show Sensor")
    state = ProjectState(store)
    runtime = InteractionRuntime()
    app = create_app(
        state,
        runtime=runtime,
        library_roots=[],
        save_library_config=False,
        config_dir=tmp_path / "cfg",
    )
    client = TestClient(app)

    # Opção arbitrária desconhecida deve retornar 422
    r_bad = client.post("/api/interact/sensor", json={"kind": "sim", "options": {"injetado": 123}})
    assert r_bad.status_code == 422

    # model_path via HTTP deve ser bloqueado com 422
    r_mp = client.post(
        "/api/interact/sensor",
        json={"kind": "webcam", "options": {"model_path": "/etc/passwd"}},
    )
    assert r_mp.status_code == 422

    # OscSensor faz bind em 127.0.0.1 por padrão e limita total de jogadores a MAX_OSC_PLAYERS
    sensor = get_sensor("osc", port=0)
    assert isinstance(sensor, OscSensor)
    try:
        assert sensor._server.server_address[0] == "127.0.0.1"
        for pid in range(MAX_OSC_PLAYERS + 15):
            sensor._on_player("/player", pid, 0.5, 1.5, 0.0, 1)
        assert len(sensor._players) <= MAX_OSC_PLAYERS
    finally:
        sensor.close()


def test_esconder_senha_masks_rtsp_rtsps_and_https() -> None:
    assert esconder_senha("rtsp://op:123456@10.0.0.5:8554/live") == "rtsp://op:***@10.0.0.5:8554/live"
    assert esconder_senha("rtsps://op:segredo@stream.local:8322/cam") == "rtsps://op:***@stream.local:8322/cam"
    assert esconder_senha("https://user:token123@api.local/hook") == "https://user:***@api.local/hook"
