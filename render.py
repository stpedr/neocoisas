"""Renderização de uma `Idea` aprovada em arquivo de vídeo.

Liga o roteiro (cenas) ao `VideoPipeline`, usando os geradores de imagem e voz
selecionados na configuração (placeholder por padrão, ou provedores reais).
Requer FFmpeg no PATH (já incluído na imagem Docker da API).
"""

from __future__ import annotations

import os
from pathlib import Path

from agents.media.factory import (
    get_image_generator,
    get_video_generator,
    get_voice_generator,
)
from agents.video_pipeline import Scene, VideoJob, VideoPipeline

_OUTPUT_DIR = os.environ.get("ANE_OUTPUT_DIR", "output")


def _flag(env_name: str, config: dict, key: str, default: bool) -> bool:
    env = os.environ.get(env_name)
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "sim")
    return bool(config.get(key, default))


def _burn_subtitles(config: dict) -> bool:
    return _flag("ANE_BURN_SUBTITLES", config, "burn_subtitles", True)


def _idea_dir(idea) -> Path:
    return Path(_OUTPUT_DIR) / "videos" / idea.id


def render_idea(idea, config: dict | None = None, lang: str | None = None) -> Path:
    """Renderiza o vídeo da ideia e devolve o caminho do `.mp4`.

    Com `lang`, gera uma **variante localizada**: traduz as narrações (legenda e,
    se houver TTS real, áudio) e grava num arquivo com sufixo de idioma.

    Levanta `ValueError` se a ideia não tiver cenas e `RuntimeError` se o FFmpeg
    ou um provedor de mídia falhar.
    """
    config = config or {}
    if not idea.scenes:
        raise ValueError("A ideia não tem cenas para renderizar.")

    scenes = idea.scenes
    title = idea.title or idea.id
    if lang:
        from agents.translator import TranslatorAgent

        traducoes = TranslatorAgent().translate([s.narration for s in idea.scenes], lang)
        scenes = [
            Scene(narration=t, visual_prompt=s.visual_prompt, duration_s=s.duration_s)
            for s, t in zip(idea.scenes, traducoes)
        ]
        title = f"{title}_{lang}"

    video_gen = get_video_generator(config)
    pipeline = VideoPipeline(
        # Com gerador de vídeo (ex: Veo/Gemini), a imagem estática é dispensável.
        image_generator=None if video_gen else get_image_generator(config),
        voice_generator=get_voice_generator(config),
        scene_video_generator=video_gen,
        burn_subtitles=_burn_subtitles(config),
        music_path=config.get("music_path") or None,
        music_volume=float(config.get("music_volume", 0.2)),
        # Ken Burns por padrão em imagens estáticas (não se aplica a vídeo por cena).
        motion=(_flag("ANE_MOTION", config, "motion", True) and not video_gen),
    )
    job = VideoJob(title=title, scenes=scenes, output_dir=_idea_dir(idea))
    return pipeline.render(job)


def render_thumbnail(idea, config: dict | None = None) -> Path:
    """Gera uma thumbnail (capa) da ideia usando o provedor de imagem."""
    config = config or {}
    prompt = idea.title or "thumbnail"
    if idea.scenes and idea.scenes[0].visual_prompt:
        prompt = f"{idea.title}. {idea.scenes[0].visual_prompt}"
    dest = _idea_dir(idea)
    dest.mkdir(parents=True, exist_ok=True)
    return get_image_generator(config)(prompt, dest / "thumb.png")
