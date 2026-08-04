"""Orquestrador central do Auto Niche Engine (ponto de entrada via CLI).

Executa a etapa de estratégia de nicho usando o modelo LLM local (Ollama) e
imprime o plano de conteúdo gerado. Com `--script`, segue para a etapa
seguinte: gera um roteiro cena-a-cena para o primeiro tópico em alta do plano.
As demais etapas (geração de mídia e distribuição) são acionadas daqui conforme
forem implementadas/conectadas.

Uso:
    python main.py                       # usa o nicho de config.json
    python main.py "Gatos Astronautas"   # sobrescreve o nicho pontualmente
    python main.py "Gatos" --script      # plano + roteiro do 1º tópico
"""

import json
import sys

from agents.niche_creator import LocalNicheAgent, OllamaError
from agents.script_writer import ScriptWriterAgent


def _first_topic(plan: dict, fallback: str) -> str:
    """Extrai um título de tópico do plano para virar roteiro."""
    topics = plan.get("trending_topics") or []
    if topics:
        first = topics[0]
        if isinstance(first, dict):
            for key in ("title", "titulo", "idea", "ideia", "topic", "name"):
                if first.get(key):
                    return str(first[key])
            # Dict sem campo conhecido: usa a primeira string encontrada.
            for value in first.values():
                if isinstance(value, str) and value.strip():
                    return value
        elif isinstance(first, str) and first.strip():
            return first
    return fallback


def _print_script(topic: str) -> int:
    try:
        agent = ScriptWriterAgent()
    except FileNotFoundError as exc:
        print(f"[ERRO] {exc}")
        return 1
    try:
        job = agent.build_video_job(topic)
    except OllamaError as exc:
        print(f"[ERRO] {exc}")
        return 2
    except ValueError as exc:
        print(f"[ERRO] {exc}")
        return 3

    print(f"\n=== Roteiro: {job.title} ({len(job.scenes)} cenas) ===")
    for i, scene in enumerate(job.scenes, 1):
        print(f"\n[Cena {i}] ({scene.duration_s}s)")
        print(f"  Narração: {scene.narration}")
        print(f"  Visual:   {scene.visual_prompt}")
    return 0


def run(niche_override: str | None = None, write_script: bool = False) -> int:
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

    if write_script:
        return _print_script(_first_topic(plan, niche))
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    write_script = "--script" in args
    args = [a for a in args if a != "--script"]
    override = args[0] if args else None
    raise SystemExit(run(override, write_script))
