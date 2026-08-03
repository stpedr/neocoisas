"""Pipeline de geração de vídeo (esqueleto).

Orquestra as etapas locais de produção de um clipe curto a partir de um roteiro:

    roteiro -> prompts visuais -> geração de mídia -> narração (TTS)
            -> montagem/renderização (FFmpeg) -> arquivo .mp4 pronto

Este módulo define a interface e a sequência das etapas. Os geradores de
mídia (imagem/vídeo) e de voz são deixados como pontos de extensão (`hooks`)
para você conectar as ferramentas de sua preferência. A montagem final usa
FFmpeg, que precisa estar instalado e disponível no PATH.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Scene:
    """Uma cena do roteiro: texto narrado + descrição visual."""

    narration: str
    visual_prompt: str
    duration_s: float = 4.0


@dataclass
class VideoJob:
    """Descreve um vídeo a ser produzido a partir de uma lista de cenas."""

    title: str
    scenes: list[Scene] = field(default_factory=list)
    output_dir: Path = Path("output")

    @property
    def output_path(self) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.title)
        return self.output_dir / f"{safe}.mp4"


class VideoPipeline:
    """Coordena as etapas de produção de um vídeo curto localmente."""

    def __init__(self, image_generator=None, voice_generator=None):
        # Pontos de extensão: funções que você fornece para gerar mídia.
        #   image_generator(visual_prompt: str, dest: Path) -> Path
        #   voice_generator(narration: str, dest: Path) -> Path
        self.image_generator = image_generator
        self.voice_generator = voice_generator
        self._check_ffmpeg()

    @staticmethod
    def _check_ffmpeg() -> None:
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(
                "FFmpeg não encontrado no PATH. Instale-o para renderizar vídeos "
                "(ex: `apt-get install ffmpeg` ou `brew install ffmpeg`)."
            )

    def render(self, job: VideoJob) -> Path:
        """Executa o pipeline completo e devolve o caminho do arquivo final."""
        job.output_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = job.output_dir / "assets"
        assets_dir.mkdir(exist_ok=True)

        rendered_clips: list[Path] = []
        for idx, scene in enumerate(job.scenes):
            image_path = self._generate_image(scene, assets_dir, idx)
            audio_path = self._generate_voice(scene, assets_dir, idx)
            clip_path = self._compose_clip(scene, image_path, audio_path, assets_dir, idx)
            rendered_clips.append(clip_path)

        return self._concat_clips(rendered_clips, job.output_path)

    def _generate_image(self, scene: Scene, assets_dir: Path, idx: int) -> Path:
        dest = assets_dir / f"scene_{idx:02d}.png"
        if self.image_generator is None:
            raise NotImplementedError(
                "Nenhum gerador de imagem conectado. Passe `image_generator` ao "
                "instanciar VideoPipeline."
            )
        return self.image_generator(scene.visual_prompt, dest)

    def _generate_voice(self, scene: Scene, assets_dir: Path, idx: int) -> Path:
        dest = assets_dir / f"scene_{idx:02d}.mp3"
        if self.voice_generator is None:
            raise NotImplementedError(
                "Nenhum gerador de voz conectado. Passe `voice_generator` ao "
                "instanciar VideoPipeline."
            )
        return self.voice_generator(scene.narration, dest)

    def _compose_clip(
        self, scene: Scene, image_path: Path, audio_path: Path, assets_dir: Path, idx: int
    ) -> Path:
        """Combina uma imagem estática e uma narração em um clipe .mp4."""
        clip_path = assets_dir / f"clip_{idx:02d}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(image_path),
            "-i", str(audio_path),
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,"
                   "crop=1080:1920",
            str(clip_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return clip_path

    def _concat_clips(self, clips: list[Path], output_path: Path) -> Path:
        """Concatena os clipes das cenas em um único vídeo final."""
        if not clips:
            raise ValueError("Nenhum clipe para concatenar.")
        list_file = output_path.parent / "concat_list.txt"
        list_file.write_text(
            "\n".join(f"file '{clip.resolve()}'" for clip in clips), encoding="utf-8"
        )
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
