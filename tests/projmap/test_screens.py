"""Escolha da tela de saída: ordem estável e "auto" = projetor."""

import pytest

from projmap.desktop.core import Settings, load_settings
from projmap.node.screens import choose_screen, order_screens

# Arranjo real que causou o bug: o Windows listou o projetor ANTES do notebook.
REAL = [(2560, 0, 1024, 768, "projetor"), (0, 0, 2560, 1600, "notebook")]


def test_principal_sempre_primeiro_e_auto_e_o_projetor():
    s = order_screens(REAL)
    assert [x.handle for x in s] == ["notebook", "projetor"] and s[0].primary
    assert choose_screen(s, "auto").handle == "projetor"
    assert choose_screen(s, "0").handle == "notebook" and choose_screen(s, 1).handle == "projetor"
    assert choose_screen(s, "principal").handle == "notebook"
    assert choose_screen(s, 5) is None


def test_uma_tela_so_e_tres_telas():
    one = order_screens([(0, 0, 1920, 1080, "a")])
    assert choose_screen(one, "auto").handle == "a"
    three = order_screens([(3840, 0, 800, 600, "dir"), (0, 0, 1920, 1080, "p"), (-1280, 0, 1280, 720, "esq")])
    assert [x.handle for x in three] == ["p", "esq", "dir"]
    assert choose_screen(three, "auto").handle == "esq"
    with pytest.raises(ValueError):
        choose_screen(three, "lado")
    assert choose_screen([], "auto") is None


def test_preferencia_antiga_numerica_vira_auto(tmp_path):
    p = tmp_path / "l.json"
    p.write_text('{"display": 2}')
    assert load_settings(p).display == "auto"
    p.write_text('{"display": "1"}')
    assert load_settings(p).display == "1"
    assert Settings().display == "auto"


def test_horario_do_mediapipe_sempre_cresce():
    from projmap.interact.sensors import next_timestamp_ms

    assert next_timestamp_ms(-1, 0.0) == 0
    assert next_timestamp_ms(33, 0.0335) == 34  # mesmo milissegundo: avança 1
    assert next_timestamp_ms(34, 0.1) == 100
    assert next_timestamp_ms(500, 0.2) == 501  # relógio "voltou": continua crescendo
