"""Lógica do lançador, sem interface (testável): preferências, shows e o comando do mestre."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path.home() / ".projmap"
SETTINGS_PATH = CONFIG_DIR / "launcher.json"
DEFAULT_SHOWS_DIR = Path.home() / "Documents" / "ProjMap"

URL_RE = re.compile(r"(http://\S+/remote/\S*)")


@dataclass
class Settings:
    shows_dir: str = str(DEFAULT_SHOWS_DIR)
    last_show: str = ""
    output: str = "display"  # display | window | none
    display: int = 1
    lan: bool = True  # liberar o celular na mesma rede
    port: int = 8100
    token: str = ""  # vazio = gerado a cada execução
    open_browser: bool = True
    extra_library: list[str] = field(default_factory=list)


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    known = {k: v for k, v in data.items() if k in Settings.__dataclass_fields__}
    try:
        return Settings(**known)
    except TypeError:
        return Settings()


def save_settings(s: Settings, path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")


def list_shows(shows_dir: str | Path) -> list[str]:
    """Shows = pastas ``*.projmap`` com ``project.json``, mais recentes primeiro."""
    d = Path(shows_dir)
    if not d.is_dir():
        return []
    shows = [p for p in d.glob("*.projmap") if (p / "project.json").is_file()]
    shows.sort(key=lambda p: (p / "project.json").stat().st_mtime, reverse=True)
    return [p.stem for p in shows]


def safe_show_name(name: str) -> str:
    """Nome de pasta válido no Windows a partir do que o usuário digitou."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip().strip(".")
    return name[:80] or "Meu show"


def show_path(s: Settings, name: str) -> Path:
    return Path(s.shows_dir) / f"{safe_show_name(name)}.projmap"


def ui_built(root: Path = REPO_ROOT) -> bool:
    return (root / "projmap" / "ui" / "out" / "index.html").is_file()


def master_command(s: Settings, show: str, python: Optional[str] = None) -> list[str]:
    """Linha de comando do mestre para as escolhas do lançador."""
    py = python or console_python()
    cmd = [py, "-m", "projmap.master", "--project", str(show_path(s, show)), "--name", safe_show_name(show),
           "--port", str(int(s.port))]
    if s.output == "display":
        cmd += ["--display", str(int(s.display))]
    elif s.output == "window":
        cmd += ["--windowed"]
    else:
        cmd += ["--no-output"]
    if s.lan:
        cmd += ["--host", "0.0.0.0"]
        if s.token:
            cmd += ["--token", s.token]
    if s.open_browser:
        cmd += ["--open"]
    for lib in s.extra_library:
        cmd += ["--library", lib]
    return cmd


def console_python() -> str:
    """O mestre roda com python.exe (precisa de stdout para o log), mesmo se o
    lançador foi aberto com pythonw.exe pelo atalho."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.is_file():
            return str(cand)
    return str(exe)


def remote_url_from_log(line: str) -> Optional[str]:
    m = URL_RE.search(line)
    return m.group(1) if m else None
