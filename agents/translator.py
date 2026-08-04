"""Agente tradutor — traduz as narrações das cenas para outro idioma.

Usado para legendas/versões multi-idioma. `parse_translations` é pura e alinha o
tamanho da lista traduzida ao esperado; a tradução em si usa o LLM local.
"""

from __future__ import annotations

import json

from .llm import OllamaError, get_text_client

__all__ = ["TranslatorAgent", "parse_translations", "OllamaError"]

# Idiomas suportados (código -> nome para o prompt).
LANGUAGES = {
    "en": "inglês",
    "es": "espanhol",
    "pt": "português",
    "fr": "francês",
    "de": "alemão",
}


def parse_translations(data, expected: int) -> list[str]:
    """Extrai uma lista de `expected` traduções, preenchendo/truncando se preciso."""
    if isinstance(data, dict):
        data = data.get("translations") or data.get("traducoes") or list(data.values())
    if not isinstance(data, list):
        data = []
    textos = [str(t).strip() for t in data if str(t).strip()]
    if len(textos) < expected:
        textos += [""] * (expected - len(textos))
    return textos[:expected]


class TranslatorAgent:
    def __init__(self, config_path: str = "config.json"):
        self.client = get_text_client(config_path, agent="translator")

    def translate(self, texts: list[str], lang: str) -> list[str]:
        """Traduz `texts` para `lang` (código ISO). Mantém a ordem e o tamanho."""
        if lang not in LANGUAGES:
            raise ValueError(f"Idioma não suportado: '{lang}'. Opções: {sorted(LANGUAGES)}.")
        if not texts:
            return []
        nome = LANGUAGES[lang]
        itens = "\n".join(f"{i}. {t}" for i, t in enumerate(texts))
        prompt = f"""
        Traduza para {nome} as frases abaixo, mantendo a ordem e a numeração.
        Retorne APENAS um JSON: uma lista de strings, uma tradução por item.
        Frases:
        {itens}
        """
        raw = self.client.generate(prompt)
        try:
            data = self.client.extract_json(raw)
        except json.JSONDecodeError:
            return texts  # fallback: mantém original
        return parse_translations(data, len(texts))
