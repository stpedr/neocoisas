"""Configuração centralizada do ProjMap Standalone (variáveis ``PROJMAP_*`` e caminhos).

Todas as leituras de variáveis de ambiente e diretórios de configuração da
máquina (``~/.projmap``) passam por este módulo, mantendo o ProjMap 100%
independente do restante do repositório.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_projmap_env(path: Optional[Path] = None) -> None:
    """Carrega ``.env.projmap`` (prioritário) e ``.env`` da raiz em ``os.environ``.

    Não requer dependências externas e nunca sobrescreve variáveis já definidas
    no ambiente do processo.
    """
    candidates = [path] if path is not None else [REPO_ROOT / ".env.projmap", REPO_ROOT / ".env"]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            if key:
                os.environ.setdefault(key, val)


def config_dir() -> Path:
    """Diretório de preferências da máquina (``PROJMAP_CONFIG_DIR`` ou ``~/.projmap``)."""
    raw = (os.environ.get("PROJMAP_CONFIG_DIR") or "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".projmap"


def scenes_dir() -> Path:
    """Diretório de assets visuais das cenas interativas (``PROJMAP_SCENES_DIR`` ou ``~/.projmap/scenes``)."""
    raw = (os.environ.get("PROJMAP_SCENES_DIR") or "").strip()
    return Path(raw).expanduser() if raw else config_dir() / "scenes"


def face_model_path() -> Path:
    """Caminho do modelo local do MediaPipe FaceLandmarker."""
    raw = (os.environ.get("PROJMAP_FACE_MODEL") or "").strip()
    return Path(raw).expanduser() if raw else Path("models/face_landmarker.task")


def max_photo_bytes() -> int:
    """Limite máximo de upload da foto do projetor em bytes (padrão: 25 MB)."""
    raw = (os.environ.get("PROJMAP_MAX_PHOTO_MB") or "25").strip()
    try:
        mb = max(1, int(raw))
    except ValueError:
        mb = 25
    return mb * 1024 * 1024


def pairing_token_from_env() -> Optional[str]:
    """Token fixo de pareamento da LAN vindo de ``PROJMAP_TOKEN`` (se definido)."""
    tok = (os.environ.get("PROJMAP_TOKEN") or "").strip()
    return tok or None
