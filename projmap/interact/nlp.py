"""Texto em linguagem natural → ``SceneSpec`` validada.

Fluxo:

1. Com um LLM disponível (``generate(prompt) -> str``; por padrão a factory do
   repo, ``agents.llm.get_text_client`` — Ollama local ou Gemini), pedimos **só
   JSON** no formato da cena, com exemplos.
2. Validamos com pydantic. Se falhar, mandamos os erros de volta ao LLM uma
   vez para ele corrigir.
3. Sem LLM, ou se ainda assim não validar, um parser por palavras-chave
   (português/inglês) monta a cena. A resposta sempre diz de onde veio
   (``source = "llm" | "fallback"``) — nunca fingimos que a IA entendeu.

Segurança: o LLM só escolhe parâmetros de peças prontas; nada do texto vira
código executado.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional, Protocol

import httpx
from pydantic import ValidationError

from .scene import (
    PRESETS,
    ChasePlayer,
    EntityGroup,
    FleePlayer,
    FreezeWhenWatched,
    SceneSpec,
    SeekGaze,
    Wander,
)

log = logging.getLogger(__name__)


class TextClient(Protocol):
    def generate(self, prompt: str) -> str: ...


@dataclass
class NlpResult:
    spec: SceneSpec
    source: str  # "llm" | "fallback"
    notes: list[str] = field(default_factory=list)


SCHEMA_GUIDE = """\
Formato (JSON, sem comentários):
{
  "title": str, "description": str,
  "background": [r,g,b],             // 0-255; preto = sem luz na projeção
  "fov_deg": número,                  // campo de visão que conta como "olhando" (padrão 60)
  "catch_radius": número,             // distância que conta como "pegou" (padrão 0.07)
  "on_caught": ["flash"|"reset"|"shake", ...],
  "seed": int,
  "groups": [ {                       // 1 a 8 grupos
    "name": str,
    "sprite": "ghost"|"orb"|"firefly"|"fish",
    "count": 1-200,
    "color": [r,g,b],
    "size": 0.01-0.6,                 // diâmetro em fração da altura da parede
    "spawn": "edges"|"random"|"center"|"far_from_player",
    "behaviors": [                    // combine à vontade
      {"type":"chase_player","speed":0.05-0.5},
      {"type":"flee_player","speed":0.1-1,"radius":0.2-1},
      {"type":"wander","speed":0.02-0.3,"turn":0-8},
      {"type":"seek_gaze","speed":0.05-0.6},
      {"type":"freeze_when_watched","shy":true|false}
    ] } ]
}
Unidades: a parede tem altura 1. A pessoa fica em frente à parede; "olhar" = a região da
parede para onde a cabeça dela aponta. Use SÓ os sprites e comportamentos listados."""

PROMPT = """Você configura cenas interativas de projeção mapeada a partir de uma descrição.
{guide}

Exemplo — "fantasmas que param quando eu olho e vêm atrás de mim quando viro de costas":
{example}

Descrição do usuário:
\"\"\"{text}\"\"\"

Responda APENAS com o JSON da cena."""

FIX_PROMPT = """O JSON abaixo não passou na validação. Corrija e responda APENAS com o JSON corrigido.
Erros:
{errors}

