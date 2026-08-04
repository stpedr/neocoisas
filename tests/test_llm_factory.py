"""Testes da factory de LLM de texto (seleção de provider) — sem rede."""

import json

import pytest

from agents.llm import get_text_client, resolve_provider
from agents.llm.gemini_text import GeminiTextClient
from agents.ollama_client import OllamaClient


def _cfg(tmp_path, **vals):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(vals), encoding="utf-8")
    return str(p)


def test_resolve_padrao_ollama(tmp_path, monkeypatch):
    monkeypatch.delenv("ANE_TEXT_PROVIDER", raising=False)
    assert resolve_provider(_cfg(tmp_path)) == "ollama"


def test_resolve_por_config(tmp_path, monkeypatch):
    monkeypatch.delenv("ANE_TEXT_PROVIDER", raising=False)
    assert resolve_provider(_cfg(tmp_path, text_provider="gemini")) == "gemini"


def test_env_tem_prioridade(tmp_path, monkeypatch):
    monkeypatch.setenv("ANE_TEXT_PROVIDER", "gemini")
    assert resolve_provider(_cfg(tmp_path, text_provider="ollama")) == "gemini"


def test_get_client_ollama(tmp_path, monkeypatch):
    monkeypatch.setenv("ANE_TEXT_PROVIDER", "ollama")
    client = get_text_client(_cfg(tmp_path, ollama_base_url="http://x:11434", ollama_model="llama3"))
    assert isinstance(client, OllamaClient)


def test_get_client_gemini(tmp_path, monkeypatch):
    monkeypatch.setenv("ANE_TEXT_PROVIDER", "gemini")
    client = get_text_client(_cfg(tmp_path))
    assert isinstance(client, GeminiTextClient)
    assert hasattr(client, "generate") and hasattr(client, "extract_json")


def test_provider_invalido(tmp_path, monkeypatch):
    monkeypatch.setenv("ANE_TEXT_PROVIDER", "xpto")
    with pytest.raises(ValueError):
        get_text_client(_cfg(tmp_path))


def test_gemini_generate_sem_chave_erro(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from agents.llm import OllamaError

    with pytest.raises(OllamaError):
        GeminiTextClient(_cfg(tmp_path)).generate("oi")
