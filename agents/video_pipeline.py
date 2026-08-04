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

import os
import shutil
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

# Fontes comuns para o burn-in de legendas (drawtext precisa de um fontfile).
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Debian/Ubuntu (Docker)
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",                          # macOS
    "C:/Windows/Fonts/arial.ttf",                        # Windows
]


def _detect_font() -> str | None:
    """Acha um arquivo de fonte para as legendas (env tem prioridade)."""
    env_font = os.environ.get("ANE_SUBTITLE_FONT")
    candidates = [env_font, *_FONT_CANDIDATES] if env_font else _FONT_CANDIDATES
    for path in candidates:
        if path and Path(path).exists():
            return path
    return None


def _ff_escape(path) -> str:
    """Escapa um caminho para uso dentro de um filtro FFmpeg (drawtext).

    Usa barras normais e escapa o `:` do drive do Windows (ex: `C:/...` →
    `C\\:/...`), que o parser de filtro interpretaria como separador de opção.
    """
    return Path(path).as_posix().replace(":", r"\:")


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

    def __init__(
        self,
        image_generator=None,
        voice_generator=None,
        scene_video_generator=None,
        burn_subtitles: bool = False,
        font_path: str | None = None,
    ):
        # Pontos de extensão: funções que você fornece para gerar mídia.
        #   image_generator(visual_prompt: str, dest: Path) -> Path
        #   voice_generator(narration: str, dest: Path) -> Path
        #   scene_video_generator(visual_prompt: str, dest: Path) -> Path (.mp4)
        # Se `scene_video_generator` for fornecido, cada cena vira um clipe de
        # vídeo (ex: Veo/Gemini) em vez de uma imagem estática.
        self.image_generator = image_generator
        self.voice_generator = voice_generator
        self.scene_video_generator = scene_video_generator
        # Legendas queimadas no vídeo (drawtext). Requer um arquivo de fonte
        # existente; se a fonte informada não existir, tenta auto-detectar, e
        # se nada for encontrado o burn-in é ignorado silenciosamente.
        if font_path and Path(font_path).exists():
            self.font_path = font_path
        else:
            self.font_path = _detect_font()
        self.burn_subtitles = burn_subtitles and self.font_path is not None
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
            audio_path = self._generate_voice(scene, assets_dir, idx)
            if self.scene_video_generator is not None:
                video_src = self._generate_scene_video(scene, assets_dir, idx)
                clip_path = self._compose_clip_from_video(
                    scene, video_src, audio_path, assets_dir, idx
                )
            else:
                image_path = self._generate_image(scene, assets_dir, idx)
                clip_path = self._compose_clip(scene, image_path, audio_path, assets_dir, idx)
            rendered_clips.append(clip_path)

        return self._concat_clips(rendered_clips, job.output_path)

    def _generate_scene_video(self, scene: Scene, assets_dir: Path, idx: int) -> Path:
        dest = assets_dir / f"scenevid_{idx:02d}.mp4"
        return self.scene_video_generator(scene.visual_prompt, dest)

    def _compose_clip_from_video(
        self, scene: Scene, video_path: Path, audio_path: Path, assets_dir: Path, idx: int
    ) -> Path:
        """Combina um clipe de vídeo (gerado) com a narração e a legenda."""
        clip_path = assets_dir / f"clip_{idx:02d}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-vf", self._build_vf(scene, assets_dir, idx),
            str(clip_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return clip_path

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

    def _build_vf(self, scene: Scene, assets_dir: Path, idx: int) -> str:
        """Monta o filtro de vídeo (escala/crop + legenda opcional)."""
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        )
        if self.burn_subtitles and scene.narration.strip():
            # `textfile` evita quase toda a dor de escape do drawtext.
            sub_file = assets_dir / f"sub_{idx:02d}.txt"
            wrapped = "\n".join(textwrap.wrap(scene.narration.strip(), width=32))
            sub_file.write_text(wrapped or scene.narration.strip(), encoding="utf-8")
            drawtext = (
                f"drawtext=fontfile='{_ff_escape(self.font_path)}':"
                f"textfile='{_ff_escape(sub_file)}':"
                "fontcolor=white:fontsize=46:line_spacing=8:"
                "box=1:boxcolor=black@0.55:boxborderw=18:"
                "x=(w-text_w)/2:y=h-text_h-140"
            )
            vf = f"{vf},{drawtext}"
        return vf

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
            "-vf", self._build_vf(scene, assets_dir, idx),
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
