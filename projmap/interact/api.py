"""Rotas da camada interativa na API do mestre (``/api/interact/...``)."""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from .nlp import TextClient, scene_from_text
from .runtime import InteractionRuntime
from .scene import PRESETS, SceneSpec
from .sensors import PhoneSensor, SimSensor, get_sensor

log = logging.getLogger(__name__)


class GenerateBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    use_llm: bool = True


class PlayerBody(BaseModel):
    x: Optional[float] = Field(None, ge=0, le=1)
    distance: Optional[float] = Field(None, gt=0, le=20)
    yaw_deg: Optional[float] = Field(None, ge=-360, le=360)
    tracked: Optional[bool] = None


class SensorBody(BaseModel):
    kind: str
    options: dict[str, Any] = Field(default_factory=dict)


def create_router(runtime: InteractionRuntime,
                  client_factory: Callable[[], Optional[TextClient]]) -> APIRouter:
    r = APIRouter(prefix="/api/interact")

    def state() -> dict:
        snap = runtime.snapshot()
        spec = snap.spec
        a = spec.aspect
        return {
            "spec": spec.model_dump(mode="json"),
            "sensor": runtime.sensor.kind,
            "phone": ({"connected": runtime.sensor.connected, "fps": runtime.sensor.fps}
                      if isinstance(runtime.sensor, PhoneSensor) else None),
            "scripted": isinstance(runtime.sensor, SimSensor) and runtime.sensor.script is not None,
            "paused": runtime.paused,
            "debug": runtime.debug_overlay,
            "tick": snap.tick,
            "entities": [
                {"id": e.id, "group": spec.groups[e.group].name, "x": e.x / a, "y": e.y, "state": e.state}
                for e in snap.entities
            ],
            "players": [
                {"id": p.id, "x": p.x / a, "distance": p.distance, "yaw_deg": math.degrees(p.yaw),
                 "tracked": p.tracked, "watching": g.active, "gaze": [g.center[0] / a, g.center[1], g.radius]}
                for p, g in zip(snap.players, snap.gazes)
            ],
            "events": [{"name": ev.name, "entity_id": ev.entity_id, "t": ev.t} for ev in runtime.recent_events()[-10:]],
        }

    @r.get("/state")
    def get_state() -> dict:
        return state()

    @r.get("/presets")
    def presets() -> dict:
        return {k: {"title": v.title, "description": v.description} for k, v in PRESETS.items()}

    @r.post("/presets/{name}")
    def apply_preset(name: str) -> dict:
        if name not in PRESETS:
            raise HTTPException(404, f"preset '{name}' não existe")
        runtime.set_scene(PRESETS[name])
        return state()

    @r.post("/generate")
    def generate(body: GenerateBody) -> dict:
        result = scene_from_text(body.text, client_factory() if body.use_llm else None, use_llm=body.use_llm)
        runtime.set_scene(result.spec)
        return {"source": result.source, "notes": result.notes, **state()}

    @r.put("/spec")
    def put_spec(spec: dict[str, Any]) -> dict:
        try:
            runtime.set_scene(SceneSpec.model_validate(spec))
        except ValidationError as exc:
            raise HTTPException(422, [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]) from exc
        return state()

    @r.post("/player")
    def set_player(body: PlayerBody) -> dict:
        if not isinstance(runtime.sensor, SimSensor):
            raise HTTPException(409, "pessoa simulada só com o sensor 'sim'")
        runtime.sensor.set(body.x, body.distance, body.yaw_deg, body.tracked)
        return state()

    @r.post("/player/auto")
    def player_auto() -> dict:
        if not isinstance(runtime.sensor, SimSensor):
            raise HTTPException(409, "roteiro automático só com o sensor 'sim'")
        runtime.sensor.script = "turning"
        return state()

    @r.post("/sensor")
    def set_sensor(body: SensorBody) -> dict:
        try:
            runtime.set_sensor(get_sensor(body.kind, aspect=runtime.spec.aspect, **body.options))
        except (ValueError, RuntimeError, OSError, TypeError) as exc:
            raise HTTPException(422, [str(exc)]) from exc
        return state()

    # HEAD também: a página /sensor testa com HEAD se há modelo local antes de baixar
    # da internet (sem isso o HEAD caía no StaticFiles e dava 404).
    @r.api_route("/face-model", methods=["GET", "HEAD"])
    def face_model() -> FileResponse:
        """Modelo do MediaPipe servido localmente (celular sem internet).

        Procura ``PROJMAP_FACE_MODEL`` ou ``models/face_landmarker.task``; sem ele, a
        página ``/sensor`` baixa do servidor oficial do MediaPipe.
        """
        path = Path(os.environ.get("PROJMAP_FACE_MODEL", "models/face_landmarker.task"))
        if not path.is_file():
            raise HTTPException(404, "modelo local ausente (rode: python -m projmap.tools.fetch_models)")
        return FileResponse(path, media_type="application/octet-stream")

    @r.websocket("/phone")
    async def phone(ws: WebSocket) -> None:
        """Celular-sensor. Conectar já troca o sensor ativo para ``phone``."""
        await ws.accept()
        if not isinstance(runtime.sensor, PhoneSensor):
            log.info("celular conectado: sensor ativo → phone")
            runtime.set_sensor(PhoneSensor(aspect=runtime.spec.aspect))
        sensor = runtime.sensor
        assert isinstance(sensor, PhoneSensor)
        sensor.connected += 1
        n = 0
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    sensor.update(json.loads(msg))
                except (ValueError, TypeError) as exc:
                    await ws.send_text(json.dumps({"error": str(exc)}))
                    continue
                n += 1
                if n % 5 == 0:  # retorno leve para a tela do celular
                    snap = runtime.snapshot()
                    p = snap.players[0] if snap.players else None
                    g = snap.gazes[0] if snap.gazes else None
                    await ws.send_text(json.dumps({
                        "tracked": bool(p and p.tracked), "watching": bool(g and g.active),
                        "yaw_deg": math.degrees(p.yaw) if p else 0.0,
                        "x": (p.x / snap.spec.aspect) if p else 0.5,
                        "scene": snap.spec.title,
                        "moving": sum(e.state == "move" for e in snap.entities),
                        "frozen": sum(e.state in ("shy", "frozen") for e in snap.entities),
                    }))
        except WebSocketDisconnect:
            pass
        finally:
            sensor.connected = max(0, sensor.connected - 1)

    @r.post("/reset")
    def reset() -> dict:
        runtime.reset()
        return state()

    @r.post("/debug")
    def debug(on: bool = True) -> dict:
        runtime.debug_overlay = on
        return state()

    @r.post("/pause")
    def pause(paused: bool = True) -> dict:
        runtime.paused = paused
        return state()

    return r
