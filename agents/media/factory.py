"""Seleção do gerador de mídia conforme a configuração.

A escolha vem da variável de ambiente (`ANE_IMAGE_PROVIDER` /
`ANE_VOICE_PROVIDER`) ou do `config.json` (`image_provider` / `voice_provider`),
caindo em `placeholder` por padrão — assim o pipeline roda sem configuração.
"""

from __future__ import annotations

import os
from typing import Callable
from pathlib import Path

from .placeholder import placeholder_image, placeholder_voice
from .providers import elevenlabs_voice, stability_image

Generator = Callable[[str, Path], Path]

_IMAGE_PROVIDERS: dict[str, Generator] = {
    "placeholder": placeholder_image,
    "stability": stability_image,
}

_VOICE_PROVIDERS: dict[str, Generator] = {
    "placeholder": placeholder_voice,
    "elevenlabs": elevenlabs_voice,
}


def _select(name: str, table: dict[str, Generator], kind: str) -> Generator:
    if name not in table:
        opcoes = ", ".join(sorted(table))
        raise ValueError(f"Provedor de {kind} inválido: '{name}'. Opções: {opcoes}.")
    return table[name]


def get_image_generator(config: dict | None = None) -> Generator:
    config = config or {}
    name = os.environ.get("ANE_IMAGE_PROVIDER") or config.get("image_provider", "placeholder")
    return _select(name, _IMAGE_PROVIDERS, "imagem")


def get_voice_generator(config: dict | None = None) -> Generator:
    config = config or {}
    name = os.environ.get("ANE_VOICE_PROVIDER") or config.get("voice_provider", "placeholder")
    return _select(name, _VOICE_PROVIDERS, "voz")
