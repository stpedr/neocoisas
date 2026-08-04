"""Teste de integração do VideoPipeline (mockando FFmpeg e os geradores)."""

from pathlib import Path

import pytest

from agents import video_pipeline
from agents.video_pipeline import Scene, VideoJob, VideoPipeline


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    """Substitui subprocess.run e shutil.which — nenhum FFmpeg real é chamado."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        dest = Path(cmd[-1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake")

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(video_pipeline.subprocess, "run", fake_run)
    monkeypatch.setattr(video_pipeline.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    return calls


def _generators():
    def image(prompt, dest):
        Path(dest).write_bytes(b"img")
        return Path(dest)

    def voice(text, dest):
        Path(dest).write_bytes(b"aud")
        return Path(dest)

    return image, voice


def test_render_gera_arquivo_e_chama_ffmpeg(fake_ffmpeg, tmp_path):
    image, voice = _generators()
    pipe = VideoPipeline(image_generator=image, voice_generator=voice)
    job = VideoJob(
        title="meu video",
        scenes=[Scene("n1", "v1", 3.0), Scene("n2", "v2", 3.0)],
        output_dir=tmp_path,
    )
    out = pipe.render(job)
    assert out.exists()
    # 2 clipes compostos + 1 concatenação = 3 chamadas de FFmpeg.
    assert len(fake_ffmpeg) == 3
    # A lista de concatenação é criada.
    assert (tmp_path / "concat_list.txt").exists()


def test_sem_gerador_de_imagem_levanta(fake_ffmpeg, tmp_path):
    _, voice = _generators()
    pipe = VideoPipeline(voice_generator=voice)  # sem image_generator
    job = VideoJob(title="x", scenes=[Scene("n", "v", 3.0)], output_dir=tmp_path)
    with pytest.raises(NotImplementedError):
        pipe.render(job)


def test_ffmpeg_ausente_levanta(monkeypatch):
    monkeypatch.setattr(video_pipeline.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError):
        VideoPipeline()


def test_legendas_adicionam_drawtext(fake_ffmpeg, tmp_path):
    image, voice = _generators()
    fonte = tmp_path / "fonte.ttf"
    fonte.write_bytes(b"ttf")
    pipe = VideoPipeline(
        image_generator=image,
        voice_generator=voice,
        burn_subtitles=True,
        font_path=str(fonte),
    )
    assert pipe.burn_subtitles is True
    job = VideoJob(title="v", scenes=[Scene("uma narração", "v", 3.0)], output_dir=tmp_path)
    pipe.render(job)
    # Algum comando de composição usa drawtext.
    assert any("drawtext" in arg for cmd in fake_ffmpeg for arg in cmd if isinstance(arg, str))


def test_sem_fonte_nao_ativa_legendas(fake_ffmpeg, monkeypatch, tmp_path):
    monkeypatch.setattr(video_pipeline, "_detect_font", lambda: None)
    image, voice = _generators()
    # burn_subtitles pedido, mas sem fonte disponível -> desativado.
    pipe = VideoPipeline(
        image_generator=image,
        voice_generator=voice,
        burn_subtitles=True,
        font_path="/caminho/inexistente.ttf",
    )
    assert pipe.font_path is None
    assert pipe.burn_subtitles is False
