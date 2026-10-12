"""Efeitos visuais interativos importados do projeto *visual_frames*
(github.com/adrielvasques/visual_frames, de Adriel Vasques, usado com permissão).

O app original é openFrameworks/C++ só para Linux (V4L2, PulseAudio, CUDA).
Aqui ele roda no Windows dentro do ProjMap, reaproveitando o trabalho dele:

- o **shader GLSL** dos efeitos e os **modelos YOLO26** são importados do
  repositório original (``python -m projmap.effects.importar``) para
  ``~/.projmap/visual_frames``, fora deste git;
- a visão (detector YOLO seg+pose, rastreador ByteTrack, One Euro, máscara),
  o áudio (bandas + batida), a animação do personagem e a cena do salto são
  traduções fiéis do C++ dele (``vision.py``, ``tracker.py``, ``audio.py``,
  ``critter.py``, ``faces.py``, ``parachutes.py``, ``engine.py``);
- o resultado vira a fonte das superfícies "Cena interativa", escolhido no
  card *Interativo*.

Os cinco efeitos do autor: Luz reativa, LEGO, Ecos em quadrinhos (fase 1),
Bichinho espelho e Salto de paraquedas (fase 2).
"""

from .catalog import EFFECTS, effect_names

__all__ = ["EFFECTS", "effect_names"]