JSON:
{raw}"""


_client_error: Optional[str] = None


class _OllamaHttpClient:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: str) -> str:
        resp = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=30.0,
        )
        resp.raise_for_status()
        return str(resp.json().get("response", ""))


class _GeminiHttpClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str) -> str:
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30.0,
        )
        resp.raise_for_status()
        candidates = resp.json().get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
        return str(parts[0].get("text", "")) if parts else ""


def default_client() -> Optional[TextClient]:
    """Cliente de texto autônomo do ProjMap (Ollama local ou Gemini via httpx)."""
    global _client_error
    provider = os.environ.get("PROJMAP_LLM_PROVIDER", os.environ.get("ANE_TEXT_PROVIDER", "ollama")).strip().lower()
    try:
        if provider == "gemini":
            api_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY não configurada")
            model = os.environ.get("PROJMAP_GEMINI_MODEL", "gemini-2.5-flash").strip()
            _client_error = None
            return _GeminiHttpClient(api_key=api_key, model=model)
        base_url = os.environ.get("PROJMAP_OLLAMA_URL", os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).strip()
        model = os.environ.get("PROJMAP_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "llama3")).strip()
        _client_error = None
        return _OllamaHttpClient(base_url=base_url, model=model)
    except Exception as exc:  # noqa: BLE001 — sem LLM configurado: usamos o fallback
        _client_error = str(exc)
        log.info("LLM indisponível para cenas (%s); usando parser por palavras-chave", exc)
        return None



def scene_from_text(text: str, client: Optional[TextClient] = None, use_llm: bool = True) -> NlpResult:
    text = (text or "").strip()
    if not text:
        raise ValueError("descreva a cena")
    notes: list[str] = []
    if use_llm and client is not None:
        example = PRESETS["fantasmas-timidos"].model_dump_json(exclude={"version"})
        raw = ""
        try:
            raw = client.generate(PROMPT.format(guide=SCHEMA_GUIDE, example=example, text=text))
            return NlpResult(_parse(raw), "llm", notes)
        except ValidationError as exc:
            errors = _errors(exc)
            notes.append("LLM errou o formato; pedindo correção")
            try:
                raw2 = client.generate(FIX_PROMPT.format(errors="\n".join(errors), raw=raw[:4000]))
                return NlpResult(_parse(raw2), "llm", notes)
            except (ValidationError, ValueError) as exc2:
                notes.append(f"correção falhou: {exc2}"[:300])
        except ValueError as exc:
            notes.append(f"resposta do LLM sem JSON válido: {exc}"[:300])
        except Exception as exc:  # noqa: BLE001 — rede/LLM fora do ar
            notes.append(f"LLM indisponível: {exc}"[:300])
    if use_llm and client is None:
        notes.append(f"LLM não configurado: {_client_error}"[:300] if _client_error else "LLM não configurado")
    spec = keyword_scene(text)
    notes.append("cena montada por palavras-chave (sem IA)")
    return NlpResult(spec, "fallback", notes)


def _parse(raw: str) -> SceneSpec:
    clean = raw.replace("```json", "").replace("```", "").strip()
    start, end = clean.find("{"), clean.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("nenhum objeto JSON na resposta")
    data = json.loads(clean[start:end + 1])
    data.pop("version", None)
    return SceneSpec.model_validate(data)


def _errors(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()][:20]


# ----------------------------------------------------------- fallback simples
COLORS = {
    "branc": (240, 244, 255), "white": (240, 244, 255), "vermelh": (255, 60, 60), "red": (255, 60, 60),
    "verde": (60, 255, 120), "green": (60, 255, 120), "azul": (70, 140, 255), "blue": (70, 140, 255),
    "roxo": (170, 90, 255), "purple": (170, 90, 255), "amarel": (255, 225, 60), "yellow": (255, 225, 60),
    "laranj": (255, 150, 40), "orange": (255, 150, 40), "rosa": (255, 110, 200), "pink": (255, 110, 200),
    "ciano": (60, 230, 255), "cyan": (60, 230, 255), "dourad": (255, 200, 80), "gold": (255, 200, 80),
}
NUMBERS = {"dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
           "oito": 8, "nove": 9, "dez": 10, "doze": 12, "quinze": 15, "vinte": 20, "trinta": 30, "cinquenta": 50,
           "cem": 100, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "ten": 10, "twenty": 20}

SPRITES = [
    ("ghost", r"fantasm|ghost|\bboo\b|assombra|espirit"),
    ("firefly", r"vaga.?lume|firefl|faisc|luzinh"),
    ("fish", r"peix|cardume|fish|agua-viva|água-viva"),
    ("orb", r"orb|bola|esfera|luz|particul|bolha"),
]


def keyword_scene(text: str) -> SceneSpec:
    t = _norm(text)
    sprite = next((s for s, pat in SPRITES if re.search(pat, t)), "orb")
    # "mario"/"boo" sem outro sprite ⇒ fantasmas tímidos
    if re.search(r"\bmario\b", t) and sprite == "orb":
        sprite = "ghost"

    behaviors = []
    watch = re.search(r"(quando|se) (eu |voce |vc |a pessoa )?(olh|encar|vir[ao] pra (eles|ele|frente))|"
                      r"param quando|congel|stop when|freeze|when (i|you) look|olha.{0,20}param", t)
    chase = re.search(r"persegu|busca|vem atras|vao atras|vem (te )?pegar|ataca|chase|follow (me|you)|"
                      r"atras de (mim|voce)|perseg", t)
    flee = re.search(r"fog|escap|flee|run away|assust", t)
    gaze = re.search(r"onde (eu |voce )?olh|seg\w* o olhar|follow (my |the )?gaze|para onde olh", t)
    wander = re.search(r"vague|passei|flutu|nad|wander|drift|voa", t)

    if sprite == "ghost" and (watch or re.search(r"mario|boo|timid", t)) and not chase:
        chase = True  # a mecânica clássica: tímidos que te perseguem
    if chase:
        behaviors.append(ChasePlayer(speed=_speed(t, 0.12)))
    if flee:
        behaviors.append(FleePlayer(speed=_speed(t, 0.3)))
    if gaze:
        behaviors.append(SeekGaze(speed=_speed(t, 0.25)))
    if wander or not behaviors:
        behaviors.append(Wander(speed=_speed(t, 0.08) * 0.6))
    if watch or (sprite == "ghost" and chase and re.search(r"mario|boo|timid", t)):
        behaviors.append(FreezeWhenWatched(shy=sprite == "ghost"))

    count = _count(t, default={"ghost": 5, "firefly": 40, "fish": 18, "orb": 12}[sprite])
    color = next((c for k, c in COLORS.items() if k in t), None)
    defaults = {"ghost": ((240, 244, 255), 0.16), "firefly": ((255, 230, 120), 0.03),
                "fish": ((90, 200, 255), 0.07), "orb": ((140, 160, 255), 0.06)}
    base_color, size = defaults[sprite]
    if re.search(r"grand|enorm|gigant|big|huge", t):
        size *= 1.8
    if re.search(r"pequen|minuscul|tiny|small", t):
        size *= 0.6
    chasing = any(isinstance(b, ChasePlayer) for b in behaviors)
    title = {"ghost": "Fantasmas", "firefly": "Vaga-lumes", "fish": "Cardume", "orb": "Luzes"}[sprite]
    if any(isinstance(b, FreezeWhenWatched) for b in behaviors) and sprite == "ghost":
        title = "Fantasmas tímidos"
    return SceneSpec(
        title=title,
        description=text[:500],
        background=(0, 8, 20) if sprite == "fish" else (0, 0, 0),
        on_caught=["flash", "reset"] if chasing else [],
        groups=[EntityGroup(name=title.lower(), sprite=sprite, count=count, color=color or base_color,
                            size=min(size, 0.6), spawn="edges" if chasing else "random", behaviors=behaviors)],
    )


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _count(t: str, default: int) -> int:
    m = re.search(r"\b(\d{1,3})\b", t)
    if m:
        return max(1, min(200, int(m.group(1))))
    for word, n in NUMBERS.items():
        if re.search(rf"\b{word}\b", t):
            return n
    if re.search(r"muit|vari|many|lots|enxame|bando", t):
        return default * 2
    return default


def _speed(t: str, base: float) -> float:
    if re.search(r"rapid|veloz|corr|fast|quick", t):
        return base * 2
    if re.search(r"devag|lent|slow", t):
        return base * 0.5
    return base
