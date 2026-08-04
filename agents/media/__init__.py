"""Geradores plugáveis de mídia (imagem e voz) para o pipeline de vídeo."""

from .factory import get_image_generator, get_video_generator, get_voice_generator

__all__ = ["get_image_generator", "get_video_generator", "get_voice_generator"]
