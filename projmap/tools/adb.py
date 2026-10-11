"""Celular por ADB: liga o celular ao mestre pelo cabo USB.

``adb reverse tcp:8100 tcp:8100`` faz o ``localhost:8100`` *do celular* apontar
para o mestre no PC. Três ganhos:

1. ``localhost`` é **contexto seguro** para o navegador: a câmera
   (``getUserMedia``) funciona em ``http://`` — sem certificado, sem HTTPS;
2. o tráfego vai pelo cabo, sem depender do Wi-Fi do local;
3. o mestre continua escutando só em ``127.0.0.1`` (nada exposto na rede).

Uso direto::

    python -m projmap.tools.adb            # reverse + abre /sensor no celular
    python -m projmap.tools.adb --no-open  # só o reverse

ou ``python -m projmap.master ... --sensor phone --adb``.

Requer o **Android Platform Tools** (``adb``) instalado e a "Depuração USB"
ligada no celular (Opções do desenvolvedor). Este módulo só chama o ``adb``
oficial do usuário; nada é baixado ou executado além disso.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional


class AdbError(RuntimeError):
    pass


@dataclass
class Device:
    serial: str
    state: str  # device | unauthorized | offline
    model: str = ""


def find_adb() -> str:
    path = os.environ.get("ADB") or shutil.which("adb")
    if not path:
        raise AdbError(
            "adb não encontrado. Instale o Android Platform Tools e coloque no PATH "
            "(ou defina a variável ADB com o caminho do executável)."
        )
    return path


def _run(args: list[str], adb: Optional[str] = None, timeout: float = 10.0) -> str:
    cmd = [adb or find_adb(), *args]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdbError(f"falha ao rodar {' '.join(cmd)}: {exc}") from exc
    if out.returncode != 0:
        raise AdbError((out.stderr or out.stdout).strip() or f"adb saiu com código {out.returncode}")
    return out.stdout


def devices(adb: Optional[str] = None) -> list[Device]:
    found = []
    for line in _run(["devices", "-l"], adb).splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        model = next((p.split(":", 1)[1] for p in parts[2:] if p.startswith("model:")), "")
        found.append(Device(parts[0], parts[1], model))
    return found


def pick_device(adb: Optional[str] = None, serial: Optional[str] = None) -> Device:
    devs = devices(adb)
    if serial:
        devs = [d for d in devs if d.serial == serial]
    if not devs:
        raise AdbError("nenhum celular encontrado: conecte o cabo e ligue a Depuração USB")
    ready = [d for d in devs if d.state == "device"]
    if not ready:
        states = ", ".join(f"{d.serial}={d.state}" for d in devs)
        raise AdbError(f"celular não autorizado ({states}): aceite o aviso de depuração USB na tela do celular")
    if len(ready) > 1 and not serial:
        raise AdbError("mais de um celular conectado: use --serial " + " | ".join(d.serial for d in ready))
    return ready[0]


def reverse(port: int, device: Device, adb: Optional[str] = None) -> None:
    _run(["-s", device.serial, "reverse", f"tcp:{port}", f"tcp:{port}"], adb)


def open_url(url: str, device: Device, adb: Optional[str] = None) -> None:
    _run(["-s", device.serial, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url], adb)


def connect_phone(port: int = 8100, open_page: bool = True, serial: Optional[str] = None,
                  path: str = "/sensor/") -> Device:
    """Reverse da porta do mestre e (opcional) abre a página do sensor no celular."""
    adb = find_adb()
    dev = pick_device(adb, serial)
    reverse(port, dev, adb)
    if open_page:
        open_url(f"http://localhost:{port}{path}", dev, adb)
    return dev


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="projmap.tools.adb", description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--serial", default=None, help="qual celular (se houver mais de um)")
    parser.add_argument("--no-open", action="store_true", help="só faz o reverse, não abre a página")
    args = parser.parse_args(argv)
    try:
        dev = connect_phone(args.port, not args.no_open, args.serial)
    except AdbError as exc:
        raise SystemExit(f"ADB: {exc}") from None
    print(f"Celular {dev.model or dev.serial} ligado: localhost:{args.port} → mestre"
          + ("" if args.no_open else f"; página http://localhost:{args.port}/sensor/ aberta"))


if __name__ == "__main__":
    main()
