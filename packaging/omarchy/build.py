"""Gera o tarball do ProjMap para Omarchy / Arch Linux.

    cd projmap/ui && npm ci && npm run build && cd ../..
    python packaging/omarchy/build.py            # -> dist/projmap-<versão>-omarchy-x86_64.tar.gz

Leva o pacote ``projmap/`` (da UI só o export estático ``ui/out``), os
requirements, o ``install.sh`` e o ``README-OMARCHY.md`` desta pasta. Finais de
linha viram LF para os scripts rodarem no Linux mesmo gerados no Windows.
"""

from __future__ import annotations

import argparse
import io
import tarfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SKIP_DIRS = {"__pycache__", "node_modules", ".next", "test-results", "android", ".pytest_cache", ".mypy_cache"}
TEXT_SUFFIXES = {".py", ".sh", ".md", ".txt", ".frag", ".vert", ".glsl", ".json", ".toml"}
ROOT_FILES = ["pyproject.toml", "requirements-projmap-master.txt", "requirements-projmap-node.txt", "LICENSE"]


def keep(rel: Path) -> bool:
    parts = rel.parts
    if any(p in SKIP_DIRS for p in parts) or rel.suffix in {".pyc", ".tsbuildinfo"}:
        return False
    # da UI só vai o export estático
    return not (parts[:2] == ("projmap", "ui") and len(parts) > 2 and parts[2] != "out")


def _add(tar: tarfile.TarFile, arc: str, data: bytes, mode: int = 0o644, text: bool = True) -> None:
    if text:
        data = data.replace(b"\r\n", b"\n")
    info = tarfile.TarInfo(arc)
    info.size, info.mode = len(data), mode
    tar.addfile(info, io.BytesIO(data))


def build(repo: Path = REPO, out_dir: Path | None = None) -> Path:
    if not (repo / "projmap/ui/out/index.html").is_file():
        raise SystemExit("UI não compilada: cd projmap/ui && npm ci && npm run build")
    version = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    name = f"projmap-{version}-omarchy-x86_64"
    out_dir = out_dir or repo / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.tar.gz"
    with tarfile.open(target, "w:gz") as tar:
        for f in sorted((repo / "projmap").rglob("*")):
            rel = f.relative_to(repo)
            if f.is_file() and keep(rel):
                _add(tar, f"{name}/{rel.as_posix()}", f.read_bytes(), text=f.suffix in TEXT_SUFFIXES)
        for extra in ROOT_FILES:
            _add(tar, f"{name}/{extra}", (repo / extra).read_bytes())
        _add(tar, f"{name}/VERSION", f"{version}\n".encode())
        _add(tar, f"{name}/README-OMARCHY.md", (HERE / "README-OMARCHY.md").read_bytes())
        _add(tar, f"{name}/install.sh", (HERE / "install.sh").read_bytes(), mode=0o755)
    return target


def main() -> None:
    ap = argparse.ArgumentParser(description="Tarball do ProjMap para Omarchy / Arch Linux")
    ap.add_argument("--out", type=Path, default=None, help="pasta de saída (padrão: dist/)")
    target = build(out_dir=ap.parse_args().out)
    print(f"{target} ({target.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
