"""Testes das fábricas de mídia/publisher e do placeholder — sem FFmpeg/rede."""

import pytest

from agents.media.factory import get_image_generator, get_voice_generator
from agents.media.placeholder import (
    _color_from_text,
    estimate_duration,
    placeholder_image,
    placeholder_voice,
)
from publishers.factory import get_publisher
from publishers.youtube import youtube_publisher


def test_image_generator_padrao_e_placeholder():
    assert get_image_generator({}) is placeholder_image
    assert get_image_generator(None) is placeholder_image


def test_voice_generator_padrao_e_placeholder():
    assert get_voice_generator({}) is placeholder_voice


def test_provider_via_config():
    fn = get_image_generator({"image_provider": "stability"})
    assert fn.__name__ == "stability_image"


def test_provider_invalido_levanta():
    with pytest.raises(ValueError):
        get_image_generator({"image_provider": "xpto"})
    with pytest.raises(ValueError):
        get_voice_generator({"voice_provider": "xpto"})


def test_env_tem_prioridade_sobre_config(monkeypatch):
    monkeypatch.setenv("ANE_IMAGE_PROVIDER", "placeholder")
    assert get_image_generator({"image_provider": "stability"}) is placeholder_image


def test_estimate_duration():
    assert estimate_duration("") == 4.0
    assert estimate_duration("uma") == 2.0  # piso
    assert estimate_duration("palavra " * 100) == 10.0  # teto


def test_color_from_text_deterministico():
    a = _color_from_text("gato")
    b = _color_from_text("gato")
    c = _color_from_text("cachorro")
    assert a == b and len(a) == 6
    assert a != c


def test_publisher_none_por_padrao():
    assert get_publisher({}) is None
    assert get_publisher({"publisher": "none"}) is None


def test_publisher_youtube():
    assert get_publisher({"publisher": "youtube"}) is youtube_publisher


def test_publisher_invalido_levanta():
    with pytest.raises(ValueError):
        get_publisher({"publisher": "xpto"})
