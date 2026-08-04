"""Testes do parsing de JSON do OllamaClient (não dependem do Ollama no ar)."""

import json

import pytest

from agents.ollama_client import OllamaClient


def test_extract_json_objeto_puro():
    assert OllamaClient.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_lista_pura():
    assert OllamaClient.extract_json('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]


def test_extract_json_com_cerca_de_codigo():
    raw = '```json\n{"account_profile": "x"}\n```'
    assert OllamaClient.extract_json(raw) == {"account_profile": "x"}


def test_extract_json_com_texto_antes_e_depois():
    raw = 'Claro! Aqui está o JSON:\n{"ok": true}\nEspero ter ajudado.'
    assert OllamaClient.extract_json(raw) == {"ok": True}


def test_extract_json_lista_com_texto_ao_redor():
    raw = 'Segue a lista:\n[{"n": 1}]\nFim.'
    assert OllamaClient.extract_json(raw) == [{"n": 1}]


def test_extract_json_prefere_a_estrutura_que_aparece_primeiro():
    # Objeto aparece antes da lista -> recorta a partir do objeto.
    raw = 'texto {"a": [1, 2, 3]} mais texto'
    assert OllamaClient.extract_json(raw) == {"a": [1, 2, 3]}


def test_extract_json_invalido_levanta():
    with pytest.raises(json.JSONDecodeError):
        OllamaClient.extract_json("isto não é json")
