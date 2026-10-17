"""Lançador (lógica sem janela) e instalador do atalho."""

import sys

import pytest

from projmap.desktop import core
from projmap.desktop.core import Settings, list_shows, master_command, remote_url_from_log, safe_show_name


def test_preferencias_salvam_e_carregam(tmp_path):
    p = tmp_path / "launcher.json"
    s = Settings(shows_dir=str(tmp_path), last_show="Natal", output="window", lan=False)
    core.save_settings(s, p)
    assert core.load_settings(p) == s
    p.write_text("{lixo")
    assert core.load_settings(p) == Settings()  # arquivo corrompido não trava o lançador
    p.write_text('{"campo_que_nao_existe": 1, "port": 9000}')
    assert core.load_settings(p).port == 9000


def test_lista_shows_validos_mais_recentes_primeiro(tmp_path):
    import os
    import time

    for i, name in enumerate(["Antigo", "Novo"]):
        d = tmp_path / f"{name}.projmap"
        d.mkdir()
        (d / "project.json").write_text("{}")
        os.utime(d / "project.json", (time.time() + i, time.time() + i))
    (tmp_path / "SemProjeto.projmap").mkdir()
    assert list_shows(tmp_path) == ["Novo", "Antigo"]
    assert list_shows(tmp_path / "nao-existe") == []


def test_nome_seguro_para_pasta():
    assert safe_show_name('Natal: "fachada"/2026?') == "Natal fachada2026"
    assert safe_show_name("   ") == "Meu show"


@pytest.mark.parametrize("output, expect", [("display", ["--display", "2"]), ("window", ["--windowed"]), ("none", ["--no-output"])])
def test_comando_do_mestre(tmp_path, output, expect):
    s = Settings(shows_dir=str(tmp_path), output=output, display=2, lan=True, token="abc", open_browser=True,
                 extra_library=["G:/Meu Drive"])
    cmd = master_command(s, "Natal", python="python")
    assert cmd[:3] == ["python", "-m", "projmap.master"]
    assert str(tmp_path / "Natal.projmap") in cmd
    i = cmd.index(expect[0])
    assert cmd[i:i + len(expect)] == expect
    assert cmd[cmd.index("--host") + 1] == "0.0.0.0" and cmd[cmd.index("--token") + 1] == "abc"
    assert "--open" in cmd and cmd[cmd.index("--library") + 1] == "G:/Meu Drive"


def test_sem_celular_nao_expoe_na_rede(tmp_path):
    cmd = master_command(Settings(shows_dir=str(tmp_path), lan=False, token="x"), "S", python="python")
    assert "--host" not in cmd and "--token" not in cmd


def test_link_do_celular_no_log():
    line = "2026-10-11 INFO projmap.master: remote no celular (mesma rede): http://192.168.1.12:8100/remote/#t=AbC_1"
    assert remote_url_from_log(line) == "http://192.168.1.12:8100/remote/#t=AbC_1"
    assert remote_url_from_log("outra linha") is None


def test_icone_multitamanho(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    from projmap.desktop.install import make_icon

    ico = make_icon(tmp_path / "x.ico")
    with Image.open(ico) as im:
        assert (256, 256) in im.info.get("sizes", {(256, 256)}) or im.size == (256, 256)


@pytest.mark.skipif(sys.platform != "win32", reason="atalho .lnk só no Windows")
def test_cria_atalho_windows(tmp_path):
    from projmap.desktop.install import create_windows_shortcut, make_icon

    lnk = tmp_path / "menu" / "ProjMap.lnk"
    create_windows_shortcut(lnk, sys.executable, "-m projmap.desktop", tmp_path, make_icon(tmp_path / "i.ico"))
    assert lnk.is_file() and lnk.stat().st_size > 0


def test_comando_com_webcam_e_celular(tmp_path):
    cmd = master_command(Settings(shows_dir=str(tmp_path), interact=True, sensor="webcam", camera="C920"), "S", python="python")
    assert cmd[cmd.index("--sensor") + 1] == "webcam" and cmd[cmd.index("--camera") + 1] == "C920"
    cmd = master_command(Settings(shows_dir=str(tmp_path), interact=True, sensor="phone"), "S", python="python")
    assert cmd[cmd.index("--sensor") + 1] == "phone" and "--camera" not in cmd
    assert "--sensor" not in master_command(Settings(shows_dir=str(tmp_path)), "S", python="python")


def test_interacao_so_quando_pedida(tmp_path):
    off = master_command(Settings(shows_dir=str(tmp_path)), "S", python="python")
    assert "--no-interact" in off and "--sensor" not in off  # padrão: show sem interação

    on = master_command(Settings(shows_dir=str(tmp_path), interact=True, sensor="phone"), "S", python="python")
    assert "--no-interact" not in on
    assert on[on.index("--sensor") + 1] == "phone" and "--adb" in on  # celular pelo cabo

    sim = master_command(Settings(shows_dir=str(tmp_path), interact=True, sensor="sim"), "S", python="python")
    assert sim[sim.index("--sensor") + 1] == "sim" and "--adb" not in sim

    weird = master_command(Settings(shows_dir=str(tmp_path), interact=True, sensor="kinect9000"), "S", python="python")
    assert weird[weird.index("--sensor") + 1] == "phone"  # valor estranho no json não quebra o mestre


def test_linux_desktop_entry_e_atalhos(tmp_path, monkeypatch):
    from projmap.desktop.install import _linux_shortcut_paths, linux_desktop_entry

    monkeypatch.setenv("XDG_DESKTOP_DIR", str(tmp_path))
    paths = _linux_shortcut_paths(desktop=True)
    assert len(paths) == 2
    assert paths[1] == tmp_path / "projmap.desktop"
    entry = linux_desktop_entry("/opt/my venv/bin/python", tmp_path / "icon.png")
    assert 'Exec="/opt/my venv/bin/python" -m projmap.desktop' in entry


def test_linux_pulseaudio_monitor_fallback():
    from types import SimpleNamespace
    from projmap.effects.audio import _pick_capture_device

    monitor_mic = SimpleNamespace(name="Monitor of Built-in Audio Analog Stereo", id="alsa_output.pci.monitor", isloopback=True)
    fake_sc = SimpleNamespace(
        default_speaker=lambda: SimpleNamespace(name="Built-in Audio", id="alsa_output.pci"),
        get_microphone=lambda _q, include_loopback=True: (_ for _ in ()).throw(RuntimeError("sem match direto")),
        all_microphones=lambda include_loopback=True: [monitor_mic],
        default_microphone=lambda: SimpleNamespace(name="Mic padrao", id="mic0"),
    )
    mic, label = _pick_capture_device(fake_sc)
    assert mic is monitor_mic
    assert "Monitor" in label

