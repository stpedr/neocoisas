"""WebSocket da página host dos motions (``/ws/motion-host``) e status (``/api/motions/host``).

Só o navegador desta máquina conecta (loopback): ele recebe as sessões, o áudio
do show e quadros da entrada de vídeo, e devolve os pixels de cada motion.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import cv2
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..motion.hub import MotionHub, hub as default_hub, pack
from .auth import is_loopback

log = logging.getLogger(__name__)

AUDIO_HZ = 60
VIDEO_MAX_W = 640


def _video_packet(device: str, rgba: Any) -> Optional[bytes]:
    """Quadro da câmera → JPEG pequeno para o motion (roda numa thread)."""
    bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
    hh, ww = bgr.shape[:2]
    if ww > VIDEO_MAX_W:
        bgr = cv2.resize(bgr, (VIDEO_MAX_W, round(hh * VIDEO_MAX_W / ww)), interpolation=cv2.INTER_AREA)
    ok, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return None
    return pack({"kind": "video", "device": device, "w": bgr.shape[1], "h": bgr.shape[0]}, jpg.tobytes())


def create_router(owner: Optional[MotionHub] = None) -> APIRouter:
    r = APIRouter()

    def _hub() -> MotionHub:
        return owner or default_hub()

    @r.get("/api/motions/host")
    def host_status() -> dict[str, Any]:
        return _hub().status()

    @r.websocket("/ws/motion-host")
    async def motion_host(ws: WebSocket) -> None:
        if not is_loopback(ws.scope):
            await ws.close(code=1008)
            return
        await ws.accept()
        h = _hub()
        h.host_connected = True
        sources: dict[str, Any] = {}
        sent_keys: dict[str, int] = {}

        async def receiver() -> None:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    raise WebSocketDisconnect(msg.get("code", 1000))
                text = msg.get("text")
                if text:
                    h.note_host_stats(text)
                    continue
                data = msg.get("bytes")
                if data:
                    try:  # decodificar o JPEG fora do event loop: senão o editor (HTTP) engasga
                        await asyncio.to_thread(h.put_frame, data)
                    except ValueError as exc:
                        log.warning("motions: quadro descartado (%s)", exc)

        async def sender() -> None:
            from ..inputs.audio import bus
            from ..inputs.video import open_capture

            version = -1
            tick = 0
            while True:
                v, sessions = h.sessions()
                if v != version:
                    version = v
                    await ws.send_json({"type": "sessions", "sessions": sessions})
                lv = bus().status()
                await ws.send_json({"type": "audio", "beats": lv["beats"], **lv["levels"]})
                tick += 1
                if tick % 2 == 0:  # vídeo a ~30 fps
                    wanted = h.devices()
                    for dev in list(sources):
                        if dev not in wanted:
                            sources.pop(dev).close()
                            sent_keys.pop(dev, None)
                    for dev in wanted:
                        if dev not in sources:
                            sources[dev] = open_capture(dev)
                        key, rgba = sources[dev].frame_at(0)
                        if key == 0 or sent_keys.get(dev) == key:
                            continue
                        sent_keys[dev] = key
                        packet = await asyncio.to_thread(_video_packet, dev, rgba)
                        if packet:
                            await ws.send_bytes(packet)
                await asyncio.sleep(1 / AUDIO_HZ)

        tasks = [asyncio.create_task(receiver()), asyncio.create_task(sender())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for t in done:
                exc = t.exception()
                if isinstance(exc, WebSocketDisconnect):
                    log.info("motions: página host desconectou (%s)", exc.code)
                elif exc is not None:
                    log.error("motions: conexão do host caiu (%r)", exc)
        finally:
            for t in tasks:
                t.cancel()
            for src in sources.values():
                src.close()
            h.host_connected = False

    return r
