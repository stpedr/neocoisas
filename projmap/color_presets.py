"""Presets de imagem do operador ("minhas configurações").

Um preset é um :class:`ColorAdjust` com nome (brilho, contraste, saturação,
gama, temperatura). Ficam na máquina (``~/.projmap/color-presets.json``), não no
show: o mesmo "Parede da igreja" serve para vários shows. O editor e o remote
aplicam um preset numa superfície (ou no projetor inteiro) com um clique.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import unicodedata
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .core.project import ColorAdjust

PRESETS_PATH = Path.home() / ".projmap" / "color-presets.json"
MAX_PRESETS = 100


class ColorPreset(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=60)
    color: ColorAdjust

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("nome vazio")
        return v


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:48] or "preset"


class ColorPresetStore:
    def __init__(self, path: Path = PRESETS_PATH):
        self.path = Path(path)
        self._lock = threading.Lock()

    def list(self) -> list[ColorPreset]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = []
        for item in raw.get("presets", []) if isinstance(raw, dict) else []:
            try:
                out.append(ColorPreset.model_validate(item))
            except ValueError:
                continue  # preset corrompido não derruba a lista
        return out

    def save(self, name: str, color: ColorAdjust) -> ColorPreset:
        """Cria ou substitui (mesmo nome = atualiza o preset)."""
        with self._lock:
            items = self.list()
            preset = ColorPreset(id=slug(name), name=name, color=color)
            items = [p for p in items if p.id != preset.id]
            if len(items) >= MAX_PRESETS:
                raise ValueError(f"limite de {MAX_PRESETS} presets; apague algum antes")
            items.append(preset)
            self._write(items)
            return preset

    def delete(self, preset_id: str) -> bool:
        with self._lock:
            items = self.list()
            kept = [p for p in items if p.id != preset_id]
            if len(kept) == len(items):
                return False
            self._write(kept)
            return True

    def _write(self, items: list[ColorPreset]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".presets.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"presets": [p.model_dump(mode="json") for p in items]}, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
