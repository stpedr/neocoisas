"""Ponte renderer ↔ navegador dos motions.

O renderer abre uma sessão por fonte ``motion`` (``open_session``); a página
host (``ui/app/motion-host``, rodando no :mod:`browser`) liga no WebSocket
``/ws/motion-host`` do mestre, recebe a lista de sessões, cria um iframe
sandbox por motion e devolve os pixels de cada um. O hub guarda só o quadro
mais novo de cada sessão — o render nunca espera o navegador.

Protocolo binário (as duas direções): ``uint32 LE`` com o tamanho do cabeçalho
JSON, o cabeçalho, e o corpo.

- navegador → mestre: ``{"sid", "w", "h", "fmt"}`` + JPEG (``fmt="jpeg"``, o padrão) ou RGBA cru;
- mestre → navegador: ``{"kind": "video", "device", "w", "h"}`` + JPEG.

Texto (mestre → navegador): ``{"type": "sessions", ...}`` quando a lista muda e
``{"type": "audio", ...}`` ~60×/s com os níveis do barramento de áudio.
"""

from __future__ import annotations

import json
import logging
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

DEFAULT_SIZE = (1280, 720)
MAX_SIDE = 1920
HOST_PATH = "/motion-host/"
HOST_TIMEOUT_S = 20.0  # navegador aberto e a página host sem conectar: reinicia


def pack(header: dict[str, Any], body: bytes) -> bytes:
    raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(raw)) + raw + body


