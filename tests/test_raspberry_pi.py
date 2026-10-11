"""Testes do controlador Raspberry Pi (sem GPIO nem rede)."""

import pytest

import raspberry_pi as rpi


def test_parse_pins_padroes():
    assert rpi.parse_pins({}) == rpi.DEFAULT_PINS


def test_parse_pins_override():
    pins = rpi.parse_pins({"RPI_PIN_APPROVE": "26", "RPI_PIN_ERROR": ""})
    assert pins["APPROVE"] == 26
    assert pins["ERROR"] == rpi.DEFAULT_PINS["ERROR"]


def test_parse_pins_repetidos():
    with pytest.raises(ValueError):
        rpi.parse_pins({"RPI_PIN_APPROVE": "27"})  # mesmo pino do REJECT


def test_pick_pending_mais_antiga():
    ideas = [{"id": "b", "created_at": "2026-02"}, {"id": "a", "created_at": "2026-01"}]
    assert rpi.pick_pending(ideas)["id"] == "a"
    assert rpi.pick_pending([]) is None


def test_pick_to_render_ignora_ja_renderizadas():
    ideas = [
        {"id": "a", "created_at": "1", "video_path": "x.mp4"},
        {"id": "b", "created_at": "2"},
    ]
    assert rpi.pick_to_render(ideas)["id"] == "b"
    assert rpi.pick_to_render(ideas[:1]) is None


def test_led_states():
    assert rpi.led_states({"pending": 2}, False, False) == {
        "PENDING": True, "BUSY": False, "ERROR": False,
    }
    assert rpi.led_states(None, True, True) == {"PENDING": False, "BUSY": True, "ERROR": True}


def test_get_board_mock_e_invalido():
    assert isinstance(rpi.get_board("mock", rpi.DEFAULT_PINS), rpi.MockBoard)
    with pytest.raises(ValueError):
        rpi.get_board("foo", rpi.DEFAULT_PINS)


def test_controller_aprova_pendente(monkeypatch):
    chamadas = []
    monkeypatch.setattr(rpi, "api_list", lambda s: [{"id": "x1", "title": "T", "created_at": "1"}])
    monkeypatch.setattr(rpi, "api_post", lambda p: chamadas.append(p) or {})
    monkeypatch.setattr(rpi, "api_counts", lambda: {"pending": 0})

    board = rpi.MockBoard()
    ctrl = rpi.Controller(board)
    ctrl._run_action("aprovar", lambda: ctrl._decide("approve"))

    assert chamadas == ["/api/ideas/x1/approve"]
    assert ctrl.error is False and ctrl.busy is False


def test_controller_erro_acende_led(monkeypatch):
    def falha(*_):
        raise RuntimeError("API fora")

    monkeypatch.setattr(rpi, "api_list", falha)
    monkeypatch.setattr(rpi, "api_counts", falha)

    board = rpi.MockBoard()
    ctrl = rpi.Controller(board)
    ctrl._run_action("aprovar", lambda: ctrl._decide("approve"))

    assert ctrl.error is True
    assert board._leds["ERROR"] is True
