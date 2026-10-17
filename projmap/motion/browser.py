"""Chromium headless dedicado aos motions.

Por que um navegador "nosso" e não o do usuário:

- **GPU dedicada.** Em notebook híbrido o Windows põe o Chrome na GPU
  integrada; ler os pixels do canvas lá custa 40–60 ms por quadro (~15 fps).
  Na RTX cai para ~11 ms (30 fps). A preferência "Alto desempenho" é gravada
  só para o executável escolhido aqui (``tools/gpu.py``) — nunca para o Chrome
  ou Edge que o usuário usa no dia a dia.
- **Sem estrangulamento.** Flags que desligam timers/renderização de fundo e o
  EcoQoS do Windows; perfil próprio em ``~/.projmap/motion-browser``.

Ordem de busca: ``PROJMAP_BROWSER`` → Chromium do Playwright (``ms-playwright``)
→ Chrome → Edge → ``chromium``/``google-chrome`` no PATH.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

VIEWPORT = (1920, 1080)
FLAGS = [
    "--headless=new",
    "--no-first-run",
    "--no-default-browser-check",
    "--mute-audio",
    "--autoplay-policy=no-user-gesture-required",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-features=CalculateNativeWinOcclusion,UseEcoQoSForBackgroundProcess,IntensiveWakeUpThrottling,"
    "IsolateSandboxedIframes",  # iframe do motion no mesmo processo: o quadro não atravessa processos
    "--ignore-gpu-blocklist",
    "--enable-gpu-rasterization",
    # Nada de trabalho de "primeira execução" em segundo plano disputando CPU/GPU com o show.
    "--disable-extensions",
    "--disable-component-extensions-with-background-pages",
    "--disable-component-update",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-domain-reliability",
    "--no-pings",
    "--metrics-recording-only",
    "--disable-client-side-phishing-detection",
    "--disable-hang-monitor",
    # O agendador de quadros do headless é instável (o rAF oscila de ~1 a 30/s). Sem o limite,
    # quem marca o passo é o shim da página host (~60 Hz no motion, 30 Hz de captura).
    "--disable-frame-rate-limit",
    "--disable-gpu-vsync",
]
WINDOWS_FLAGS = ["--use-angle=d3d11"]


def _playwright_chromium() -> list[Path]:
    roots = [Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])] if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else []
    if sys.platform == "win32":
        roots.append(Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ms-playwright")
    else:
        roots.append(Path.home() / ".cache" / "ms-playwright")
    found: list[Path] = []
    for root in roots:
        pattern = "chromium-*/chrome-win*/chrome.exe" if sys.platform == "win32" else "chromium-*/chrome-linux*/chrome"
        found += [Path(p) for p in glob.glob(str(root / pattern))]
    return sorted(found, key=lambda p: p.parts[-3], reverse=True)  # chromium-1248 > chromium-1208


def find_browser() -> Optional[Path]:
    env = os.environ.get("PROJMAP_BROWSER")
    if env:
        return Path(env) if Path(env).is_file() else None
    candidates = _playwright_chromium()
    if sys.platform == "win32":
        pf = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for base in filter(None, pf):
            candidates += [Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
                           Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"]
    else:
        for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge"):
            hit = shutil.which(name)
            if hit:
                candidates.append(Path(hit))
    return next((c for c in candidates if c.is_file()), None)


_JOB = None  # handle do Job Object do Windows (vive enquanto o processo do mestre viver)


def _kill_with_parent_windows(pid: int) -> None:
    """Põe o navegador num Job Object com KILL_ON_JOB_CLOSE: se o mestre morrer (até por
    TerminateProcess, sem chance de rodar ``finally``), o Windows fecha o handle e mata o navegador."""
    global _JOB
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE
    if _JOB is None:
        job = k32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), "CreateJobObject")

        class _Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class _Io(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class _Extended(ctypes.Structure):
            _fields_ = [("Basic", _Basic), ("Io", _Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = _Extended()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
        _JOB = job
    handle = k32.OpenProcess(0x0100 | 0x0001, False, pid)  # PROCESS_SET_QUOTA | PROCESS_TERMINATE
    if not handle:
        raise OSError(ctypes.get_last_error(), "OpenProcess")
    try:
        if not k32.AssignProcessToJobObject(wintypes.HANDLE(_JOB), wintypes.HANDLE(handle)):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")
    finally:
        k32.CloseHandle(wintypes.HANDLE(handle))


def _linux_pdeathsig() -> None:  # pragma: no cover — roda no filho, só no Linux
    import ctypes
    import signal

    ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG


def dedicated(exe: Path) -> bool:
    """O executável é só nosso (pode receber preferência de GPU sem afetar o usuário)?"""
    return "ms-playwright" in exe.parts or bool(os.environ.get("PROJMAP_BROWSER"))


class MotionBrowser:
    """Um processo do navegador com uma página: a página host dos motions."""

    def __init__(self, url: str, exe: Optional[Path] = None, profile: Optional[Path] = None):
        self.url = url
        self.exe = exe or find_browser()
        self.profile = profile or (Path.home() / ".projmap" / "motion-browser")
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self.error = ""

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, timeout: float = 15.0) -> None:
        with self._lock:
            if self.running:
                return
            if self.exe is None:
                self.error = "nenhum Chromium/Chrome/Edge encontrado (defina PROJMAP_BROWSER)"
                raise RuntimeError(self.error)
            if sys.platform == "win32" and dedicated(self.exe):
                try:
                    from ..tools.gpu import set_preference

                    set_preference([self.exe])
                except OSError as exc:
                    log.warning("motions: não consegui marcar a GPU dedicada para %s (%s)", self.exe.name, exc)
            self.profile.mkdir(parents=True, exist_ok=True)
            port_file = self.profile / "DevToolsActivePort"
            port_file.unlink(missing_ok=True)
            flags = FLAGS + (WINDOWS_FLAGS if sys.platform == "win32" else [])
            w, h = VIEWPORT
            self._proc = subprocess.Popen(
                [str(self.exe), *flags, "--remote-debugging-port=0", "--remote-allow-origins=http://127.0.0.1",
                 f"--user-data-dir={self.profile}", f"--window-size={w},{h}", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                preexec_fn=_linux_pdeathsig if sys.platform.startswith("linux") else None)  # noqa: PLW1509
            if sys.platform == "win32":
                try:  # o navegador morre junto com o mestre (os processos filhos dele nascem no mesmo job)
                    _kill_with_parent_windows(self._proc.pid)
                except OSError as exc:
                    log.warning("motions: não consegui ligar o navegador à vida do mestre (%s)", exc)
            end = time.monotonic() + timeout
            while not (port_file.is_file() and port_file.read_text(encoding="utf-8").strip()):
                if self._proc.poll() is not None or time.monotonic() > end:
                    self.error = "o navegador dos motions não abriu"
                    self._kill()
                    raise RuntimeError(self.error)
                time.sleep(0.05)
            port = int(port_file.read_text(encoding="utf-8").split()[0])
            self._open_page(port, end)
            self.error = ""
            log.info("motions: %s rodando a página host (%s)", self.exe.name, self.url)

    def _targets(self, port: int) -> list[dict]:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as resp:  # noqa: S310
            return [t for t in json.load(resp) if t.get("type") == "page"]

    def _open_page(self, port: int, deadline: float) -> None:
        """Navega a aba inicial até a página host e confere que ela chegou lá (a primeira
        navegação às vezes cai numa aba que o navegador ainda estava criando)."""
        from websockets.sync.client import connect

        w, h = VIEWPORT
        for _attempt in range(3):
            page = None
            while page is None:
                try:
                    pages = self._targets(port)
                    page = pages[0] if pages else None
                except (OSError, ValueError):
                    pass
                if page is None:
                    if time.monotonic() > deadline:
                        raise RuntimeError("navegador dos motions sem página")
                    time.sleep(0.1)
            with connect(page["webSocketDebuggerUrl"], max_size=None, open_timeout=5) as ws:
                for i, (method, params) in enumerate([
                    ("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1,
                                                            "mobile": False}),
                    ("Emulation.setFocusEmulationEnabled", {"enabled": True}),
                    ("Page.navigate", {"url": self.url}),
                ], start=1):
                    ws.send(json.dumps({"id": i, "method": method, "params": params}))
                    while json.loads(ws.recv(timeout=5)).get("id") != i:
                        pass
            end = min(deadline, time.monotonic() + 5)
            while time.monotonic() < end:
                try:
                    if any(t.get("url", "").startswith(self.url) for t in self._targets(port)):
                        return
                except (OSError, ValueError):
                    pass
                time.sleep(0.1)
            log.warning("motions: a página host não abriu; tentando de novo")
        raise RuntimeError("o navegador dos motions não abriu a página host")

    def stop(self) -> None:
        with self._lock:
            self._kill()

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
