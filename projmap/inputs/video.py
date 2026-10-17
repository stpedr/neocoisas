"""Entrada de vídeo ao vivo (webcam, placa de captura HDMI) como fonte de superfície.

- **Uma captura por dispositivo.** No Windows uma câmera só abre uma vez; duas
  superfícies com a mesma entrada dividem a mesma captura (contagem de
  referências em :func:`open_capture`).
- **O render nunca espera.** Uma thread lê a câmera e guarda só o quadro mais
  novo; ``frame_at`` devolve o último (a chave muda a cada quadro novo, então o
  renderer só reenvia a textura quando chega imagem nova). Antes do primeiro
  quadro a fonte mostra preto.
- **Câmera que cai volta sozinha.** Falha de leitura fecha e reabre com recuo,
  e o erro fica em :meth:`Capture.status` (a API mostra).

A escolha do dispositivo (``auto`` / índice / parte do nome) é a mesma do
sensor de webcam (``interact/cameras.py``).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

PLACEHOLDER = np.zeros((9, 16, 4), np.uint8)
PLACEHOLDER[..., 3] = 255

Opener = Callable[[str], tuple[Any, str]]


def _default_opener(device: str) -> tuple[Any, str]:
    """Abre a câmera escolhida e devolve ``(cap, nome)``."""
    from ..interact.cameras import choose_camera, list_cameras, open_camera

    cams = list_cameras()
    cam = choose_camera(cams, device)
    if cam is None:
        raise RuntimeError(f"entrada de vídeo '{device}' não encontrada")
    cap, got = open_camera(cam.index)
    log.info("entrada de vídeo: %s (%dx%d @ %.0f fps)", cam.name, got[0], got[1], got[2])
    return cap, cam.name


class Capture:
    """Thread de leitura de um dispositivo; compartilhada pelas fontes."""

    def __init__(self, device: str, opener: Opener = _default_opener):
        self.device = device
        self._opener = opener
        self._lock = threading.Lock()
        self._frame: tuple[int, np.ndarray] = (0, PLACEHOLDER)
        self._name = ""
        self._error = ""
        self._frames = 0
        self._started = time.monotonic()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"capture-{device}", daemon=True)
        self.refs = 0

    def start(self) -> "Capture":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=3)

    def latest(self) -> tuple[int, np.ndarray]:
        with self._lock:
            return self._frame

    def status(self) -> dict[str, Any]:
        with self._lock:
            key, img = self._frame
            elapsed = max(time.monotonic() - self._started, 1e-6)
            return {"device": self.device, "name": self._name, "frames": self._frames,
                    "fps": round(self._frames / elapsed, 1), "size": [int(img.shape[1]), int(img.shape[0])],
                    "error": self._error, "refs": self.refs}

    def _run(self) -> None:
        backoff = 0.5
        while not self._stop.is_set():
            cap = None
            try:
                cap, name = self._opener(self.device)
                with self._lock:
                    self._name, self._error = name, ""
                backoff = 0.5
                misses = 0
                while not self._stop.is_set():
                    ok, bgr = cap.read()
                    if not ok or bgr is None:
                        misses += 1
                        if misses > 30:
                            raise RuntimeError("a câmera parou de mandar quadros")
                        self._stop.wait(0.01)
                        continue
                    misses = 0
                    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
                    with self._lock:
                        self._frames += 1
                        self._frame = (self._frames, rgba)
            except Exception as exc:  # noqa: BLE001 — dispositivo some/ocupado: tenta de novo
                log.warning("entrada de vídeo '%s': %s; tentando de novo em %.1fs", self.device, exc, backoff)
                with self._lock:
                    self._error = str(exc)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 5.0)
            finally:
                if cap is not None:
                    cap.release()


class CaptureSource:
    """``FrameSource`` de uma entrada de vídeo ao vivo."""

    def __init__(self, capture: Capture, release: Callable[[Capture], None]):
        self._capture = capture
        self._release = release
        self._closed = False

    @property
    def size(self) -> tuple[int, int]:
        img = self._capture.latest()[1]
        return int(img.shape[1]), int(img.shape[0])

    @property
    def duration(self) -> Optional[float]:
        return None

    def frame_at(self, t: float) -> tuple[int, np.ndarray]:
        return self._capture.latest()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._release(self._capture)


_CAPTURES: dict[str, Capture] = {}
_LOCK = threading.Lock()


def _key(device: Optional[str]) -> str:
    return (device or "auto").strip().lower() or "auto"


def open_capture(device: Optional[str], opener: Optional[Opener] = None) -> CaptureSource:
    """Fonte da entrada ``device``; reaproveita a captura já aberta."""
    key = _key(device)
    with _LOCK:
        cap = _CAPTURES.get(key)
        if cap is None:
            cap = _CAPTURES[key] = Capture(key, opener or _default_opener).start()
        cap.refs += 1
    return CaptureSource(cap, _release)


def _release(cap: Capture) -> None:
    with _LOCK:
        cap.refs -= 1
        if cap.refs > 0 or _CAPTURES.get(cap.device) is not cap:
            return
        del _CAPTURES[cap.device]
    # O release vem do sync do renderer (thread do GL): fecha a câmera em segundo plano.
    threading.Thread(target=cap.stop, name="capture-stop", daemon=True).start()


def active_captures() -> list[dict[str, Any]]:
    with _LOCK:
        caps = list(_CAPTURES.values())
    return [c.status() for c in caps]


def list_video_devices() -> list[dict[str, Any]]:
    from ..interact.cameras import choose_camera, list_cameras

    cams = list_cameras()
    auto = choose_camera(cams, "auto")
    return [{"index": c.index, "name": c.name, "virtual": c.virtual, "auto": bool(auto and auto.index == c.index)}
            for c in cams]
