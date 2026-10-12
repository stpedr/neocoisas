"""Importa o trabalho do visual_frames: shader GLSL e modelos YOLO26.

    python -m projmap.effects.importar                       # usa ../visual_frames ou clona do GitHub
    python -m projmap.effects.importar C:\\caminho\\visual_frames
    python -m projmap.effects.importar https://github.com/adrielvasques/visual_frames.git

Copia para ``~/.projmap/visual_frames/``:
- ``efeitos.frag``: o FRAGMENT_SHADER extraído de ``of_void_cloud/src/ofApp.cpp``;
- ``modelos/yolo26n-seg.onnx`` e ``modelos/yolo26s-pose.onnx``;
- ``ORIGEM.txt``: de onde e de qual commit veio.

O código do autor não entra no repositório do ProjMap: fica na máquina, e
reimportar traz as melhorias que ele fizer depois.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

DEST = Path.home() / ".projmap" / "visual_frames"
REPO_URL = "https://github.com/adrielvasques/visual_frames.git"
MODELS = ("yolo26n-seg.onnx", "yolo26s-pose.onnx")
_SHADER_RE = re.compile(r'const std::string FRAGMENT_SHADER = R"\((?P<src>.*?)\)";', re.S)


def extract_fragment_shader(ofapp_cpp: str) -> str:
    m = _SHADER_RE.search(ofapp_cpp)
    if not m:
        raise ValueError("FRAGMENT_SHADER não encontrado no ofApp.cpp (o projeto original mudou de formato?)")
    return m.group("src").strip() + "\n"


def _find_repo(src: str | None) -> tuple[Path, bool]:
    """Devolve (pasta do repo, é temporária?)."""
    if src and not src.startswith(("http://", "https://", "git@")):
        p = Path(src).expanduser()
        if not (p / "of_void_cloud" / "src" / "ofApp.cpp").is_file():
            raise FileNotFoundError(f"{p} não parece o visual_frames (falta of_void_cloud/src/ofApp.cpp)")
        return p, False
    if not src:
        for cand in (Path.cwd().parent / "visual_frames", Path(__file__).resolve().parents[3] / "visual_frames"):
            if (cand / "of_void_cloud" / "src" / "ofApp.cpp").is_file():
                return cand, False
    tmp = Path(tempfile.mkdtemp(prefix="visual_frames-"))
    subprocess.run(["git", "clone", "--depth", "1", src or REPO_URL, str(tmp / "vf")], check=True)
    return tmp / "vf", True


def import_from(src: str | None = None, dest: Path = DEST) -> Path:
    repo, temporary = _find_repo(src)
    try:
        shader = extract_fragment_shader((repo / "of_void_cloud" / "src" / "ofApp.cpp").read_text(encoding="utf-8"))
        (dest / "modelos").mkdir(parents=True, exist_ok=True)
        (dest / "efeitos.frag").write_text(shader, encoding="utf-8")
        for name in MODELS:
            shutil.copy2(repo / "modelos" / name, dest / "modelos" / name)
        try:
            commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                                    check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            commit = "desconhecido"
        (dest / "ORIGEM.txt").write_text(
            f"visual_frames, de Adriel Vasques (usado com permissão)\n{REPO_URL}\ncommit: {commit}\n"
            f"importado de: {repo}\n", encoding="utf-8")
        return dest
    finally:
        if temporary:
            shutil.rmtree(repo.parent, ignore_errors=True)


def is_imported(dest: Path = DEST) -> bool:
    return (dest / "efeitos.frag").is_file() and all((dest / "modelos" / m).is_file() for m in MODELS)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="projmap.effects.importar", description=__doc__.split("\n")[0])
    ap.add_argument("origem", nargs="?", help="pasta do visual_frames clonado ou URL do git")
    args = ap.parse_args(argv)
    dest = import_from(args.origem)
    print(f"Importado para {dest}")
    print("No editor: card Interativo -> Luz reativa / LEGO / Ecos em quadrinhos.")


if __name__ == "__main__":
    main()
