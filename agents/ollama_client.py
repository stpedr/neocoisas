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
import os
import time
from pathlib import Path

import requests

# Padrões usados quando não há config.json nem variáveis de ambiente.
_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3"
_DEFAULT_TIMEOUT = 120


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
        self.retries = int(
            os.environ.get("ANE_REQUEST_RETRIES", self.config.get("request_retries", 2))
        )
        self.backoff = float(
            os.environ.get("ANE_REQUEST_BACKOFF", self.config.get("request_backoff", 2.0))
        )

    @staticmethod
    def _load_config(config_path: str) -> dict:
        """Carrega a config do arquivo e sobrepõe com variáveis de ambiente.

        As variáveis `ANE_OLLAMA_BASE_URL`, `ANE_OLLAMA_MODEL` e
        `ANE_REQUEST_TIMEOUT` têm prioridade — é assim que o docker-compose
        aponta a API para o serviço `ollama` (http://ollama:11434). Se não
        houver `config.json` nem a variável de base URL, o erro amigável de
        sempre é levantado (fluxo local via CLI/painel).
        """
        path = Path(config_path)
        cfg: dict = {}
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
        elif not os.environ.get("ANE_OLLAMA_BASE_URL"):
            raise FileNotFoundError(
                f"Arquivo de configuração '{config_path}' não encontrado. "
                "Copie 'config.example.json' para 'config.json' e ajuste os valores."
            )

        cfg.setdefault("ollama_base_url", _DEFAULT_BASE_URL)
        cfg.setdefault("ollama_model", _DEFAULT_MODEL)
        cfg.setdefault("request_timeout", _DEFAULT_TIMEOUT)

        if os.environ.get("ANE_OLLAMA_BASE_URL"):
            cfg["ollama_base_url"] = os.environ["ANE_OLLAMA_BASE_URL"]
        if os.environ.get("ANE_OLLAMA_MODEL"):
            cfg["ollama_model"] = os.environ["ANE_OLLAMA_MODEL"]
        if os.environ.get("ANE_REQUEST_TIMEOUT"):
            cfg["request_timeout"] = int(os.environ["ANE_REQUEST_TIMEOUT"])
        return cfg

    def generate(self, prompt: str) -> str:
        """Envia um prompt ao Ollama local e devolve o texto gerado.

        Reexecuta em falhas transitórias (conexão/timeout) com backoff
        exponencial (`ANE_REQUEST_RETRIES` / `ANE_REQUEST_BACKOFF`).
        """
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        ultimo_erro: Exception | None = None
        for tentativa in range(self.retries + 1):
            try:
                response = requests.post(self.ollama_url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                return response.json().get("response", "")
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                ultimo_erro = exc
                if tentativa < self.retries:
                    time.sleep(self.backoff * (2 ** tentativa))
                    continue
            except requests.exceptions.RequestException as exc:
                raise OllamaError(f"Falha na requisição ao Ollama: {exc}") from exc

        if isinstance(ultimo_erro, requests.exceptions.Timeout):
            raise OllamaError(
                f"Tempo esgotado ({self.timeout}s) aguardando resposta do Ollama "
                f"após {self.retries + 1} tentativas."
            ) from ultimo_erro
        raise OllamaError(
            "Não foi possível conectar ao Ollama em "
            f"{self.ollama_url} após {self.retries + 1} tentativas. Verifique se o "
            f"servidor está rodando (ex: `ollama run {self.model}`)."
        ) from ultimo_erro

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
