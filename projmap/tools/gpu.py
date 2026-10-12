"""Faz o ProjMap usar a placa de vídeo dedicada (ex.: RTX 4060) no Windows.

Notebooks com duas placas (Intel + NVIDIA) abrem o OpenGL na integrada por
padrão: a projeção e os efeitos rodavam na Intel UHD. Este comando grava a
preferência "Alto desempenho" do Windows para o Python do ProjMap — o mesmo que
*Configurações → Sistema → Tela → Elementos gráficos* — em
``HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences``.

    python -m projmap.tools.gpu            # aplica e mostra a placa do OpenGL
    python -m projmap.tools.gpu --remover  # volta ao padrão do Windows

Vale para os próximos processos (feche e abra o ProjMap).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
HIGH_PERFORMANCE = "GpuPreference=2;"


def python_executables() -> list[Path]:
    """python.exe/pythonw.exe do ambiente e do interpretador base (o processo do
    venv no Windows repassa a execução para o base, que é quem abre o OpenGL)."""
    exes: set[Path] = set()
    base = Path(getattr(sys, "_base_executable", sys.executable)).parent
    for d in {Path(sys.executable).parent, base, Path(sys.base_prefix), Path(sys.base_prefix) / "Scripts"}:
        for name in ("python.exe", "pythonw.exe"):
            p = d / name
            if p.is_file():
                # O Windows compara o caminho EXATO da imagem do processo: registra
                # o caminho como está (pode passar por um atalho/junção, como o uv
                # faz) e também o resolvido.
                exes.add(Path(str(p)))
                exes.add(p.resolve())
    return sorted(exes)


def set_preference(paths: list[Path], value: str | None = HIGH_PERFORMANCE) -> list[Path]:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        for p in paths:
            if value is None:
                try:
                    winreg.DeleteValue(k, str(p))
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(k, str(p), 0, winreg.REG_SZ, value)
    return paths


def gl_renderer() -> str:
    """Placa usada pelo OpenGL num processo novo (a preferência só vale para novos)."""
    code = "import moderngl; print(moderngl.create_standalone_context().info['GL_RENDERER'])"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    return (out.stdout or out.stderr).strip().splitlines()[-1] if (out.stdout or out.stderr) else "?"


def main(argv: list[str] | None = None) -> None:
    if sys.platform != "win32":
        print("Só é necessário no Windows.")
        return
    ap = argparse.ArgumentParser(prog="projmap.tools.gpu", description=__doc__.split("\n")[0])
    ap.add_argument("--remover", action="store_true", help="volta à escolha padrão do Windows")
    args = ap.parse_args(argv)
    paths = set_preference(python_executables(), None if args.remover else HIGH_PERFORMANCE)
    for p in paths:
        print(("padrão: " if args.remover else "alto desempenho: ") + str(p))
    print("OpenGL agora em:", gl_renderer())


if __name__ == "__main__":
    main()
