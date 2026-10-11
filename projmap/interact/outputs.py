"""Saídas do motor de interação — OSC para o TouchDesigner (ou qualquer app).

O motor decide *onde está cada coisa e em que estado*; quem desenha pode ser o
renderer nativo do ProjMap (``render.py``) ou o TouchDesigner, que recebe o
estado por OSC e faz o visual (instancing, partículas, shaders do TD).

Mensagens (padrão ``127.0.0.1:7000``), coordenadas **normalizadas 0..1**::

    /projmap/frame   tick:int  t:float  count:int  flash:float
    /projmap/entity  id:int  group:str  x:float  y:float  state:str  heading:float  size:float
    /projmap/player  id:int  x:float  y:float  yaw_deg:float  watching:int  gaze_x:float  gaze_y:float  gaze_r:float
    /projmap/event   name:str  entity_id:int
    /projmap/scene   json:str            (quando a cena muda)

``state``: ``move`` | ``frozen`` | ``shy`` | ``idle``. ``y`` cresce para baixo
(como o canvas); no TD, use ``1 - y`` se o seu espaço tiver y para cima.
"""

from __future__ import annotations

import logging
from typing import Optional

from .sim import Snapshot

log = logging.getLogger(__name__)


class OscOutput:
    kind = "osc"

    def __init__(self, host: str = "127.0.0.1", port: int = 7000):
        from pythonosc.udp_client import SimpleUDPClient

        self.host, self.port = host, port
        self._client = SimpleUDPClient(host, port)
        self._scene_json: Optional[str] = None

    def send(self, snap: Snapshot) -> None:
        c = self._client
        a = snap.spec.aspect
        try:
            scene_json = snap.spec.model_dump_json()
            if scene_json != self._scene_json:
                c.send_message("/projmap/scene", scene_json)
                self._scene_json = scene_json
            c.send_message("/projmap/frame", [snap.tick, float(snap.t), len(snap.entities), float(snap.flash)])
            for e in snap.entities:
                g = snap.spec.groups[e.group]
                c.send_message("/projmap/entity", [e.id, g.name, e.x / a, e.y, e.state, float(e.heading), g.size])
            for p, gz in zip(snap.players, snap.gazes):
                c.send_message("/projmap/player", [p.id, p.x / a, p.eye_y, _deg(p.yaw), int(gz.active),
                                                   gz.center[0] / a, gz.center[1], gz.radius])
            for ev in snap.events:
                c.send_message("/projmap/event", [ev.name, ev.entity_id])
        except OSError as exc:  # rede caiu / TD fechado: não derruba o motor
            log.debug("OSC %s:%s indisponível: %s", self.host, self.port, exc)

    def close(self) -> None:
        pass


def _deg(rad: float) -> float:
    import math

    return math.degrees(rad)


def parse_target(target: str) -> tuple[str, int]:
    """``"host:porta"`` → (host, porta)."""
    host, _, port = target.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError(f"destino OSC inválido: '{target}' (use host:porta)")
    return host, int(port)
