"""Testes da conversão de roteiro em cenas (build_scenes) — sem Ollama."""

from agents.script_writer import (
    DEFAULT_SCENE_DURATION_S,
    MAX_SCENE_DURATION_S,
    MIN_SCENE_DURATION_S,
    build_scenes,
)
from agents.video_pipeline import Scene


def test_build_scenes_campos_padrao():
    raw = [
        {"narration": "Oi", "visual_prompt": "a cat", "duration_s": 3},
        {"narration": "Tchau", "visual_prompt": "a dog", "duration_s": 5},
    ]
    scenes = build_scenes(raw)
    assert len(scenes) == 2
    assert all(isinstance(s, Scene) for s in scenes)
    assert scenes[0].narration == "Oi"
    assert scenes[0].visual_prompt == "a cat"
    assert scenes[0].duration_s == 3.0


def test_build_scenes_nomes_alternativos_de_campo():
    raw = [{"texto": "Fala", "imagem": "uma paisagem", "duracao": 4}]
    scenes = build_scenes(raw)
    assert len(scenes) == 1
    assert scenes[0].narration == "Fala"
    assert scenes[0].visual_prompt == "uma paisagem"
    assert scenes[0].duration_s == 4.0


def test_build_scenes_descarta_itens_vazios_e_nao_dict():
    raw = [
        {"narration": "", "visual_prompt": ""},  # vazio -> descartado
        "não é dict",                              # ignorado
        {"narration": "válida", "visual_prompt": "algo"},
    ]
    scenes = build_scenes(raw)
    assert len(scenes) == 1
    assert scenes[0].narration == "válida"


def test_build_scenes_duracao_invalida_vira_padrao():
    raw = [{"narration": "n", "visual_prompt": "v", "duration_s": "abc"}]
    assert build_scenes(raw)[0].duration_s == DEFAULT_SCENE_DURATION_S


def test_build_scenes_duracao_ausente_vira_padrao():
    raw = [{"narration": "n", "visual_prompt": "v"}]
    assert build_scenes(raw)[0].duration_s == DEFAULT_SCENE_DURATION_S


def test_build_scenes_duracao_fora_da_faixa_e_ajustada():
    curta = build_scenes([{"narration": "n", "visual_prompt": "v", "duration_s": 0.1}])
    longa = build_scenes([{"narration": "n", "visual_prompt": "v", "duration_s": 999}])
    assert curta[0].duration_s == MIN_SCENE_DURATION_S
    assert longa[0].duration_s == MAX_SCENE_DURATION_S


def test_build_scenes_aceita_cena_so_com_narracao():
    scenes = build_scenes([{"narration": "só fala"}])
    assert len(scenes) == 1
    assert scenes[0].visual_prompt == ""
