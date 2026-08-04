"""Agente de Criação e Análise de Tendências.

Conecta-se ao Ollama rodando localmente (usando a GPU da máquina) para gerar,
com custo zero de inferência, a estratégia de conteúdo de um nicho: perfil de
conta sugerido, ideias de histórias/memes em alta e hashtags principais.
"""

import json

from .ollama_client import OllamaClient, OllamaError

# Reexportado para compatibilidade com quem importa de `niche_creator`.
__all__ = ["LocalNicheAgent", "OllamaError"]


class LocalNicheAgent:
    """Agente que usa um modelo LLM local (via Ollama) para planejar nichos."""

    def __init__(self, config_path: str = "config.json"):
        self.client = OllamaClient(config_path)
        self.config = self.client.config

    def query_ollama(self, prompt: str) -> str:
        """Envia um prompt ao Ollama local e devolve o texto gerado."""
        return self.client.generate(prompt)

    def setup_niche_campaign(self, niche_name: str) -> dict:
        """Gera um plano de conteúdo em JSON para o nicho informado."""
        print(
            f"[OLLAMA/GPU] Analisando o nicho '{niche_name}' "
            f"usando o modelo local {self.client.model}..."
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
            return self.client.extract_json(raw_response)
        except json.JSONDecodeError:
            return {
                "error": "O modelo não retornou um JSON válido.",
                "raw_output": raw_response,
            }


if __name__ == "__main__":
    agent = LocalNicheAgent()
    plan = agent.setup_niche_campaign(agent.config.get("active_niche", "memes"))
    print(json.dumps(plan, indent=2, ensure_ascii=False))
