"""Orquestrador central do Auto Niche Engine (ponto de entrada via CLI).

Executa a etapa de estratégia de nicho usando o modelo LLM local (Ollama) e
imprime o plano de conteúdo gerado. As etapas seguintes do pipeline
(geração de vídeo e distribuição) são acionadas a partir daqui conforme
forem implementadas/conectadas.

Uso:
    python main.py                      # usa o nicho de config.json
    python main.py "Gatos Astronautas"  # sobrescreve o nicho pontualmente
"""

import json
import sys

from agents.niche_creator import LocalNicheAgent, OllamaError


def run(niche_override: str | None = None) -> int:
    try:
        agent = LocalNicheAgent()
    except FileNotFoundError as exc:
        print(f"[ERRO] {exc}")
        return 1

    niche = niche_override or agent.config.get("active_niche", "memes")

    try:
        plan = agent.setup_niche_campaign(niche)
    except OllamaError as exc:
        print(f"[ERRO] {exc}")
        return 2

    print("\n=== Plano de Conteúdo ===")
    print(json.dumps(plan, indent=2, ensure_ascii=False))

    if "error" in plan:
        return 3
    return 0


if __name__ == "__main__":
    override = sys.argv[1] if len(sys.argv) > 1 else None
    raise SystemExit(run(override))
