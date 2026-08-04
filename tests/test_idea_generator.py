"""Testes da normalização de conceitos (build_idea_concepts) — sem Ollama."""

from agents.idea_generator import build_idea_concepts


def test_dicts_com_campos_padrao():
    raw = [
        {"title": "Gancho 1", "angle": "abordagem 1"},
        {"title": "Gancho 2", "angle": "abordagem 2"},
    ]
    out = build_idea_concepts(raw)
    assert out == raw


def test_nomes_alternativos_de_campo():
    raw = [{"titulo": "T", "descricao": "D"}]
    out = build_idea_concepts(raw)
    assert out == [{"title": "T", "angle": "D"}]


def test_itens_string_viram_conceito_sem_angulo():
    out = build_idea_concepts(["Ideia solta"])
    assert out == [{"title": "Ideia solta", "angle": ""}]


def test_descarta_sem_titulo_e_nao_suportados():
    raw = [
        {"angle": "sem título"},  # descartado
        123,                       # ignorado
        {"title": "  "},          # título vazio -> descartado
        {"title": "válido"},
    ]
    out = build_idea_concepts(raw)
    assert out == [{"title": "válido", "angle": ""}]


def test_faz_strip():
    out = build_idea_concepts([{"title": "  T  ", "angle": "  A  "}])
    assert out == [{"title": "T", "angle": "A"}]
