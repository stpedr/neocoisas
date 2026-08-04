"""Testes puros do titulador, tradutor e analista (sem Ollama)."""

import pytest

from agents.analyst import parse_analysis
from agents.titler import parse_titles
from agents.translator import parse_translations


# ------------------------------------------------------------------ titulador
def test_parse_titles_lista_de_strings():
    assert parse_titles(["A", " B ", ""]) == ["A", "B"]


def test_parse_titles_dict_e_objetos():
    assert parse_titles({"titles": [{"title": "X"}, {"titulo": "Y"}]}) == ["X", "Y"]


def test_parse_titles_invalido():
    assert parse_titles(123) == []


# -------------------------------------------------------------------- tradutor
def test_parse_translations_ajusta_tamanho():
    assert parse_translations(["a", "b"], 2) == ["a", "b"]
    assert parse_translations(["a"], 3) == ["a", "", ""]          # preenche
    assert parse_translations(["a", "b", "c"], 2) == ["a", "b"]   # trunca


def test_parse_translations_dict():
    assert parse_translations({"translations": ["x", "y"]}, 2) == ["x", "y"]


# -------------------------------------------------------------------- analista
def test_parse_analysis_normaliza():
    out = parse_analysis({"insights": "cresceu", "recommendations": ["mais memes", ""]})
    assert out["insights"] == "cresceu"
    assert out["recommendations"] == ["mais memes"]


def test_parse_analysis_recs_string():
    out = parse_analysis({"resumo": "ok", "recomendacoes": "faça shorts"})
    assert out["recommendations"] == ["faça shorts"]


def test_parse_analysis_vazio():
    assert parse_analysis("nada") == {"insights": "", "recommendations": []}
