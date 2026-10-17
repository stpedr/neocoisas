"""Entrada de áudio do show: um barramento único que alimenta os efeitos ``fx``.

Reaproveita o analisador do ``effects/audio.py`` (FFT, bandas com ganho
automático e batida de Patin) e só acrescenta:

- **escolha do dispositivo** (``project.audio.device``): ``loopback`` (o que
  toca no PC), ``mic`` ou parte do nome; trocar reinicia só a captura;
- **nomes em inglês** das bandas, iguais aos de ``AudioFx.band``
  (``bass/mid/high/level``);
- **envelope de batida** (``beat``): vai a 1 em cada batida e cai com meia-vida
  de :data:`BEAT_HALF_LIFE_S` — é o que faz o ``strobe`` piscar no tempo.

A captura só liga quando alguma superfície tem efeito (``ensure``): show sem
efeito não abre o dispositivo de áudio.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional, Protocol

import numpy as np

from ..core.project import AudioInput

log = logging.getLogger(__name__)

BEAT_HALF_LIFE_S = 0.12


class _Analyzer(Protocol):
    device: str
    device_label: str

    def start(self) -> Any: ...

    def stop(self) -> None: ...

    def get(self) -> Any: ...


def _default_factory(device: str) -> _Analyzer:
    from ..effects.audio import AudioAnalyzer

    return AudioAnalyzer(device)


class AudioBus:
    def __init__(self, factory: Callable[[str], _Analyzer] = _default_factory,
                 clock: Callable[[], float] = time.monotonic):
        self._factory = factory
        self._clock = clock
        self._lock = threading.Lock()
        self._analyzer: Optional[_Analyzer] = None
        self._spec = AudioInput()
        self._beats = 0
        self._beat_at: Optional[float] = None

    @property
    def running(self) -> bool:
        return self._analyzer is not None

    def ensure(self, spec: AudioInput) -> None:
        """Liga a captura (ou troca de dispositivo) conforme ``spec``."""
        with self._lock:
            self._spec = spec
            if self._analyzer is not None and self._analyzer.device == spec.device:
                return
            old, self._analyzer = self._analyzer, None
        if old is not None:  # ``ensure`` roda na thread do render: o join da captura antiga não pode travar a parede
            threading.Thread(target=old.stop, name="audio-stop", daemon=True).start()
        analyzer = self._factory(spec.device)
        analyzer.start()
        with self._lock:
            self._analyzer = analyzer
            self._beats, self._beat_at = 0, None
        log.info("entrada de áudio: %s", spec.device)

    def stop(self) -> None:
        with self._lock:
            old, self._analyzer = self._analyzer, None
        if old is not None:
            old.stop()

    def levels(self) -> dict[str, float]:
        """Níveis 0..1 por banda (já com o ganho) + ``beat`` (envelope)."""
        with self._lock:
            analyzer, gain = self._analyzer, self._spec.gain
        if analyzer is None:
            return dict.fromkeys(("bass", "mid", "high", "level", "beat"), 0.0)
        lv = analyzer.get()
        now = self._clock()
        with self._lock:
            if lv.batidas != self._beats:
                self._beats, self._beat_at = lv.batidas, now
            beat_at = self._beat_at
        beat = 0.0 if beat_at is None else 0.5 ** ((now - beat_at) / BEAT_HALF_LIFE_S)

        def g(v: float) -> float:
            return float(np.clip(v * gain, 0.0, 1.0))

        return {"bass": g(lv.grave), "mid": g(lv.medio), "high": g(lv.agudo), "level": g(lv.geral),
                "beat": float(np.clip(beat, 0.0, 1.0))}

    def status(self) -> dict[str, Any]:
        with self._lock:
            analyzer, spec, beats = self._analyzer, self._spec, self._beats
        active = bool(analyzer is not None and analyzer.get().ativo)
        return {"running": analyzer is not None, "active": active, "device": spec.device,
                "device_label": getattr(analyzer, "device_label", "") if analyzer else "",
                "gain": spec.gain, "beats": beats, "levels": self.levels()}


def list_audio_devices() -> list[dict[str, Any]]:
    """Dispositivos de captura (inclui loopbacks). Vazio se ``soundcard`` faltar."""
    try:
        import soundcard as sc
    except Exception as exc:  # noqa: BLE001 — lib nativa ausente/quebrada
        log.warning("áudio indisponível (instale 'soundcard'): %s", exc)
        return []
    out = []
    try:
        for mic in sc.all_microphones(include_loopback=True):
            out.append({"name": getattr(mic, "name", "?"), "loopback": bool(getattr(mic, "isloopback", False))})
    except Exception as exc:  # noqa: BLE001
        log.warning("não consegui listar o áudio: %s", exc)
    return out


_BUS: Optional[AudioBus] = None
_BUS_LOCK = threading.Lock()


def bus() -> AudioBus:
    """O barramento do processo (renderer e API leem o mesmo)."""
    global _BUS
    with _BUS_LOCK:
        if _BUS is None:
            _BUS = AudioBus()
        return _BUS
