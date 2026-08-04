"""Provedor de LLM de texto via Gemini API (opt-in por GEMINI_API_KEY).

Implementa o mesmo contrato do OllamaClient: `generate(prompt)->str`,
`extract_json(raw)`, `.model`, `.config`. A dependência google-genai é importada
sob demanda; sem chave, `generate` levanta erro claro.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..ollama_client import OllamaClient, OllamaError


class GeminiTextClient:
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.model = os.environ.get(
            "GEMINI_TEXT_MODEL", self.config.get("gemini_text_model", "gemini-1.5-flash")
        )

    @staticmethod
    def _load_config(config_path: str) -> dict:
        path = Path(config_path)
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    # Reusa o parser tolerante do OllamaClient (mesmo contrato).
    extract_json = staticmethod(OllamaClient.extract_json)

    def generate(self, prompt: str) -> str:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise OllamaError(
                "Configure GEMINI_API_KEY para usar text_provider=gemini."
            )
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - dependência opcional
            raise OllamaError(
                "Dependência ausente. Instale com `pip install google-genai`."
            ) from exc
        try:
            client = genai.Client(api_key=key)
            resp = client.models.generate_content(model=self.model, contents=prompt)
            return resp.text or ""
        except Exception as exc:  # noqa: BLE001 - normaliza erro do provedor
            raise OllamaError(f"Falha no Gemini (texto): {exc}") from exc
