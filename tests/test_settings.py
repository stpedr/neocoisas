"""Testes da seleção de modelos (persistência + aplicação no ambiente)."""

import os

import settings


def test_set_selection_persiste_e_aplica_env(tmp_path, monkeypatch):
    monkeypatch.delenv("ANE_TEXT_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_TEXT_MODEL", raising=False)
    path = str(tmp_path / "m.json")

    settings.set_selection("text", "gemini", "gemini-1.5-pro", path=path)

    # Aplicou no ambiente
    assert os.environ["ANE_TEXT_PROVIDER"] == "gemini"
    assert os.environ["GEMINI_TEXT_MODEL"] == "gemini-1.5-pro"
    # Persistiu
    data = settings.load(path)
    assert data["text"] == {"provider": "gemini", "model": "gemini-1.5-pro"}


def test_apply_saved_reaplica(tmp_path, monkeypatch):
    monkeypatch.delenv("ANE_IMAGE_PROVIDER", raising=False)
    path = str(tmp_path / "m.json")
    settings.save({"image": {"provider": "stability", "model": None}}, path)

    settings.apply_saved(path)
    assert os.environ["ANE_IMAGE_PROVIDER"] == "stability"


def test_provider_sem_modelo_so_seta_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("ANE_PUBLISHER", raising=False)
    path = str(tmp_path / "m.json")
    settings.set_selection("publisher", "youtube", path=path)
    assert os.environ["ANE_PUBLISHER"] == "youtube"


def test_set_agent_model_e_limpar(tmp_path, monkeypatch):
    monkeypatch.delenv("ANE_AGENT_MODEL_CRITIC", raising=False)
    path = str(tmp_path / "m.json")
    settings.set_agent_model("critic", "llama3:70b", path=path)
    assert os.environ["ANE_AGENT_MODEL_CRITIC"] == "llama3:70b"
    assert settings.load(path)["agents"]["critic"] == "llama3:70b"
    # limpar (model vazio) volta ao global
    settings.set_agent_model("critic", None, path=path)
    assert "ANE_AGENT_MODEL_CRITIC" not in os.environ
    assert "critic" not in settings.load(path).get("agents", {})


def test_apply_saved_aplica_agents(tmp_path, monkeypatch):
    monkeypatch.delenv("ANE_AGENT_MODEL_IDEA", raising=False)
    path = str(tmp_path / "m.json")
    settings.save({"agents": {"idea": "mistral"}}, path)
    settings.apply_saved(path)
    assert os.environ["ANE_AGENT_MODEL_IDEA"] == "mistral"
