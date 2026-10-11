"""Cria (ou remove) o atalho "ProjMap" no Menu Iniciar.

    python -m projmap.desktop.install              # Menu Iniciar
    python -m projmap.desktop.install --desktop    # + Área de Trabalho
    python -m projmap.desktop.install --uninstall  # remove os atalhos

O atalho chama ``pythonw.exe -m projmap.desktop`` (sem janela de terminal) do
mesmo ambiente Python que rodou este comando, na pasta do repositório. No Linux
cria um ``.desktop`` em ``~/.local/share/applications``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .core import REPO_ROOT

APP_NAME = "ProjMap"
ICON_PATH = REPO_ROOT / "projmap" / "desktop" / "projmap.ico"


def make_icon(path: Path = ICON_PATH) -> Path:
    """Ícone do app (losango roxo/azul com ▶, igual ao da UI) em .ico multi-tamanho."""
    from PIL import Image, ImageDraw

    n = 256
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    grad = Image.new("RGBA", (n, n))
    px = grad.load()
    a, b = (124, 92, 255), (79, 140, 255)
    for y in range(n):
        for x in range(n):
            t = (x + y) / (2 * n - 2)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, n - 1, n - 1), radius=64, fill=255)
    img.paste(grad, (0, 0), mask)
    ImageDraw.Draw(img).polygon([(104, 80), (184, 128), (104, 176)], fill=(255, 255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def gui_python() -> str:
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return str(cand if cand.is_file() else exe)


def windows_shortcut_paths(desktop: bool) -> list[Path]:
    start = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    paths = [start / f"{APP_NAME}.lnk"]
    if desktop:
        paths.append(Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop" / f"{APP_NAME}.lnk")
    return paths


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def create_windows_shortcut(lnk: Path, target: str, args: str, workdir: Path, icon: Path) -> None:
    lnk.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + _ps_quote(lnk) + ");"
        f"$s.TargetPath = {_ps_quote(target)};"
        f"$s.Arguments = {_ps_quote(args)};"
        f"$s.WorkingDirectory = {_ps_quote(workdir)};"
        f"$s.IconLocation = {_ps_quote(str(icon) + ',0')};"
        "$s.Description = 'ProjMap - projeção mapeada';"
        "$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True,
                   capture_output=True, text=True)


def linux_desktop_entry(target: str, icon: Path) -> str:
    return (
        "[Desktop Entry]\nType=Application\nName=ProjMap\nComment=Projeção mapeada\n"
        f"Exec={target} -m projmap.desktop\nPath={REPO_ROOT}\nIcon={icon}\nTerminal=false\nCategories=AudioVideo;Graphics;\n"
    )


def install(desktop: bool = False) -> list[Path]:
    icon = make_icon()
    target = gui_python()
    if sys.platform == "win32":
        out = windows_shortcut_paths(desktop)
        for lnk in out:
            create_windows_shortcut(lnk, target, "-m projmap.desktop", REPO_ROOT, icon)
        return out
    png = icon.with_suffix(".png")
    from PIL import Image

    Image.open(icon).save(png)
    entry = Path.home() / ".local" / "share" / "applications" / "projmap.desktop"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(linux_desktop_entry(target, png), encoding="utf-8")
    return [entry]


def uninstall() -> list[Path]:
    removed = []
    cands = windows_shortcut_paths(True) if sys.platform == "win32" else [
        Path.home() / ".local" / "share" / "applications" / "projmap.desktop"]
    for p in cands:
        if p.exists():
            p.unlink()
            removed.append(p)
    return removed


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="projmap.desktop.install", description="Atalho do ProjMap no Menu Iniciar")
    ap.add_argument("--desktop", action="store_true", help="também cria um atalho na Área de Trabalho")
    ap.add_argument("--uninstall", action="store_true", help="remove os atalhos")
    args = ap.parse_args(argv)
    if args.uninstall:
        removed = uninstall()
        print("Removido:" if removed else "Nenhum atalho encontrado.", *map(str, removed), sep="\n  ")
        return
    for p in install(args.desktop):
        print(f"Atalho criado: {p}")
    print("Procure por \"ProjMap\" no Menu Iniciar.")


if __name__ == "__main__":
    main()
