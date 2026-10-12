"""Laço em tempo real: sensor → simulação → saídas, numa thread a ``tick_hz``.

Um ``InteractionRuntime`` por processo (o mestre cria um). O renderer do ProjMap
lê ``snapshot()`` a cada frame (fonte ``interactive``) e as saídas (OSC → TD)
recebem cada passo. Trocar a cena ou o sensor é seguro com a cena rodando.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .outputs import OscOutput
from .render import render_snapshot
from .scene import PRESETS, SceneSpec
from .sensors import Sensor, SimSensor, get_sensor
from .sim import Event, Simulation, Snapshot

log = logging.getLogger(__name__)

_current: Optional["InteractionRuntime"] = None


def current() -> Optional["InteractionRuntime"]:
    """Runtime ativo neste processo (o que as superfícies ``interactive`` mostram)."""
    return _current


class InteractionRuntime:
    def __init__(self, spec: Optional[SceneSpec] = None, sensor: Optional[Sensor] = None,
                 outputs: Optional[list] = None, tick_hz: float = 60.0, scene_file: Optional[Path] = None):
        self.spec = spec or PRESETS["fantasmas-timidos"]
        self.sensor: Sensor = sensor or SimSensor(aspect=self.spec.aspect)
        self.outputs = list(outputs or [])
        self.tick_hz = tick_hz
        self.scene_file = scene_file
        self._sim = Simulation(self.spec)
        self._lock = threading.Lock()
        self._snap: Snapshot = self._sim.step(0.0, self.sensor.players())
        self._events: deque[Event] = deque(maxlen=50)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._render_cache: tuple[int, tuple[int, int], np.ndarray] | None = None
        self.paused = False
        self.debug_overlay = False  # desenha pessoa + região do olhar (calibração)
        # Efeitos importados do visual_frames (projmap/effects): quando um está
        # ativo, as superfícies "Cena interativa" mostram o efeito em vez da cena.
        self.effect: Optional[str] = None
        self._engine = None
        self.engine_factory = None  # testes injetam um motor falso
        self.publisher = None  # transmissão RTSP opcional (ver interact/stream.py)

    # ------------------------------------------------------------- ciclo de vida
    def start(self) -> "InteractionRuntime":
        global _current
        _current = self
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="interact", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        global _current
        self._stop.set()
        if self.publisher is not None:
            self.publisher.stop()
            self.publisher = None
        self._stop_engine()
        if self._thread:
            self._thread.join(timeout=2)
        self.sensor.close()
        for out in self.outputs:
            out.close()
        if _current is self:
            _current = None

    def _run(self) -> None:
        period = 1.0 / self.tick_hz
        last = time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            dt, last = now - last, now
            self.step(0.0 if self.paused else dt)
            time.sleep(max(0.0, period - (time.perf_counter() - now)))

    def step(self, dt: float) -> Snapshot:
        """Um passo (público para testes e para o modo sem thread)."""
        players = self.sensor.players()
        with self._lock:
            snap = self._sim.step(dt, players)
            self._snap = snap
            self._events.extend(snap.events)
        for out in self.outputs:
            out.send(snap)
        return snap

    # ------------------------------------------------------------------ estado
    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snap

    def recent_events(self) -> list[Event]:
        with self._lock:
            return list(self._events)

    def set_scene(self, spec: SceneSpec) -> None:
        self.set_effect(None)  # voltar a uma cena desliga o efeito (libera câmera e GPU)
        with self._lock:
            self.spec = spec
            self._sim = Simulation(spec)
            self._snap = self._sim.step(0.0, self.sensor.players())
            self._render_cache = None
        if isinstance(self.sensor, SimSensor):
            self.sensor.aspect = spec.aspect
        if self.scene_file is not None:
            self.scene_file.parent.mkdir(parents=True, exist_ok=True)
            self.scene_file.write_text(spec.model_dump_json(indent=2), encoding="utf-8")

    def set_sensor(self, sensor: Sensor) -> None:
        old = self.sensor
        self.sensor = sensor
        old.close()

    def reset(self) -> None:
        with self._lock:
            self._sim.reset(self.sensor.players())

    # ------------------------------------------------------- efeitos visuais
    def set_effect(self, key: Optional[str]) -> None:
        """Liga um efeito do visual_frames ("vf-luz", "vf-lego", "vf-ecos") ou volta à cena (None).

        O motor (câmera + YOLO + áudio) só sobe quando o primeiro efeito é
        escolhido. Se o sensor da cena for a webcam, ele é trocado pela pessoa
        simulada: a câmera passa a ser do motor (duas aberturas brigariam)."""
        if key is None:
            self.effect = None
            self._stop_engine()
            return
        if self._engine is None:
            if self.sensor.kind == "webcam":
                self.set_sensor(SimSensor(aspect=self.spec.aspect))
            factory = self.engine_factory
            if factory is None:
                from ..effects.engine import EffectsEngine

                camera = getattr(self, "camera", "auto")
                factory = lambda: EffectsEngine(camera=camera)  # noqa: E731
            self._engine = factory().start()
        self._engine.set_effect(key)
        self.effect = key

    def _stop_engine(self) -> None:
        if self._engine is not None:
            self._engine.stop()
            self._engine = None

    @property
    def engine(self):
        return self._engine

    def render(self, size: tuple[int, int] = (1280, 720), debug: Optional[bool] = None) -> tuple[int, np.ndarray]:
        """Frame RGBA do estado atual (cacheado por tick)."""
        if self.effect is not None and self._engine is not None:
            seq, img = self._engine.frame()
            if (img.shape[1], img.shape[0]) != size:
                img = cv2.resize(img, size, interpolation=cv2.INTER_LINEAR)
            return -seq - 1, img  # chave negativa: não colide com os ticks da cena
        debug = self.debug_overlay if debug is None else debug
        snap = self.snapshot()
        cache = self._render_cache
        if cache and cache[0] == snap.tick and cache[1] == size:
            return snap.tick, cache[2]
        img = render_snapshot(snap, size, debug=debug)
        self._render_cache = (snap.tick, size, img)
        return snap.tick, img


def build_runtime(spec: Optional[SceneSpec] = None, sensor: str = "sim", osc_out: Optional[str] = None,
                  sensor_options: Optional[dict] = None, scene_file: Optional[Path] = None) -> InteractionRuntime:
    """Monta o runtime a partir de opções de linha de comando/config."""
    from .outputs import parse_target

    if spec is None and scene_file is not None and scene_file.is_file():
        try:
            spec = SceneSpec.model_validate_json(scene_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.error("cena salva inválida (%s); usando o preset padrão", exc)
    spec = spec or PRESETS["fantasmas-timidos"]
    outputs = []
    if osc_out:
        host, port = parse_target(osc_out)
        outputs.append(OscOutput(host, port))
    sens = get_sensor(sensor, aspect=spec.aspect, **(sensor_options or {}))
    return InteractionRuntime(spec, sens, outputs, scene_file=scene_file)
