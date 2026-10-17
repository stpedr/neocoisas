"""Utilitários dos e2e ao vivo (projetor + webcam + som deste PC). Só usados com ``PROJMAP_LIVE=1``."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
RATE = 48000


def launcher() -> dict:
    cfg = Path.home() / ".projmap" / "launcher.json"
    return json.loads(cfg.read_text(encoding="utf-8")) if cfg.is_file() else {}


def show_dir() -> Path:
    """O show em uso neste PC (``PROJMAP_LIVE_SHOW`` ou o último aberto no lançador)."""
    if os.environ.get("PROJMAP_LIVE_SHOW"):
        return Path(os.environ["PROJMAP_LIVE_SHOW"])
    cfg = launcher()
    if not cfg.get("shows_dir") or not cfg.get("last_show"):
        pytest.skip("sem show conectado: defina PROJMAP_LIVE_SHOW")
    return Path(cfg["shows_dir"]) / f"{cfg['last_show']}.projmap"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def kick_track(seconds: float, bpm: float = 120.0) -> np.ndarray:
    """Bumbo (varredura 150→45 Hz) em cada tempo + chiado baixo contínuo
    (mantém o analisador fora do 'silêncio' entre as batidas). Estéreo float32."""
    n = int(seconds * RATE)
    rng = np.random.default_rng(7)
    out = 0.01 * rng.standard_normal(n)
    kick_len = int(0.25 * RATE)
    kt = np.arange(kick_len) / RATE
    freq = 45 + 105 * np.exp(-kt / 0.04)
    kick = np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-kt / 0.09)
    for start in np.arange(0.5, seconds - 0.3, 60.0 / bpm):
        i = int(start * RATE)
        out[i:i + kick_len] += 0.7 * kick[: n - i]
    return np.clip(out, -1, 1).astype(np.float32).reshape(-1, 1).repeat(2, axis=1)


@contextlib.contextmanager
def live_master(tmp: Path) -> Iterator[tuple[str, Path]]:
    """Cópia do show deste PC + mestre com a saída em tela cheia na tela do projetor do lançador."""
    import httpx

    src = show_dir()
    assert (src / "project.json").is_file(), f"show não encontrado: {src}"
    show = tmp / src.name
    shutil.copytree(src, show, ignore=shutil.ignore_patterns("cache", "captures"))
    port = free_port()
    display = os.environ.get("PROJMAP_LIVE_DISPLAY") or str(launcher().get("display", "auto"))
    log_path = tmp / "master.log"
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "projmap.master", "--project", str(show), "--port", str(port),
                             "--display", display, "--no-interact"],
                            cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        end = time.monotonic() + 40
        while True:
            assert proc.poll() is None, f"mestre saiu (ver {log_path})"
            try:
                if httpx.get(f"{url}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            assert time.monotonic() < end, "mestre não subiu em 40 s"
            time.sleep(0.3)
        yield url, show
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        print(f"\nlog do mestre: {log_path}")
