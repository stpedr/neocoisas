"""Testes puros do provider ComfyUI (injeção de prompt e parse da saída)."""

from agents.media.comfyui import find_output_files, inject_prompt


def test_inject_prompt_substitui_e_faz_parse():
    template = '{"6": {"inputs": {"text": "%prompt%"}, "class_type": "CLIPTextEncode"}}'
    wf = inject_prompt(template, "gatos no espaço")
    assert wf["6"]["inputs"]["text"] == "gatos no espaço"


def test_inject_prompt_escapa_aspas():
    template = '{"6": {"inputs": {"text": "%prompt%"}}}'
    wf = inject_prompt(template, 'ele disse "oi"')
    assert wf["6"]["inputs"]["text"] == 'ele disse "oi"'


def test_find_output_files_imagens_e_videos():
    hist = {
        "outputs": {
            "9": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]},
            "12": {"gifs": [{"filename": "v.mp4", "subfolder": "sub", "type": "output"}]},
        }
    }
    files = find_output_files(hist)
    nomes = {f["filename"] for f in files}
    assert nomes == {"a.png", "v.mp4"}


def test_find_output_files_vazio():
    assert find_output_files({"outputs": {}}) == []
    assert find_output_files({}) == []
