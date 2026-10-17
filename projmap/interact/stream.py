"""Transmissão da camada interativa por RTSP.

Publica num servidor RTSP (MediaMTX, rtsp-simple-server, …) o que a camada
interativa está mostrando — a cena ou o efeito do visual_frames —, para quem
quiser assistir de outra máquina::

    ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay rtsp://…/cam

Quem codifica é o **ffmpeg**: os quadros RGBA vão crus pelo ``stdin`` e saem em
H.264. Roda numa thread própria, a uma taxa fixa, então um servidor lento
segura só a transmissão, nunca a projeção.

Configuração **pelo ``.env``** (a URL leva a senha, que não pode ir para o git
nem para a linha de comando, onde apareceria na lista de processos)::

    PROJMAP_RTSP_URL=rtsp://usuario:senha@servidor:8554/caminho
    PROJMAP_RTSP_SIZE=1280x720      # opcional
    PROJMAP_RTSP_FPS=30             # opcional
    PROJMAP_RTSP_BITRATE=4M         # opcional
    PROJMAP_RTSP_TRANSPORT=tcp      # tcp (padrão) | udp

Sem ``PROJMAP_RTSP_URL`` nada sobe e o ProjMap funciona como antes.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

Fonte = Callable[[tuple[int, int]], "tuple[int, np.ndarray]"]

_SENHA = re.compile(r"((?:rtsps?|https?)://[^:/@\s]+:)([^@/\s]+)(@)", re.IGNORECASE)


def esconder_senha(url: str) -> str:
    """``rtsp://user:segredo@host/x`` → ``rtsp://user:***@host/x`` (para log)."""
    return _SENHA.sub(r"\1***\3", url or "")


def carregar_env(caminho: Optional[Path] = None) -> None:
    """Lê o ``.env`` da raiz do repositório para ``os.environ``.

    Sem dependência externa e **sem sobrescrever** o que já veio do ambiente.
    """
    caminho = caminho or Path(__file__).resolve().parents[2] / ".env"
    try:
        texto = caminho.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave = chave.strip()
        if chave.startswith("export "):
            chave = chave[7:].strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


