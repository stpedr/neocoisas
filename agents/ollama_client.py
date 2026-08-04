"""Cliente compartilhado para o Ollama local.

Concentra a lógica comum a todos os agentes que falam com um modelo LLM local
via Ollama (rodando na GPU da máquina, custo zero de inferência):

- carregar a configuração (`config.json`);
- enviar um prompt e devolver o texto gerado, com erros claros (`OllamaError`)
  em vez de tracebacks;
- extrair um objeto JSON da resposta, tolerando cercas de código e texto extra
  antes/depois do JSON.

Assim, `LocalNicheAgent` e `ScriptWriterAgent` não repetem esse encanamento.
"""

import json
from pathlib import Path

import requests


class OllamaError(RuntimeError):
    """Erro ao comunicar com o servidor local do Ollama."""


class OllamaClient:
    """Encapsula a comunicação com o Ollama e o parsing das respostas."""

    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        base_url = self.config["ollama_base_url"].rstrip("/")
        self.ollama_url = f"{base_url}/api/generate"
        self.model = self.config["ollama_model"]
        self.timeout = self.config.get("request_timeout", 120)

    @staticmethod
    def _load_config(config_path: str) -> dict:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Arquivo de configuração '{config_path}' não encontrado. "
                "Copie 'config.example.json' para 'config.json' e ajuste os valores."
            )
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def generate(self, prompt: str) -> str:
        """Envia um prompt ao Ollama local e devolve o texto gerado."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        try:
            response = requests.post(self.ollama_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.exceptions.ConnectionError as exc:
            raise OllamaError(
                "Não foi possível conectar ao Ollama em "
                f"{self.ollama_url}. Verifique se o servidor está rodando "
                f"(ex: `ollama run {self.model}`)."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaError(
                f"Tempo esgotado ({self.timeout}s) aguardando resposta do Ollama."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise OllamaError(f"Falha na requisição ao Ollama: {exc}") from exc

    @staticmethod
    def extract_json(raw_response: str):
        """Extrai o objeto/lista JSON da resposta, tolerando cercas de código.

        Aceita tanto um objeto (`{...}`) quanto uma lista (`[...]`) no topo.
        Se o modelo adicionar texto antes/depois, recorta do primeiro delimitador
        de abertura até o último de fechamento correspondente.
        """
        clean = raw_response.replace("```json", "").replace("```", "").strip()
        if clean and clean[0] not in "{[":
            # Descobre qual estrutura aparece primeiro e recorta até o fecho dela.
            candidates = [(clean.find("{"), clean.rfind("}")),
                          (clean.find("["), clean.rfind("]"))]
            candidates = [(s, e) for s, e in candidates if s != -1 and e != -1]
            if candidates:
                start, end = min(candidates, key=lambda pair: pair[0])
                clean = clean[start : end + 1]
        return json.loads(clean)
