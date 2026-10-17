"""Motions (Motion Module v1, HTML) projetados nas superfícies.

- ``manifest.py``: lê e valida o manifesto do ``.html`` no upload.
- ``browser.py``: Chromium headless dedicado (na GPU dedicada) que roda os motions.
- ``hub.py``: sessões abertas pelo renderer, quadros que chegam do navegador e
  o que o mestre manda para ele (áudio do show, quadros da entrada de vídeo).
- ``source.py``: a fonte ``motion`` das superfícies.
"""
