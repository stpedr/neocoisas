"""Câmeras USB para o sensor de webcam (ex.: Logitech C920).

Problemas que este módulo resolve:

- **Qual câmera?** O OpenCV só conhece índices (0, 1, 2…), e câmeras virtuais
  (OBS, DroidCam, Animaze…) ocupam índices. Aqui as câmeras são listadas
  **pelo nome** (DirectShow no Windows, ``/sys/class/video4linux`` no Linux),
  e ``"auto"`` escolhe uma C920/Logitech física, ignorando as virtuais.
- **Fluidez da C920.** No modo padrão (YUY2) ela entrega 1080p a ~5 fps. Em
  **MJPG 1280×720 ela dá 30 fps**, o que a interação precisa. O foco
  automático é desligado: ele "caça" quando alguém se mexe e borra o rosto.

A ordem do DirectShow é a mesma dos índices do ``cv2.CAP_DSHOW``.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

log = logging.getLogger(__name__)

VIRTUAL_HINTS = ("virtual", "droidcam", "animaze", "obs", "streamfog", "snap camera", "nvidia broadcast",
                 "xsplit", "manycam", "iriun", "epoccam", "camo")
PREFERRED_HINTS = ("c920", "c922", "c930", "c925", "brio", "logitech", "streamcam")


@dataclass(frozen=True)
class CameraInfo:
    index: int
    name: str

    @property
    def virtual(self) -> bool:
        n = self.name.lower()
        return any(h in n for h in VIRTUAL_HINTS)

    @property
    def preferred(self) -> bool:
        n = self.name.lower()
        return any(h in n for h in PREFERRED_HINTS)


_DSHOW_RE = re.compile(r'\]\s+"(?P<name>[^"]+)"\s+\((?P<kind>video|audio|none)\)')


def parse_dshow_list(text: str) -> list[str]:
    """Nomes das câmeras na saída de ``ffmpeg -list_devices true -f dshow -i dummy``.

    Só entram dispositivos de vídeo, na ordem em que aparecem (= índice CAP_DSHOW).
    """
    return [m.group("name") for m in _DSHOW_RE.finditer(text) if m.group("kind") == "video"]


def list_cameras() -> list[CameraInfo]:
    if sys.platform == "win32":
        ff = shutil.which("ffmpeg")
        if ff:
            try:
                out = subprocess.run([ff, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                names = parse_dshow_list(out.stderr + out.stdout)
                if names:
                    return [CameraInfo(i, n) for i, n in enumerate(names)]
            except (OSError, subprocess.TimeoutExpired):
                pass
        return _probe_indices()
    sys_v4l = Path("/sys/class/video4linux")
    if sys_v4l.is_dir():
        cams = []
        for d in sorted(sys_v4l.glob("video*"), key=lambda p: int(re.sub(r"\D", "", p.name) or 0)):
            try:
                cams.append(CameraInfo(int(re.sub(r"\D", "", d.name)), (d / "name").read_text().strip()))
            except (OSError, ValueError):
                continue
        if cams:
            return cams
    return _probe_indices()


def _probe_indices(n: int = 5) -> list[CameraInfo]:
    """Sem nomes disponíveis: testa os primeiros índices."""
    import cv2

    found = []
    for i in range(n):
        cap = cv2.VideoCapture(i, _backend())
        if cap.isOpened():
            found.append(CameraInfo(i, f"Câmera {i}"))
        cap.release()
    return found


def choose_camera(cams: list[CameraInfo], want: Union[str, int, None] = "auto") -> Optional[CameraInfo]:
    """``want``: índice, parte do nome (ex.: ``"C920"``) ou ``"auto"``.

    ``auto``: a primeira preferida (C920/Logitech/BRIO) física; senão a primeira
    física; senão qualquer uma.
    """
    if not cams:
        return None
    if isinstance(want, int) or (isinstance(want, str) and want.strip().isdigit()):
        idx = int(want)
        return next((c for c in cams if c.index == idx), CameraInfo(idx, f"Câmera {idx}"))
    w = (want or "auto").strip().lower()
    if w != "auto":
        return next((c for c in cams if w in c.name.lower()), None)
    physical = [c for c in cams if not c.virtual]
    return next((c for c in physical if c.preferred), None) or (physical[0] if physical else cams[0])


def _backend() -> int:
    import cv2

    return cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


def open_camera(index: int, width: int = 1280, height: int = 720, fps: int = 30, mjpg: bool = True,
                autofocus: bool = False):
    """Abre a câmera já configurada. Devolve ``(cap, (w, h, fps))`` com o que foi obtido."""
    import cv2

    cap = cv2.VideoCapture(index, _backend())
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"não abriu a câmera {index}")
    if mjpg:  # precisa vir antes da resolução no DirectShow
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # sempre o quadro mais novo (menos atraso)
    if not autofocus:
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
    got = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
           float(cap.get(cv2.CAP_PROP_FPS) or 0))
    return cap, got


def parse_size(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{2,5})\s*[x×]\s*(\d{2,5})\s*", text or "")
    if not m:
        raise ValueError(f"tamanho inválido: {text!r} (use LARGURAxALTURA, ex.: 1280x720)")
    return int(m.group(1)), int(m.group(2))


if __name__ == "__main__":  # python -m projmap.interact.cameras
    cams = list_cameras()
    pick = choose_camera(cams, "auto")
    print("Câmeras encontradas:" if cams else "Nenhuma câmera encontrada.")
    for c in cams:
        tags = ["virtual" if c.virtual else "física"] + (["recomendada"] if c.preferred else [])
        mark = "  <-- 'auto' usa esta" if pick and c.index == pick.index else ""
        print(f"  {c.index}: {c.name}  ({', '.join(tags)}){mark}")
