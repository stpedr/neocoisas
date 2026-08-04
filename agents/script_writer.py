"""Agente Roteirista cena-a-cena.

Transforma um `trending_topic` (uma ideia de história/meme vinda do
`LocalNicheAgent`) num roteiro concreto: uma lista de `Scene` — cada cena com
narração + prompt visual + duração — pronta para virar um `VideoJob` e ser
renderizada pelo `VideoPipeline`.

Usa o mesmo modelo LLM local (Ollama, GPU da máquina) que os demais agentes.
A conversão da resposta do modelo em objetos `Scene` (`build_scenes`) é pura e
não depende do Ollama, então pode ser testada isoladamente.
"""

import json

from .llm import OllamaError, get_text_client
from .video_pipeline import Scene, VideoJob

__all__ = ["ScriptWriterAgent", "OllamaError", "build_scenes"]

# Faixa de duração aceitável por cena, em segundos. Fora disso, a duração é
# ajustada para caber (vídeos curtos: cenas curtas mantêm o ritmo).
MIN_SCENE_DURATION_S = 1.5
MAX_SCENE_DURATION_S = 10.0
DEFAULT_SCENE_DURATION_S = 4.0


def _coerce_duration(value) -> float:
    """Converte a duração vinda do modelo num float dentro da faixa válida."""
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return DEFAULT_SCENE_DURATION_S
    if duration <= 0:
        return DEFAULT_SCENE_DURATION_S
    return max(MIN_SCENE_DURATION_S, min(MAX_SCENE_DURATION_S, duration))


def build_scenes(raw_scenes: list) -> list[Scene]:
    """Converte a lista de cenas (dicts do JSON do modelo) em objetos `Scene`.

    Tolerante a nomes de campo alternativos que o modelo pode usar
    (`narration`/`narracao`/`text`, `visual_prompt`/`visual`/`image`,
    `duration_s`/`duration`/`seconds`). Cenas sem narração e sem prompt visual
    são descartadas.
    """
    scenes: list[Scene] = []
    for item in raw_scenes:
        if not isinstance(item, dict):
            continue
        narration = (
            item.get("narration")
            or item.get("narracao")
            or item.get("text")
            or item.get("texto")
            or ""
        ).strip()
        visual_prompt = (
            item.get("visual_prompt")
            or item.get("visual")
            or item.get("image")
            or item.get("imagem")
            or item.get("prompt")
            or ""
        ).strip()
        if not narration and not visual_prompt:
            continue
        duration = _coerce_duration(
            item.get("duration_s")
            if item.get("duration_s") is not None
            else item.get("duration", item.get("seconds", item.get("duracao")))
        )
        scenes.append(
            Scene(
                narration=narration,
                visual_prompt=visual_prompt,
                duration_s=duration,
            )
        )
    return scenes


class ScriptWriterAgent:
    """Gera um roteiro cena-a-cena para um tópico usando o LLM local."""

    def __init__(self, config_path: str = "config.json"):
        self.client = get_text_client(config_path, agent="script")
        self.config = self.client.config

    @staticmethod
    def _build_prompt(topic: str, num_scenes: int) -> str:
        return f"""
        Você é um roteirista de vídeos curtos verticais (TikTok/Reels/Shorts),
        especialista em ganchos fortes e ritmo rápido.
        Tópico do vídeo: '{topic}'.
        Escreva um roteiro dividido em exatamente {num_scenes} cenas curtas.
        A primeira cena deve ser um gancho que prende nos 2 primeiros segundos.
        Retorne APENAS um JSON válido: uma LISTA de objetos, cada um com:
          - "narration": a fala/narração da cena (1 a 2 frases curtas, em português);
          - "visual_prompt": descrição visual da cena, em inglês, detalhada o
            suficiente para um gerador de imagens;
          - "duration_s": duração sugerida da cena em segundos (número).
        Não inclua texto fora do JSON.
        """

    def write_script(self, topic: str, num_scenes: int = 5) -> list[Scene]:
        """Gera e devolve as cenas do roteiro para o tópico informado.

        Levanta `OllamaError` se o servidor local falhar e `ValueError` se o
        modelo não devolver um JSON de cenas aproveitável.
        """
        print(
            f"[OLLAMA/GPU] Escrevendo roteiro de {num_scenes} cenas para "
            f"'{topic}' com o modelo local {self.client.model}..."
        )
        raw_response = self.client.generate(self._build_prompt(topic, num_scenes))
        try:
            data = self.client.extract_json(raw_response)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "O modelo não retornou um JSON de roteiro válido.\n"
                f"Saída bruta:\n{raw_response}"
            ) from exc

        # O modelo pode devolver a lista direto, ou embrulhada em {"scenes": [...]}.
        if isinstance(data, dict):
            data = data.get("scenes") or data.get("cenas") or []
        if not isinstance(data, list):
            raise ValueError(
                f"Esperava uma lista de cenas, recebi {type(data).__name__}."
            )

        scenes = build_scenes(data)
        if not scenes:
            raise ValueError("Nenhuma cena aproveitável foi gerada pelo modelo.")
        return scenes

    def build_video_job(self, topic: str, num_scenes: int = 5) -> VideoJob:
        """Gera o roteiro e já embrulha num `VideoJob` pronto para renderizar."""
        scenes = self.write_script(topic, num_scenes)
        return VideoJob(title=topic, scenes=scenes)


if __name__ == "__main__":
    agent = ScriptWriterAgent()
    job = agent.build_video_job(agent.config.get("active_niche", "memes"))
    print(f"Roteiro '{job.title}' com {len(job.scenes)} cenas:")
    for i, scene in enumerate(job.scenes, 1):
        print(f"\n[Cena {i}] ({scene.duration_s}s)")
        print(f"  Narração: {scene.narration}")
        print(f"  Visual:   {scene.visual_prompt}")
