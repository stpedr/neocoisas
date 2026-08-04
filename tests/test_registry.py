"""Testes do registry unificado de modelos (sem rede)."""

import pytest

import registry


def test_describe_tem_todas_as_capacidades():
    d = registry.describe({})
    caps = d["capabilities"]
    assert set(caps) == {"text", "image", "voice", "video", "publisher"}


def test_providers_refletem_os_factories():
    caps = registry.describe({})["capabilities"]
    assert "ollama" in caps["text"]["providers"]
    assert "gemini" in caps["text"]["providers"]
    assert "placeholder" in caps["image"]["providers"]
    assert "none" in caps["video"]["providers"]
    assert "youtube" in caps["publisher"]["providers"]


def test_current_padroes(monkeypatch):
    for v in ("ANE_TEXT_PROVIDER", "ANE_IMAGE_PROVIDER", "ANE_VIDEO_PROVIDER", "ANE_PUBLISHER"):
        monkeypatch.delenv(v, raising=False)
    caps = registry.describe({})["capabilities"]
    assert caps["text"]["current"] == {"provider": "ollama", "model": "llama3"}
    assert caps["image"]["current"]["provider"] == "placeholder"
    assert caps["video"]["current"]["provider"] == "none"
    assert caps["publisher"]["current"]["provider"] == "none"


def test_current_por_env(monkeypatch):
    monkeypatch.setenv("ANE_TEXT_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_TEXT_MODEL", "gemini-1.5-pro")
    cur = registry.current("text", {})
    assert cur == {"provider": "gemini", "model": "gemini-1.5-pro"}


def test_current_por_config(monkeypatch):
    monkeypatch.delenv("ANE_IMAGE_PROVIDER", raising=False)
    cur = registry.current("image", {"image_provider": "stability"})
    assert cur["provider"] == "stability"


def test_configured_reflete_env(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert registry.describe({})["capabilities"]["text"]["configured"]["gemini"] is False
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert registry.describe({})["capabilities"]["text"]["configured"]["gemini"] is True


def test_validate():
    assert registry.validate("text", "ollama") is True
    assert registry.validate("image", "xpto") is False
    with pytest.raises(ValueError):
        registry.validate("cap-invalida", "x")
