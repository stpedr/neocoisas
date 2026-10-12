"""Catálogo dos efeitos do visual_frames que aparecem no menu Interativo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EffectInfo:
    key: str  # usado na API: "vf-luz"
    shader_id: str  # nome interno (Efeito no EstadoPainel original)
    title: str
    description: str
    available: bool = True  # fase 1 x fase 2


EFFECTS: dict[str, EffectInfo] = {
    "vf-luz": EffectInfo("vf-luz", "luz", "Luz reativa",
                         "Pontos neon no contorno das pessoas; as cores seguem a música."),
    "vf-lego": EffectInfo("vf-lego", "lego", "LEGO",
                          "A pessoa vira um mosaico de peças LEGO; ao se mexer, as peças se soltam e caem."),
    "vf-ecos": EffectInfo("vf-ecos", "ecos", "Ecos em quadrinhos",
                          "A pessoa vira HQ (nanquim e retícula) e deixa ecos coloridos; na batida, um carimbo."),
}


def effect_names() -> list[str]:
    return list(EFFECTS)
