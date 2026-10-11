"""Controlador Raspberry Pi — opera o Auto Niche Engine por botões e LEDs (GPIO).

Assim como o bot do Telegram, fala com a API (server.py) por HTTP e roda como um
serviço à parte (no próprio Pi ou em qualquer máquina com acesso à API).

Botões (pull-up, ligados ao GND):
    APPROVE   — aprova a ideia pendente mais antiga
    REJECT    — rejeita a ideia pendente mais antiga
    RENDER    — renderiza a aprovada mais antiga ainda sem vídeo
    PUBLISH   — roda o agendador agora (posta as aprovadas: /api/schedule/run-now)
    GENERATE  — autogera ideias com o prompt do agendamento (/api/schedule/autogen-now)

LEDs:
    PENDING   — aceso quando há ideias aguardando revisão
    BUSY      — aceso enquanto uma ação está em andamento
    ERROR     — aceso se a última ação/consulta falhou (API fora, etc.)

Configuração (via .env):
    ANE_API_URL           — base da API (padrão http://localhost:8000)
    ANE_API_KEY           — opcional, se a API exigir
    RPI_BACKEND           — gpiozero (padrão, no Pi) | mock (teclado, para testar no PC)
    RPI_POLL_INTERVAL     — segundos entre consultas de status (padrão 5)
    RPI_PIN_<NOME>        — pino BCM de cada botão/LED (padrões em DEFAULT_PINS)

Padrão do projeto: contrato (`Board`) + factory selecionável (`get_board`). As
funções puras (parse_pins, pick_pending, pick_to_render, led_states) não dependem
de GPIO nem de rede e são cobertas por testes.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Callable, Protocol

import requests

API_URL = os.environ.get("ANE_API_URL", "http://localhost:8000").rstrip("/")
_TIMEOUT = 300

BUTTONS = ("APPROVE", "REJECT", "RENDER", "PUBLISH", "GENERATE")
LEDS = ("PENDING", "BUSY", "ERROR")

# Numeração BCM. Escolhidos para não conflitar com I2C/SPI/UART.
DEFAULT_PINS = {
    "APPROVE": 17,
    "REJECT": 27,
    "RENDER": 22,
    "PUBLISH": 23,
    "GENERATE": 24,
    "PENDING": 5,
    "BUSY": 6,
    "ERROR": 13,
}


def _headers() -> dict:
    key = os.environ.get("ANE_API_KEY")
    return {"X-API-Key": key} if key else {}


# --------------------------------------------------------------- helpers puros
def parse_pins(env: dict) -> dict[str, int]:
    """Pinos BCM a partir de RPI_PIN_<NOME>, com padrões. Rejeita pinos repetidos."""
    pins = {}
    for name, default in DEFAULT_PINS.items():
        raw = env.get(f"RPI_PIN_{name}")
        pins[name] = int(raw) if raw not in (None, "") else default
    usados = list(pins.values())
    if len(set(usados)) != len(usados):
        raise ValueError(f"Pinos GPIO repetidos na configuração: {pins}")
    return pins


def _oldest(ideas: list[dict]) -> list[dict]:
    return sorted(ideas, key=lambda i: i.get("created_at") or "")


def pick_pending(ideas: list[dict]) -> dict | None:
    """Ideia pendente mais antiga (a que os botões aprovar/rejeitar afetam)."""
    ideas = _oldest(ideas)
    return ideas[0] if ideas else None


def pick_to_render(ideas: list[dict]) -> dict | None:
    """Aprovada mais antiga que ainda não tem vídeo renderizado."""
    for idea in _oldest(ideas):
        if not idea.get("video_path"):
            return idea
    return None


def led_states(counts: dict | None, busy: bool, error: bool) -> dict[str, bool]:
    """Estado desejado de cada LED."""
    pending = int((counts or {}).get("pending", 0))
    return {"PENDING": pending > 0, "BUSY": busy, "ERROR": error}


# ------------------------------------------------------------------ API client
def api_counts() -> dict:
    r = requests.get(f"{API_URL}/api/counts", headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def api_list(status: str) -> list[dict]:
    r = requests.get(
        f"{API_URL}/api/ideas", params={"status": status}, headers=_headers(), timeout=30
    )
    r.raise_for_status()
    return r.json().get("ideas", [])


def api_post(path: str) -> dict:
    r = requests.post(f"{API_URL}{path}", headers=_headers(), timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------- hardware (contrato)
class Board(Protocol):
    def on_press(self, name: str, callback: Callable[[], None]) -> None: ...
    def set_led(self, name: str, on: bool) -> None: ...
    def run(self) -> None: ...


class GpiozeroBoard:
    """GPIO real via gpiozero (funciona em Pi 3/4/5 com lgpio)."""

    def __init__(self, pins: dict[str, int]):
        from gpiozero import LED, Button

        self._buttons = {n: Button(pins[n], pull_up=True, bounce_time=0.05) for n in BUTTONS}
        self._leds = {n: LED(pins[n]) for n in LEDS}

    def on_press(self, name, callback):
        self._buttons[name].when_pressed = callback

    def set_led(self, name, on):
        led = self._leds[name]
        led.on() if on else led.off()

    def run(self):
        from signal import pause

        pause()


class MockBoard:
    """Simulação por teclado para testar sem Pi: a/r/d/p/g + Enter; q sai."""

    KEYS = {"a": "APPROVE", "r": "REJECT", "d": "RENDER", "p": "PUBLISH", "g": "GENERATE"}

    def __init__(self, pins: dict[str, int] | None = None):
        self._callbacks: dict[str, Callable[[], None]] = {}
        self._leds = {n: False for n in LEDS}

    def on_press(self, name, callback):
        self._callbacks[name] = callback

    def set_led(self, name, on):
        if self._leds.get(name) != on:
            self._leds[name] = on
            print(f"[mock] LED {name}: {'●' if on else '○'}")

    def press(self, name):
        cb = self._callbacks.get(name)
        if cb:
            cb()

    def run(self):
        print("[mock] teclas: a=aprovar r=rejeitar d=renderizar p=publicar g=gerar q=sair")
        for line in sys.stdin:
            key = line.strip().lower()
            if key == "q":
                break
            if key in self.KEYS:
                self.press(self.KEYS[key])


def get_board(backend: str, pins: dict[str, int]) -> Board:
    backend = (backend or "gpiozero").lower()
    if backend == "gpiozero":
        return GpiozeroBoard(pins)
    if backend == "mock":
        return MockBoard(pins)
    raise ValueError(f"RPI_BACKEND inválido: '{backend}' (use gpiozero | mock).")


# ------------------------------------------------------------------ controlador
class Controller:
    """Liga botões a ações da API e mantém os LEDs sincronizados."""

    def __init__(self, board: Board):
        self.board = board
        self._lock = threading.Lock()
        self.busy = False
        self.error = False
        self.counts: dict = {}

    def refresh_leds(self):
        for name, on in led_states(self.counts, self.busy, self.error).items():
            self.board.set_led(name, on)

    def poll(self):
        try:
            self.counts = api_counts()
            if not self.busy:
                self.error = False
        except Exception as exc:  # noqa: BLE001 - API pode estar reiniciando
            print(f"[rpi] falha ao consultar a API: {exc}")
            self.error = True
        self.refresh_leds()

    def _run_action(self, label: str, fn: Callable[[], str | None]):
        """Executa uma ação por vez (ignora cliques enquanto ocupado)."""
        if not self._lock.acquire(blocking=False):
            print(f"[rpi] ocupado; ignorando {label}")
            return
        self.busy = True
        self.refresh_leds()
        try:
            msg = fn()
            print(f"[rpi] {label}: {msg or 'ok'}")
            self.error = False
        except Exception as exc:  # noqa: BLE001
            print(f"[rpi] erro em {label}: {exc}")
            self.error = True
        finally:
            self.busy = False
            self._lock.release()
            self.poll()

    def _decide(self, action: str) -> str:
        idea = pick_pending(api_list("pending"))
        if idea is None:
            return "nenhuma ideia pendente"
        api_post(f"/api/ideas/{idea['id']}/{action}")
        return f"{idea.get('title', idea['id'])}"

    def _render(self) -> str:
        idea = pick_to_render(api_list("approved"))
        if idea is None:
            return "nenhuma aprovada sem vídeo"
        api_post(f"/api/ideas/{idea['id']}/render")
        return f"{idea.get('title', idea['id'])}"

    def _async(self, label, fn):
        # Callbacks do gpiozero rodam numa thread própria; ações longas (render)
        # não devem bloquear a leitura dos outros botões.
        return lambda: threading.Thread(
            target=self._run_action, args=(label, fn), daemon=True
        ).start()

    def wire(self):
        b = self.board
        b.on_press("APPROVE", self._async("aprovar", lambda: self._decide("approve")))
        b.on_press("REJECT", self._async("rejeitar", lambda: self._decide("reject")))
        b.on_press("RENDER", self._async("renderizar", self._render))
        b.on_press("PUBLISH", self._async("publicar", lambda: str(api_post("/api/schedule/run-now"))))
        b.on_press("GENERATE", self._async("gerar", lambda: str(api_post("/api/schedule/autogen-now"))))


# ------------------------------------------------------------------------ main
def main() -> None:
    pins = parse_pins(dict(os.environ))
    board = get_board(os.environ.get("RPI_BACKEND", "gpiozero"), pins)
    ctrl = Controller(board)
    ctrl.wire()

    interval = float(os.environ.get("RPI_POLL_INTERVAL", "5"))

    def poll_loop():
        while True:
            ctrl.poll()
            time.sleep(interval)

    threading.Thread(target=poll_loop, daemon=True).start()
    print(f"[rpi] controlador iniciado; API em {API_URL}; pinos {pins}")
    board.run()


if __name__ == "__main__":
    main()
