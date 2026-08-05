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


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_available_models_descobre_ollama(monkeypatch):
    monkeypatch.setattr(
        registry.requests, "get",
        lambda *a, **k: _Resp({"models": [{"name": "llama3"}, {"name": "mistral"}]}),
    )
    av = registry.available_models({})
    assert av["text"]["ollama"] == ["llama3", "mistral"]
    assert "gemini-2.5-flash" in av["text"]["gemini"]


def test_available_models_fallback_quando_ollama_cai(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("ollama offline")

    monkeypatch.setattr(registry.requests, "get", boom)
    av = registry.available_models({})
    assert av["text"]["ollama"] == registry.KNOWN_MODELS["text"]["ollama"]


def test_agent_models_padrao_usa_global(monkeypatch):
    for a in registry.AGENTS:
        monkeypatch.delenv(f"ANE_AGENT_MODEL_{a.upper()}", raising=False)
    monkeypatch.delenv("ANE_TEXT_PROVIDER", raising=False)
    am = registry.agent_models({"ollama_model": "llama3"})
    assert am["critic"] == {"model": "llama3", "override": False}


def test_agent_models_override_por_env(monkeypatch):
    monkeypatch.setenv("ANE_AGENT_MODEL_CRITIC", "llama3:70b")
    am = registry.agent_models({"ollama_model": "llama3"})
    assert am["critic"] == {"model": "llama3:70b", "override": True}
    assert am["idea"]["override"] is False  # os outros seguem global
