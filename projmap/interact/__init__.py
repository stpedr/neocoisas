"""Camada interativa: sensores → comportamentos → visuais (ProjMap ou TouchDesigner).

- ``world``/``sim``: parede, pessoas, região do olhar e comportamentos.
- ``scene``: especificação de cena (o que o NLP gera), com presets.
- ``nlp``: texto → cena, via LLM do repo com validação e fallback.
- ``sensors``: sim | osc (Kinect via TouchDesigner) | webcam (MediaPipe).
- ``outputs``: OSC para o TouchDesigner.
- ``render``: renderer nativo (fonte ``interactive`` das superfícies).
- ``runtime``: laço em tempo real.
"""
