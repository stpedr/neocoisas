"""Modelo de slide de carrossel — o formato padrão de post de uma empresa.

Paralelo ao `Scene` (que descreve uma cena de vídeo), o `Slide` descreve **uma
tela do carrossel**: manchete, apoio, arte e papel narrativo. Um carrossel segue
o arco:

    gancho (para o scroll) -> conteúdo x N -> resumo (salvável) -> CTA

`build_slides` (normalização da saída do modelo) é **pura** e coberta por testes;
a composição visual fica em `render_carousel.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Slide", "build_slides", "ROLES", "HOOK", "CONTENT", "SUMMARY", "CTA"]

HOOK = "hook"
CONTENT = "content"
SUMMARY = "summary"
CTA = "cta"

ROLES = (HOOK, CONTENT, SUMMARY, CTA)

# Sinônimos aceitos vindos do modelo (pt/en), por papel.
_ROLE_ALIASES = {
    HOOK: {"hook", "gancho", "capa", "abertura", "cover"},
    CONTENT: {"content", "conteudo", "conteúdo", "corpo", "body", "dica", "tip"},
    SUMMARY: {"summary", "resumo", "recap", "conclusao", "conclusão"},
    CTA: {"cta", "call_to_action", "chamada", "acao", "ação", "oferta"},
}

# Limites práticos do formato (Graph API aceita até 10 itens por carrossel).
MIN_SLIDES = 3
MAX_SLIDES = 10


def _first(data: dict, *keys: str) -> str:
    """Primeiro valor não vazio entre as chaves (tolerante a nomes alternativos)."""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_role(raw: str) -> str:
    """Converte um papel vindo do modelo para um dos `ROLES` (padrão: conteúdo)."""
    value = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    for role, aliases in _ROLE_ALIASES.items():
        if value in aliases:
            return role
    return CONTENT


@dataclass
class Slide:
    """Uma tela do carrossel."""

    headline: str
    body: str = ""
    role: str = CONTENT
    visual_prompt: str = ""
    image_path: str | None = None
    alt_text: str = ""

    def to_dict(self) -> dict:
        return {
            "headline": self.headline,
            "body": self.body,
            "role": self.role,
            "visual_prompt": self.visual_prompt,
            "image_path": self.image_path,
            "alt_text": self.alt_text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Slide":
        return cls(
            headline=data.get("headline", ""),
            body=data.get("body", ""),
            role=normalize_role(data.get("role", CONTENT)),
            visual_prompt=data.get("visual_prompt", ""),
            image_path=data.get("image_path"),
            alt_text=data.get("alt_text", ""),
        )


def build_slides(raw_slides: list, max_slides: int = MAX_SLIDES) -> list[Slide]:
    """Normaliza os slides vindos do modelo em uma lista de `Slide`.

    Tolera itens que sejam apenas strings e nomes de campo alternativos
    (pt/en), no mesmo espírito de `build_idea_concepts` e `build_scenes`.
    Slides sem manchete aproveitável são descartados.

    Quando o modelo não informa os papéis, o arco é inferido pela posição: o
    primeiro vira **gancho** e o último, **CTA** — desde que haja slides
    suficientes para o arco fazer sentido.
    """
    slides: list[Slide] = []
    marcou_papel = False

    for item in raw_slides:
        if isinstance(item, str):
            headline, body, role_raw = item.strip(), "", ""
            visual = alt = ""
        elif isinstance(item, dict):
            headline = _first(item, "headline", "titulo", "título", "title", "texto", "text")
            body = _first(item, "body", "corpo", "apoio", "subtitle", "subtitulo", "descricao", "descrição")
            role_raw = _first(item, "role", "papel", "tipo", "type")
            visual = _first(item, "visual_prompt", "visual", "imagem", "image_prompt")
            alt = _first(item, "alt_text", "alt", "descricao_imagem")
        else:
            continue

        if not headline:
            continue
        if role_raw:
            marcou_papel = True
        slides.append(
            Slide(
                headline=headline,
                body=body,
                role=normalize_role(role_raw),
                visual_prompt=visual,
                alt_text=alt,
            )
        )

    slides = slides[:max_slides]

    # Sem papéis explícitos, infere o arco pela posição (precisa de gancho + CTA).
    if slides and not marcou_papel and len(slides) >= MIN_SLIDES:
        slides[0].role = HOOK
        slides[-1].role = CTA

    return slides
