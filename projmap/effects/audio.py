"""Música → cores — tradução de ``AnalisadorAudio.cpp`` do visual_frames.

No Linux o original grava o monitor do PulseAudio. No Windows a captura é o
*loopback* WASAPI da saída padrão (o que está tocando no PC), via ``soundcard``.
FFT de 2048 com salto de 1024, bandas grave/médio/agudo com ganho automático e
batida de Patin (energia do grave > C × média do último ~1 s).
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import config as C

log = logging.getLogger(__name__)

ANALISES_POR_SEGUNDO = C.AUDIO_TAXA / C.AUDIO_SALTO
HISTORICO_BATIDA = round(ANALISES_POR_SEGUNDO)


@dataclass
class AudioLevels:
    grave: float = 0.0
    medio: float = 0.0
    agudo: float = 0.0
    geral: float = 0.0
    batidas: int = 0  # contador; mudou = houve batida nova
    ativo: bool = False


class _Band:
    """Ganho automático + suavização (sobe rápido, desce devagar)."""

    def __init__(self) -> None:
        self.peak = 1e-9
        self.level = 0.0

    def update(self, energy: float, decay: float) -> float:
        self.peak = max(energy, self.peak * decay, 1e-9)
        target = math.sqrt(energy / self.peak)
        self.level += (0.6 if target > self.level else 0.12) * (target - self.level)
        return self.level


def _bin(hz: float) -> int:
    return int(np.clip(round(hz * C.AUDIO_JANELA_FFT / C.AUDIO_TAXA), 1, C.AUDIO_JANELA_FFT // 2))


class AudioAnalyzer:
    """Analisa blocos de ``AUDIO_SALTO`` amostras mono (``feed``); a thread de
    captura (``start``) alimenta pelo loopback do Windows."""

    def __init__(self, device: str = "loopback") -> None:
        # "loopback" = o que toca no PC; "mic" = microfone padrão; outro = parte do nome do dispositivo
        self.device = device
        self.device_label = ""
        n = C.AUDIO_JANELA_FFT
        self._window = np.zeros(n, np.float32)
        self._hann = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / (n - 1))).astype(np.float32)
        self._g_end, self._m_end, self._a_end = _bin(C.AUDIO_GRAVE_MAX_HZ), _bin(C.AUDIO_MEDIO_MAX_HZ), _bin(C.AUDIO_AGUDO_MAX_HZ)
        self._decay = 0.5 ** (1.0 / (C.AUDIO_MEIA_VIDA_PICO_S * ANALISES_POR_SEGUNDO))
        self._refractory = int(C.BATIDA_REFRATARIO_S * ANALISES_POR_SEGUNDO)
        self._bands = [_Band() for _ in range(4)]
        self._hist: deque[float] = deque()
        self._since = self._refractory
        self._lock = threading.Lock()
        self.levels = AudioLevels()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def feed(self, block: np.ndarray) -> AudioLevels:
        block = np.asarray(block, np.float32).ravel()
        self._window = np.concatenate([self._window[len(block):], block])
        rms = float(np.sqrt(np.mean(block * block))) if len(block) else 0.0
        g, m, a, t = self._bands
        if rms < C.AUDIO_SILENCIO_RMS:
            lv = AudioLevels(g.update(0, self._decay), m.update(0, self._decay), a.update(0, self._decay),
                             t.update(0, self._decay), self.levels.batidas, False)
            self._hist.clear()
        else:
            spec = np.fft.rfft(self._window * self._hann)
            power = (spec.real ** 2 + spec.imag ** 2).astype(np.float64)

            def band(lo: int, hi: int) -> float:
                return float(power[lo:hi].sum() / max(1, hi - lo))

            e_grave = band(1, self._g_end)
            lv = AudioLevels(g.update(e_grave, self._decay), m.update(band(self._g_end, self._m_end), self._decay),
                             a.update(band(self._m_end, self._a_end), self._decay), t.update(rms * rms, self._decay),
                             self.levels.batidas, True)
            self._since += 1
            if len(self._hist) >= HISTORICO_BATIDA:
                hist = np.array(self._hist)
                mean = hist.mean()
                cv = hist.std() / max(mean, 1e-12)
                c = float(np.clip(C.BATIDA_C_MAX - 0.3 * cv, C.BATIDA_C_MIN, C.BATIDA_C_MAX))
                if e_grave > c * mean and self._since >= self._refractory:
                    lv.batidas += 1
                    self._since = 0
                self._hist.popleft()
            self._hist.append(e_grave)
        with self._lock:
            self.levels = lv
        return lv

    def get(self) -> AudioLevels:
        with self._lock:
            return AudioLevels(**self.levels.__dict__)

    # ------------------------------------------------------------- captura
    def start(self) -> "AudioAnalyzer":
        self._thread = threading.Thread(target=self._run, name="vf-audio", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        import warnings

        try:
            import soundcard as sc

            # "data discontinuity" é só um bloco atrasado do WASAPI/PulseAudio: inofensivo e muito repetitivo.
            warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)
        except Exception as exc:  # noqa: BLE001
            log.warning("áudio indisponível (instale 'soundcard'): %s", exc)
            return
        while not self._stop.is_set():
            try:
                mic, label = _pick_capture_device(sc, self.device)
                self.device_label = label
                log.info("áudio: capturando '%s' (%s)", label, self.device)
                with mic.recorder(samplerate=C.AUDIO_TAXA, channels=1, blocksize=C.AUDIO_SALTO) as rec:
                    while not self._stop.is_set():
                        data = rec.record(numframes=C.AUDIO_SALTO)
                        self.feed(data.mean(axis=1) if data.ndim > 1 else data)
            except Exception as exc:  # noqa: BLE001 — troca de dispositivo, fone desconectado…
                log.warning("áudio: %s; tentando de novo", exc)
                with self._lock:
                    self.levels.ativo = False
                self._stop.wait(2.0)


def _pick_capture_device(sc, device: str = "loopback"):  # noqa: ANN001, ANN202
    """Escolhe o dispositivo de captura de áudio.

    ``loopback``: loopback WASAPI no Windows ou fonte '.monitor' do
    PulseAudio/PipeWire no Linux (com fallback para microfone). ``mic``: o
    microfone padrão. Outro texto: o primeiro dispositivo cujo nome o contém."""
    want = (device or "loopback").strip().lower()
    if want == "mic":
        mic = sc.default_microphone()
        return mic, getattr(mic, "name", "microfone padrão")
    if want != "loopback":
        for mic in sc.all_microphones(include_loopback=True):
            if want in getattr(mic, "name", "").lower():
                return mic, getattr(mic, "name", want)
        raise RuntimeError(f"dispositivo de áudio '{device}' não encontrado")
    speaker = sc.default_speaker()
    for query in (getattr(speaker, "id", None), getattr(speaker, "name", None)):
        if not query:
            continue
        try:
            mic = sc.get_microphone(query, include_loopback=True)
            if mic is not None:
                return mic, getattr(speaker, "name", str(query))
        except Exception:  # noqa: BLE001
            continue
    for mic in sc.all_microphones(include_loopback=True):
        name_l = getattr(mic, "name", "").lower()
        id_l = str(getattr(mic, "id", "")).lower()
        if getattr(mic, "isloopback", False) or "monitor" in name_l or ".monitor" in id_l:
            return mic, getattr(mic, "name", "monitor")
    mic = sc.default_microphone()
    return mic, getattr(mic, "name", "microfone padrão")

