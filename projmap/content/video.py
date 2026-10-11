"""Vídeo via PyAV (FFmpeg), decodificado numa thread à frente do relógio.

Desenho:

- Uma thread decodifica **sequencialmente** para uma fila curta (``max_queue``
  frames já em RGBA). A thread de render nunca espera o decoder: ``frame_at``
  só consome o que já está pronto e, se o decoder atrasar, repete o último frame
  (melhor um frame repetido que um engasgo na projeção).
- O tempo manda. ``frame_at(t)`` descarta frames cujo pts já passou e devolve o
  mais recente com ``pts ≤ t`` (mesma regra do GIF). Voltar no tempo (loop ou seek) ou pular muito à
  frente faz a thread reposicionar o arquivo (seek no keyframe anterior +
  descarte até o alvo).
- O Raspberry Pi 5 não tem decoder H.264 por hardware (BLUEPRINT U2): a
  decodificação é por software aqui. O perfil de transcodificação e o modo
  *baked* (F2) existem para caber nesse orçamento.
"""

from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import av
import numpy as np

from .base import loop_time

# Pular para frente mais que isso ⇒ seek em vez de decodificar tudo no caminho.
SEEK_AHEAD_S = 1.5
# Folga para pts como 0.30000000004 contarem como 0.3.
PTS_EPS = 1e-4


@dataclass
class _Frame:
    serial: int
    pts: float
    rgba: np.ndarray


class VideoSource:
    def __init__(self, path: Path, loop: bool = True, max_queue: int = 6, max_dim: int = 3840):
        self.path = Path(path)
        self.loop = loop
        self.max_queue = max(2, max_queue)

        with av.open(str(self.path)) as probe:
            if not probe.streams.video:
                raise ValueError(f"arquivo sem trilha de vídeo: {self.path.name}")
            stream = probe.streams.video[0]
            rate = stream.average_rate or stream.guessed_rate or 30
            self.fps = float(rate)
            w, h = stream.codec_context.width, stream.codec_context.height
            duration = None
            if stream.duration is not None and stream.time_base is not None:
                duration = float(stream.duration * stream.time_base)
            elif probe.duration is not None:
                duration = probe.duration / av.time_base
            elif stream.frames:
                duration = stream.frames / self.fps
        scale = min(1.0, max_dim / max(w, h))
        # Dimensões pares: alguns conversores de formato exigem.
        self._out_w = max(2, int(w * scale) // 2 * 2)
        self._out_h = max(2, int(h * scale) // 2 * 2)
        self._duration = duration if duration and duration > 0 else None

        self._queue: collections.deque[_Frame] = collections.deque()
        self._cond = threading.Condition()
        self._shown: Optional[_Frame] = None
        self._seek_to: Optional[float] = 0.0
        self._stop = False
        self._eof = False
        self._serial = 0
        self._error: Optional[BaseException] = None
        self._thread = threading.Thread(target=self._run, name=f"video:{self.path.name}", daemon=True)
        self._thread.start()

    # ----------------------------------------------------------------- contrato
    @property
    def size(self) -> tuple[int, int]:
        return self._out_w, self._out_h

    @property
    def duration(self) -> Optional[float]:
        return self._duration

    def frame_at(self, t: float, block_timeout: float = 0.0) -> tuple[int, np.ndarray]:
        """Frame para o instante ``t``.

        ``block_timeout > 0`` espera o decoder alcançar ``t`` (usado em testes e no
        render offline do modo *baked*); no laço de render fica 0.
        """
        local = loop_time(t, self._duration, self.loop)
        half = 0.5 / self.fps
        # Regra de exibição igual à do GIF: o frame vale de pts até o próximo pts
        # (piso, com folga de arredondamento). Todos os nós aplicam a mesma regra,
        # então o mesmo t vira o mesmo frame em todos.
        with self._cond:
            shown = self._shown
            backwards = shown is not None and local + half < shown.pts
            head = self._queue[0].pts if self._queue else (shown.pts if shown else 0.0)
            far_ahead = local - head > SEEK_AHEAD_S
            if backwards or far_ahead:
                self._request_seek(local)
                shown = None
                if self._shown is not None:
                    # Mantém a última imagem na tela até o decoder reposicionar, mas
                    # "move" seu tempo para o alvo — senão o próximo frame_at veria o
                    # tempo voltando de novo e pediria seek em laço.
                    self._shown = _Frame(self._shown.serial, local - half, self._shown.rgba)

            deadline = None
            while True:
                while self._queue and self._queue[0].pts <= local + PTS_EPS:
                    shown = self._queue.popleft()
                    self._cond.notify_all()
                caught_up = bool(self._queue) or self._eof
                if caught_up or block_timeout <= 0 or self._error is not None:
                    break
                now = time.monotonic()
                deadline = deadline or now + block_timeout
                if now >= deadline:
                    break
                self._cond.wait(timeout=min(0.05, deadline - now))

            if shown is not None:
                self._shown = shown
            if self._shown is None:
                if self._error is not None:
                    raise RuntimeError(f"falha ao decodificar {self.path.name}: {self._error}")
                blank = np.zeros((self._out_h, self._out_w, 4), dtype=np.uint8)
                return -1, blank
            return self._shown.serial, self._shown.rgba

    def close(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()
        self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------ decoder
    def _request_seek(self, target: float) -> None:
        self._seek_to = max(0.0, target)
        self._queue.clear()
        self._eof = False
        self._cond.notify_all()

    def _run(self) -> None:
        try:
            with av.open(str(self.path)) as container:
                stream = container.streams.video[0]
                stream.thread_type = "AUTO"
                tb = float(stream.time_base) if stream.time_base else 1.0 / self.fps
                frames = None
                skip_until = 0.0
                count = 0
                while True:
                    with self._cond:
                        if self._stop:
                            return
                        seek = self._seek_to
                        self._seek_to = None
                    if seek is not None:
                        offset = int(seek / tb) if stream.time_base else 0
                        container.seek(offset, stream=stream, backward=True, any_frame=False)
                        frames = container.decode(stream)
                        # Mantém o frame que *contém* o alvo (pts > alvo − 1 frame).
                        skip_until = seek - 1.0 / self.fps + PTS_EPS
                        count = 0
                    try:
                        frame = next(frames)  # type: ignore[arg-type]
                    except StopIteration:
                        with self._cond:
                            self._eof = True
                            self._cond.notify_all()
                            # Em loop, o consumidor pede seek(0) ao voltar no tempo;
                            # até lá, dormimos.
                            while self._seek_to is None and not self._stop:
                                self._cond.wait()
                        continue
                    pts = float(frame.pts * tb) if frame.pts is not None else count / self.fps
                    count += 1
                    if pts < skip_until:
                        continue
                    rgba = frame.to_ndarray(format="rgba", width=self._out_w, height=self._out_h)
                    with self._cond:
                        while (
                            len(self._queue) >= self.max_queue and self._seek_to is None and not self._stop
                        ):
                            self._cond.wait()
                        if self._stop:
                            return
                        if self._seek_to is not None:
                            continue  # frame obsoleto: houve seek enquanto esperávamos
                        self._serial += 1
                        self._queue.append(_Frame(self._serial, pts, np.ascontiguousarray(rgba)))
                        self._cond.notify_all()
        except BaseException as exc:  # noqa: BLE001 — repassado ao consumidor
            with self._cond:
                self._error = exc
                self._eof = True
                self._cond.notify_all()
