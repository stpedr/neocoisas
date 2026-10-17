"""Rotas HTTP para geração de Motion Module v1 com Claude (SSE streaming + configuração segura via keyring)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..ai.motion_generator import MotionAiConfigStore, stream_motion_generation

log = logging.getLogger(__name__)


class ImageBlockModel(BaseModel):
    media_type: str = "image/png"
    data: str


class MotionAiConfigBody(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None


class MotionAiGenerateBody(BaseModel):
    kind: Literal["new", "edit", "repair"] = "new"
    prompt: str = ""
    current_html: str = ""
    errors: list[str] = Field(default_factory=list)
    images: list[ImageBlockModel] = Field(default_factory=list, max_length=4)
    model: Optional[str] = None


def create_router(
    config_dir: Optional[Path] = None,
    ai_client_factory: Optional[Callable[[str], Any]] = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/motions/ai", tags=["motions-ai"])
    cfg_store = MotionAiConfigStore((config_dir / "motion-ai.json") if config_dir else None)

    @router.get("/config")
    def get_ai_config() -> dict[str, Any]:
        return cfg_store.public_status()

    @router.put("/config")
    def put_ai_config(body: MotionAiConfigBody) -> dict[str, Any]:
        if body.api_key is not None:
            cfg_store.set_api_key(body.api_key)
        if body.model is not None:
            cfg_store.set_model(body.model)
        return cfg_store.public_status()

    @router.post("/generate")
    def generate_motion(body: MotionAiGenerateBody) -> StreamingResponse:
        api_key = cfg_store.get_api_key()
        if not api_key:
            raise HTTPException(
                422,
                ["Chave ANTHROPIC_API_KEY não configurada. Defina nas configurações ou no ambiente."],
            )
        if body.kind == "new" and not body.prompt.strip():
            raise HTTPException(422, ["Informe uma descrição para gerar o motion."])
        if body.kind == "edit" and (not body.prompt.strip() or not body.current_html.strip()):
            raise HTTPException(422, ["Informe o pedido de edição e o HTML atual."])
        if body.kind == "repair" and (not body.errors or not body.current_html.strip()):
            raise HTTPException(422, ["Informe os erros e o HTML atual para reparo."])

        chosen_model = (body.model or "").strip() or cfg_store.get_model()
        imgs = [{"media_type": img.media_type, "data": img.data} for img in body.images[:4]]

        def _sse_stream() -> Iterator[str]:
            try:
                for event in stream_motion_generation(
                    kind=body.kind,
                    prompt=body.prompt,
                    current_html=body.current_html,
                    errors=body.errors,
                    images=imgs,
                    model=chosen_model,
                    api_key=api_key,
                    client_factory=ai_client_factory,
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except GeneratorExit:
                log.info("stream de geração de motion cancelado pelo cliente")
                return
            except Exception as exc:  # noqa: BLE001
                log.error("falha na geração com Claude: %s", exc)
                err_ev = {
                    "type": "done",
                    "ok": False,
                    "html": "",
                    "layer_preset": {},
                    "notes": "",
                    "errors": [f"Falha na API Anthropic: {exc}"],
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "estimated_cost_usd": 0.0,
                    },
                    "elapsed_s": 0.0,
                }
                yield f"data: {json.dumps(err_ev, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            _sse_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
