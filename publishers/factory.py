"""Seleção do publisher conforme a configuração.

`ANE_PUBLISHER` (env) ou `publisher` (config.json). Padrão `none` → sem
publicação automática (as ideias ficam aprovadas e prontas).
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from .youtube import youtube_publisher

Publisher = Callable[[object], str]

_PUBLISHERS: dict[str, Publisher] = {
    "youtube": youtube_publisher,
}


def get_publisher(config: dict | None = None) -> Optional[Publisher]:
    config = config or {}
    name = os.environ.get("ANE_PUBLISHER") or config.get("publisher", "none")
    if name in ("none", "", None):
        return None
    if name not in _PUBLISHERS:
        opcoes = ", ".join(sorted(_PUBLISHERS) + ["none"])
        raise ValueError(f"Publisher inválido: '{name}'. Opções: {opcoes}.")
    return _PUBLISHERS[name]
