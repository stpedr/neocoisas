"""Testes do loop de melhoria do editor de roteiros (puro, sem Ollama)."""

from agents.editor import refine_loop
from agents.video_pipeline import Scene


def _scenes(n=2):
    return [Scene(f"n{i}", f"v{i}", 3.0) for i in range(n)]


def test_passa_na_primeira_sem_reescrever():
    chamadas = {"rewrite": 0}

    def score(sc):
        return {"score": 9.0, "reason": "ótimo"}

    def rewrite(sc, fb):
        chamadas["rewrite"] += 1
        return sc

    r = refine_loop(_scenes(), score, rewrite, min_score=6.0, max_iterations=3)
    assert r["passed"] is True
    assert r["iterations"] == 0
    assert chamadas["rewrite"] == 0
    assert len(r["history"]) == 1


def test_melhora_ao_longo_das_iteracoes():
    notas = iter([3.0, 5.0, 8.0])  # inicial, após 1ª, após 2ª reescrita

    def score(sc):
        return {"score": next(notas), "reason": "melhore o gancho"}

    def rewrite(sc, fb):
        return sc + [Scene("nova", "v", 2.0)]

    r = refine_loop(_scenes(1), score, rewrite, min_score=6.0, max_iterations=3)
    assert r["passed"] is True
    assert r["iterations"] == 2
    assert r["score"] == 8.0
    assert len(r["history"]) == 3


def test_para_no_maximo_de_iteracoes():
    def score(sc):
        return {"score": 2.0, "reason": "fraco"}

    def rewrite(sc, fb):
        return sc

    r = refine_loop(_scenes(), score, rewrite, min_score=8.0, max_iterations=2)
    assert r["passed"] is False
    assert r["iterations"] == 2


def test_rewrite_vazio_mantem_cenas():
    scenes = _scenes(2)
    notas = iter([1.0, 1.0])

    def score(sc):
        return {"score": next(notas), "reason": "x"}

    def rewrite(sc, fb):
        return []  # não conseguiu reescrever

    r = refine_loop(scenes, score, rewrite, min_score=6.0, max_iterations=1)
    assert r["scenes"] is scenes  # manteve o original
