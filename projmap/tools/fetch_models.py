"""``python -m projmap.tools.fetch_models`` — baixa o modelo oficial de rosto do MediaPipe.

Salva em ``models/face_landmarker.task`` (Apache-2.0, Google). Com ele no disco,
a webcam local usa o arquivo e o mestre o serve para o celular
(``/api/interact/face-model``) — o show funciona sem internet.
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/"
       "float16/1/face_landmarker.task")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="projmap.tools.fetch_models")
    parser.add_argument("--dest", default="models/face_landmarker.task")
    args = parser.parse_args(argv)
    dest = Path(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    print(f"baixando {URL}")
    with urllib.request.urlopen(URL, timeout=60) as resp, open(tmp, "wb") as out:  # noqa: S310 — URL fixa oficial
        data = resp.read()
        out.write(data)
    if len(data) < 100_000:
        tmp.unlink(missing_ok=True)
        raise SystemExit("download incompleto (arquivo pequeno demais)")
    tmp.replace(dest)
    print(f"ok: {dest} ({len(data) / 1e6:.1f} MB, sha256 {hashlib.sha256(data).hexdigest()[:16]}…)")


if __name__ == "__main__":
    main()
