"""Renderização de uma `Idea` aprovada em arquivo de vídeo.

Liga o roteiro (cenas) ao `VideoPipeline`, usando os geradores de imagem e voz
selecionados na configuração (placeholder por padrão, ou provedores reais).
Requer FFmpeg no PATH (já incluído na imagem Docker da API).
"""

from __future__ import annotations

import os
from pathlib import Path

from agents.media.factory import get_image_generator, get_voice_generator
from agents.video_pipeline import VideoJob, VideoPipeline

_OUTPUT_DIR = os.environ.get("ANE_OUTPUT_DIR", "output")


def render_idea(idea, config: dict | None = None) -> Path:
    """Renderiza o vídeo da ideia e devolve o caminho do `.mp4`.

    Levanta `ValueError` se a ideia não tiver cenas e `RuntimeError` se o FFmpeg
    ou um provedor de mídia falhar.
    """
    if not idea.scenes:
        raise ValueError("A ideia não tem cenas para renderizar.")

    pipeline = VideoPipeline(
        image_generator=get_image_generator(config),
        voice_generator=get_voice_generator(config),
    )
    job = VideoJob(
        title=idea.title or idea.id,
        scenes=idea.scenes,
        output_dir=Path(_OUTPUT_DIR) / "videos" / idea.id,
    )
    return pipeline.render(job)
