"""Agente de Criação e Análise de Tendências.

Conecta-se ao Ollama rodando localmente (usando a GPU da máquina) para gerar,
com custo zero de inferência, a estratégia de conteúdo de um nicho: perfil de
conta sugerido, ideias de histórias/memes em alta e hashtags principais.
"""

import json
from pathlib import Path

import requests


class OllamaError(RuntimeError):
    """Erro ao comunicar com o servidor local do Ollama."""


class LocalNicheAgent:
    """Agente que usa um modelo LLM local (via Ollama) para planejar nichos."""

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

    def query_ollama(self, prompt: str) -> str:
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
    def _extract_json(raw_response: str) -> dict:
        """Extrai o objeto JSON da resposta do modelo, tolerando cercas de código."""
        clean = raw_response.replace("```json", "").replace("```", "").strip()
        # Fallback: recorta do primeiro '{' até o último '}' caso o modelo
        # adicione texto antes/depois do JSON.
        if not clean.startswith("{"):
            start = clean.find("{")
            end = clean.rfind("}")
            if start != -1 and end != -1:
                clean = clean[start : end + 1]
        return json.loads(clean)

    def setup_niche_campaign(self, niche_name: str) -> dict:
        """Gera um plano de conteúdo em JSON para o nicho informado."""
        print(
            f"[OLLAMA/GPU] Analisando o nicho '{niche_name}' "
            f"usando o modelo local {self.model}..."
        )
        prompt = f"""
        Você é um estrategista de mídias sociais focado em crescimento rápido.
        O nicho alvo é: '{niche_name}'.
        Gere um plano de conteúdo em formato JSON estrito contendo:
        1. 'account_profile': Nome de usuário sugerido, bio otimizada e foto de
           perfil conceitual.
        2. 'trending_topics': 3 ideias de histórias/memes curtos e engraçados que
           estão gerando engajamento nesse nicho hoje.
        3. 'hashtags': 5 hashtags principais.
        Retorne APENAS o JSON válido, sem texto adicional.
        """
        raw_response = self.query_ollama(prompt)
        try:
            return self._extract_json(raw_response)
        except json.JSONDecodeError:
            return {
                "error": "O modelo não retornou um JSON válido.",
                "raw_output": raw_response,
            }


if __name__ == "__main__":
    agent = LocalNicheAgent()
    plan = agent.setup_niche_campaign(agent.config.get("active_niche", "memes"))
    print(json.dumps(plan, indent=2, ensure_ascii=False))
