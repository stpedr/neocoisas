"""Testes das funções puras do bot do Telegram (sem a lib do Telegram/rede)."""

from telegram_bot import format_idea, is_allowed, parse_callback


def test_parse_callback():
    assert parse_callback("approve:abc123") == ("approve", "abc123")
    assert parse_callback("render:xyz") == ("render", "xyz")


def test_parse_callback_sem_id():
    assert parse_callback("noop") == ("noop", "")


def test_is_allowed_sem_lista_libera_todos():
    assert is_allowed(123, None) is True
    assert is_allowed(123, "") is True


def test_is_allowed_com_lista():
    assert is_allowed(123, "123,456") is True
    assert is_allowed("456", "123, 456") is True
    assert is_allowed(999, "123,456") is False


def test_format_idea():
    idea = {
        "title": "Gatos no espaço",
        "mode": "manual",
        "scenes": [
            {"narration": "Cena um"},
            {"narration": "Cena dois"},
        ],
    }
    texto = format_idea(idea)
    assert "Gatos no espaço" in texto
    assert "2 cenas" in texto
    assert "1. Cena um" in texto
    assert "2. Cena dois" in texto


def test_format_idea_com_video():
    idea = {"title": "T", "mode": "auto", "video_path": "x.mp4", "scenes": []}
    assert "vídeo renderizado" in format_idea(idea)
