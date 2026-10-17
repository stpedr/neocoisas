"""Manifesto de um Motion Module v1 (``<script type="application/json" id="motion-manifest">``).

O upload de um ``.html`` só entra no projeto se for um motion válido: assim a
galeria e a superfície mostram nome/versão e o renderer sabe se o motion quer
entrada de vídeo. A validação completa (params, ranges) continua no editor
(``ui/app/lib/motionModule.ts``); aqui conferimos o mínimo que o projetor usa,
sem executar nada do arquivo.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

MAX_MOTION_BYTES = 5 * 1024 * 1024
SPEC = "motion-module/1"

_MANIFEST_RE = re.compile(
    r"<script\b(?=[^>]*\bid\s*=\s*[\"']motion-manifest[\"'])(?=[^>]*\btype\s*=\s*[\"']application/json[\"'])[^>]*>"
    r"(?P<json>.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True)
class MotionInfo:
    id: str
    name: str
    version: str
    video_input: bool = False
    modes: list[str] = field(default_factory=list)


def parse_motion_html(data: bytes) -> MotionInfo:
    """Lê o manifesto; ``ValueError`` com mensagem clara se não for um motion v1."""
    if len(data) > MAX_MOTION_BYTES:
        raise ValueError(f"motion maior que {MAX_MOTION_BYTES // (1024 * 1024)} MB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("motion deve ser um .html em UTF-8") from exc
    m = _MANIFEST_RE.search(text)
    if not m:
        raise ValueError('não é um Motion Module v1: falta <script type="application/json" id="motion-manifest">')
    try:
        man: Any = json.loads(m.group("json"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifesto do motion com JSON inválido ({exc.msg})") from exc
    if not isinstance(man, dict) or man.get("spec") != SPEC:
        raise ValueError(f"manifesto do motion: 'spec' deve ser '{SPEC}'")
    mid, name, version = man.get("id"), man.get("name"), man.get("version")
    if not isinstance(mid, str) or not _ID_RE.match(mid):
        raise ValueError("manifesto do motion: 'id' inválido (kebab-case)")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("manifesto do motion: falta 'name'")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("manifesto do motion: falta 'version'")
    video = man.get("video")
    modes = [str(x["id"]) for x in man.get("modes", []) if isinstance(x, dict) and "id" in x]
    return MotionInfo(id=mid, name=name.strip()[:80], version=version.strip()[:32],
                      video_input=isinstance(video, dict) and bool(video.get("input")), modes=modes[:32])