class RtspPublisher:
    """Empurra quadros para um servidor RTSP através do ffmpeg."""

    def __init__(self, url: str, size: tuple[int, int] = (1280, 720), fps: float = 30.0,
                 bitrate: str = "4M", transport: str = "tcp", ffmpeg: Optional[str] = None):
        self.url = url
        self.size = size
        self.fps = max(1.0, float(fps))
        self.bitrate = bitrate
        self.transport = transport
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg")
        self.status = "parado"
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._fonte: Optional[Fonte] = None
        self.quadros = 0

    # ------------------------------------------------------------------ comando
    def comando(self) -> list[str]:
        w, h = self.size
        return [
            self.ffmpeg or "ffmpeg", "-hide_banner", "-loglevel", "error",
            # entrada: quadros crus pelo stdin, no ritmo em que chegam
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{self.fps:g}",
            "-use_wallclock_as_timestamps", "1", "-i", "-",
            # H.264 de baixa latência: sem lookahead, GOP curto para quem entra no meio
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-pix_fmt", "yuv420p", "-g", str(int(self.fps * 2)),
            "-b:v", self.bitrate, "-maxrate", self.bitrate, "-bufsize", self.bitrate,
            "-f", "rtsp", "-rtsp_transport", self.transport, self.url,
        ]

    # --------------------------------------------------------------------- vida
    def start(self, fonte: Fonte) -> "RtspPublisher":
        """``fonte(size)`` devolve ``(seq, quadro RGBA)`` — ex.: ``runtime.render``."""
        if self.ffmpeg is None:
            self.status = "ffmpeg não encontrado no PATH"
            log.error("transmissão RTSP: %s", self.status)
            return self
        self._fonte = fonte
        self._thread = threading.Thread(target=self._run, name="rtsp", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._encerrar()
        self.status = "parado"

    def _abrir(self) -> None:
        self._proc = subprocess.Popen(self.comando(), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.PIPE,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _encerrar(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
            proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()

    # --------------------------------------------------------------------- laço
    def _run(self) -> None:
        espera = 1.0
        while not self._stop.is_set():
            try:
                self._abrir()
                self.status = ""
                log.info("transmitindo em %s (%dx%d @ %g fps)", esconder_senha(self.url),
                         self.size[0], self.size[1], self.fps)
                self._bombear()
            except Exception as exc:  # noqa: BLE001 — a rede cair não derruba o show
                self.status = f"transmissão indisponível: {exc}"
                log.warning("%s", self.status)
            self._encerrar()
            if self._stop.wait(espera):  # reconecta com recuo progressivo
                break
            espera = min(espera * 2, 15.0)

    def _motivo(self) -> str:
        """A última linha do stderr do ffmpeg — é onde está o motivo de verdade
        (ex.: ``401 Unauthorized`` quando a credencial só tem leitura). Sem
        isso, a escrita num cano fechado só diria "Broken pipe"."""
        proc = self._proc
        if proc is None:
            return ""
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        texto = ""
        if proc.stderr is not None:
            try:
                texto = (proc.stderr.read() or b"").decode("utf-8", "replace")
            except (OSError, ValueError):
                texto = ""
        linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
        for ln in linhas:  # a mais informativa costuma ser a do código HTTP/RTSP
            if "Unauthorized" in ln or "failed" in ln or "Error" in ln:
                return esconder_senha(ln)
        return esconder_senha(linhas[-1]) if linhas else ""

    def _bombear(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdin is not None
        periodo = 1.0 / self.fps
        buf = np.empty((self.size[1], self.size[0], 3), np.uint8)
        proximo = time.perf_counter()
        while not self._stop.is_set():
            if proc.poll() is not None:
                raise RuntimeError(self._motivo() or f"ffmpeg saiu com {proc.returncode}")
            seq, img = self._fonte(self.size)
            if (img.shape[1], img.shape[0]) != self.size:
                img = cv2.resize(img, self.size, interpolation=cv2.INTER_LINEAR)
            # RGBA (o que o motor entrega) -> BGR24, que é o que o ffmpeg espera
            cv2.cvtColor(img, cv2.COLOR_RGBA2BGR if img.shape[2] == 4 else cv2.COLOR_RGB2BGR, dst=buf)
            try:
                proc.stdin.write(buf.tobytes())
            except (BrokenPipeError, OSError) as exc:
                raise RuntimeError(self._motivo() or str(exc)) from None
            self.quadros += 1
            proximo += periodo
            atraso = proximo - time.perf_counter()
            if atraso < -periodo:  # ficamos para trás: não tenta recuperar o tempo perdido
                proximo = time.perf_counter()
            elif atraso > 0 and self._stop.wait(atraso):
                break


def publisher_from_env() -> Optional[RtspPublisher]:
    """Monta o publicador a partir do ``.env``; ``None`` se não estiver configurado."""
    carregar_env()
    url = (os.environ.get("PROJMAP_RTSP_URL") or "").strip()
    if not url:
        return None
    from .cameras import parse_size

    try:
        size = parse_size(os.environ.get("PROJMAP_RTSP_SIZE", "1280x720"))
    except ValueError as exc:
        log.error("PROJMAP_RTSP_SIZE: %s", exc)
        size = (1280, 720)
    try:
        fps = float(os.environ.get("PROJMAP_RTSP_FPS", "30"))
    except ValueError:
        fps = 30.0
    return RtspPublisher(url, size, fps,
                         bitrate=os.environ.get("PROJMAP_RTSP_BITRATE", "4M"),
                         transport=os.environ.get("PROJMAP_RTSP_TRANSPORT", "tcp"))
