"""Testes do parser do agente crítico (sem Ollama)."""

from agents.critic import parse_critique


def test_score_e_reason():
    out = parse_critique({"score": 8.5, "reason": "Gancho forte"})
    assert out == {"score": 8.5, "reason": "Gancho forte"}


def test_clamp_e_arredonda():
    assert parse_critique({"score": 15})["score"] == 10.0
    assert parse_critique({"score": -3})["score"] == 0.0
    assert parse_critique({"score": 7.26})["score"] == 7.3


def test_score_invalido_vira_zero():
    assert parse_critique({"score": "abc"})["score"] == 0.0
    assert parse_critique({})["score"] == 0.0


def test_nomes_alternativos():
    out = parse_critique({"nota": 6, "motivo": "ok"})
    assert out["score"] == 6.0
    assert out["reason"] == "ok"