def unpack(data: bytes) -> tuple[dict[str, Any], memoryview]:
    if len(data) < 4:
        raise ValueError("pacote curto")
    (n,) = struct.unpack_from("<I", data, 0)
    if n > 4096 or 4 + n > len(data):
        raise ValueError("cabeçalho inválido")
    header = json.loads(bytes(data[4:4 + n]).decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("cabeçalho inválido")
    return header, memoryview(data)[4 + n:]


@dataclass
class MotionSession:
    sid: str
    key: str
    media: str  # sha256
    size: tuple[int, int]
    params: dict[str, Any]
    mode: Optional[str]
    device: Optional[str]
    refs: int = 0
    frames: int = 0
    frame: tuple[int, np.ndarray] = field(default_factory=lambda: (0, np.zeros((9, 16, 4), np.uint8)))
    last_at: float = 0.0

    def describe(self) -> dict[str, Any]:
        return {"sid": self.sid, "media": self.media, "w": self.size[0], "h": self.size[1],
                "params": self.params, "mode": self.mode, "device": self.device}


BrowserFactory = Callable[[str], Any]


def _default_browser(url: str) -> Any:
    from .browser import MotionBrowser

    return MotionBrowser(url)


class MotionHub:
    def __init__(self, browser_factory: BrowserFactory = _default_browser, idle_stop_s: float = 10.0):
        self._lock = threading.Lock()
        self._sessions: dict[str, MotionSession] = {}
        self._by_key: dict[str, str] = {}
        self._seq = 0
        self.version = 0
        self.base_url: Optional[str] = None
        self._browser_factory = browser_factory
        self._browser: Any = None
        self._idle_stop_s = idle_stop_s
        self._empty_since: Optional[float] = None
        self._watch: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.host_connected = False
        self._started_at: Optional[float] = None
        self.host_stats: dict[str, Any] = {}
        self.error = ""

    # ------------------------------------------------------------ configuração
    def configure(self, base_url: str) -> None:
        """URL do mestre vista pelo navegador local (ex.: ``http://127.0.0.1:8100``)."""
        self.base_url = base_url.rstrip("/")
        if self._watch is None:
            self._watch = threading.Thread(target=self._watchdog, name="motion-hub", daemon=True)
            self._watch.start()

    def shutdown(self) -> None:
        self._stop.set()
        browser, self._browser = self._browser, None
        if browser is not None:
            browser.stop()

    # ---------------------------------------------------------------- sessões
    def open_session(self, media: str, size: tuple[int, int] = DEFAULT_SIZE, params: Optional[dict[str, Any]] = None,
                     mode: Optional[str] = None, device: Optional[str] = None) -> MotionSession:
        w, h = (max(16, min(int(v), MAX_SIDE)) for v in size)
        params = dict(params or {})
        key = json.dumps([media, w, h, params, mode, device], sort_keys=True)
        with self._lock:
            sid = self._by_key.get(key)
            if sid is None:
                self._seq += 1
                sid = f"m{self._seq}"
                self._sessions[sid] = MotionSession(sid, key, media, (w, h), params, mode, device)
                self._by_key[key] = sid
                self.version += 1
            sess = self._sessions[sid]
            sess.refs += 1
            self._empty_since = None
        return sess

    def release(self, sess: MotionSession) -> None:
        with self._lock:
            sess.refs -= 1
            if sess.refs > 0 or self._sessions.get(sess.sid) is not sess:
                return
            del self._sessions[sess.sid]
            self._by_key.pop(sess.key, None)
            self.version += 1
            if not self._sessions:
                self._empty_since = time.monotonic()

    def sessions(self) -> tuple[int, list[dict[str, Any]]]:
        with self._lock:
            return self.version, [s.describe() for s in self._sessions.values()]

    def devices(self) -> set[str]:
        with self._lock:
            return {s.device for s in self._sessions.values() if s.device}

    def latest(self, sess: MotionSession) -> tuple[int, np.ndarray]:
        with self._lock:
            return sess.frame

    def put_frame(self, data: bytes) -> None:
        """Quadro RGBA vindo do navegador (pacote :func:`pack`)."""
        header, body = unpack(data)
        sid, w, h = header.get("sid"), int(header.get("w", 0)), int(header.get("h", 0))
        if not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE):
            raise ValueError("quadro com tamanho inválido")
        if header.get("fmt") == "jpeg":  # o padrão da página host: ~200 KB em vez de 3,7 MB por quadro
            bgr = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
            if bgr is None or bgr.shape[:2] != (h, w):
                raise ValueError("JPEG do motion ilegível")
            rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
        else:
            if len(body) != w * h * 4:
                raise ValueError("quadro com tamanho inválido")
            rgba = np.frombuffer(body, np.uint8).reshape(h, w, 4)
            rgba = rgba[::-1].copy() if header.get("flip_y") else rgba.copy()
        with self._lock:
            sess = self._sessions.get(str(sid))
            if sess is None:
                return
            sess.frames += 1
            sess.frame = (sess.frames, rgba)
            sess.last_at = time.monotonic()

    def note_host_stats(self, text: str) -> None:
        """Estatísticas que a página host manda a cada 2 s (fps capturado, ms por quadro)."""
        try:
            data = json.loads(text)
        except ValueError:
            return
        if isinstance(data, dict) and data.get("type") == "stats":
            self.host_stats = {k: v for k, v in data.items() if k in ("fps", "ms", "buffered") and isinstance(v, (int, float))}

    def status(self) -> dict[str, Any]:
        with self._lock:
            sessions = [{**s.describe(), "frames": s.frames, "refs": s.refs,
                         "age_s": round(time.monotonic() - s.last_at, 2) if s.last_at else None}
                        for s in self._sessions.values()]
        browser = self._browser
        return {"host_connected": self.host_connected, "host_stats": self.host_stats,
                "browser": bool(browser and browser.running),
                "browser_exe": str(getattr(browser, "exe", "") or ""), "error": self.error or getattr(browser, "error", ""),
                "sessions": sessions}

    # ------------------------------------------------------------- navegador
    def _watchdog(self) -> None:
        """Liga o navegador quando há sessão, religa se cair, desliga ocioso."""
        backoff = 1.0
        while not self._stop.wait(0.5):
            with self._lock:
                has, empty_since = bool(self._sessions), self._empty_since
            browser = self._browser
            if browser is not None and browser.running and not self.host_connected and has:
                waiting = time.monotonic() - (self._started_at or time.monotonic())
                if waiting > HOST_TIMEOUT_S:  # navegador vivo mas a página não conectou: reinicia
                    log.warning("motions: página host não conectou em %.0fs; reiniciando o navegador", waiting)
                    browser.stop()
            try:
                if has and self.base_url and (browser is None or not browser.running):
                    if browser is None:
                        self._browser = browser = self._browser_factory(self.base_url + HOST_PATH)
                    browser.start()
                    self._started_at = time.monotonic()
                    self.error, backoff = "", 1.0
                elif not has and browser is not None and empty_since and \
                        time.monotonic() - empty_since > self._idle_stop_s:
                    browser.stop()
                    self._browser = None
                    log.info("motions: navegador desligado (nenhum motion em uso)")
            except Exception as exc:  # noqa: BLE001 — navegador ausente/quebrado: superfície fica escura, show segue
                self.error = str(exc)
                log.error("motions: %s; tentando de novo em %.0fs", exc, backoff)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30.0)


_HUB: Optional[MotionHub] = None
_HUB_LOCK = threading.Lock()


def hub() -> MotionHub:
    global _HUB
    with _HUB_LOCK:
        if _HUB is None:
            _HUB = MotionHub()
        return _HUB
