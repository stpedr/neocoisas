"""Brand Kit — o **contrato visual** que todo post obedece.

Guarda a identidade da empresa (paleta, tipografia, marca, arte de referência).
É ele que faz N posts terem a mesma cara: o motor de slides
(`render_carousel.py`) compõe cada tela a partir daqui, em vez de deixar o
visual a cargo do modelo.

As cores são semânticas (não posicionais), então uma paleta incompleta ainda
produz um resultado coerente. `hex_to_rgb` e `from_palette` são puros e
cobertos por testes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["BrandKit", "hex_to_rgb", "DEFAULT_KIT"]


def hex_to_rgb(value: str, fallback: tuple[int, int, int] = (0, 0, 0)) -> tuple[int, int, int]:
    """Converte `#RRGGBB` (ou `#RGB`) em tupla RGB. Valor inválido cai no fallback."""
    text = (value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        return fallback
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return fallback


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Luminância relativa (0–1) — usada para escolher texto claro ou escuro."""
    def canal(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def readable_on(background: tuple[int, int, int]) -> tuple[int, int, int]:
    """Preto ou branco — o que tiver mais contraste sobre o fundo dado."""
    return (17, 17, 17) if _relative_luminance(background) > 0.45 else (255, 255, 255)


@dataclass
class BrandKit:
    """Identidade visual de uma empresa.

    Cores em `#RRGGBB`. Papéis:

    - `surface`: fundo padrão dos slides de conteúdo;
    - `ink`: cor do texto sobre `surface`;
    - `accent`: faixa/realce e fundo do slide de CTA;
    - `deep`: fundo do slide de gancho (a capa).
    """

    name: str = ""
    handle: str = ""
    surface: str = "#F2EEE9"
    ink: str = "#1D1B19"
    accent: str = "#C4632F"
    deep: str = "#2A1710"
    font_path: str | None = None          # fonte da manchete (.ttf)
    body_font_path: str | None = None     # fonte do apoio (padrão: a mesma)
    logo_path: str | None = None
    style_keywords: list[str] = field(default_factory=list)
    reference_images: list[str] = field(default_factory=list)

    # ------------------------------------------------------------- cores ---
    @property
    def rgb_surface(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.surface, (242, 238, 233))

    @property
    def rgb_ink(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.ink, (29, 27, 25))

    @property
    def rgb_accent(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.accent, (196, 99, 47))

    @property
    def rgb_deep(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.deep, (42, 23, 16))

    @property
    def palette(self) -> list[str]:
        return [self.surface, self.ink, self.accent, self.deep]

    # -------------------------------------------------------- (de)serial ---
    @classmethod
    def from_palette(cls, colors: list[str], **kwargs) -> "BrandKit":
        """Monta um kit a partir de uma lista de cores (ordem: surface, ink, accent, deep).

        Cores faltantes mantêm o padrão — uma paleta parcial ainda gera um kit
        utilizável.
        """
        campos = ("surface", "ink", "accent", "deep")
        dados = {campo: cor for campo, cor in zip(campos, colors or []) if cor}
        dados.update(kwargs)
        return cls(**dados)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "handle": self.handle,
            "surface": self.surface,
            "ink": self.ink,
            "accent": self.accent,
            "deep": self.deep,
            "font_path": self.font_path,
            "body_font_path": self.body_font_path,
            "logo_path": self.logo_path,
            "style_keywords": list(self.style_keywords),
            "reference_images": list(self.reference_images),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "BrandKit":
        """Aceita tanto os campos semânticos quanto uma lista `palette`."""
        data = dict(data or {})
        palette = data.pop("palette", None)
        conhecidos = {
            "name", "handle", "surface", "ink", "accent", "deep",
            "font_path", "body_font_path", "logo_path",
            "style_keywords", "reference_images",
        }
        limpos = {k: v for k, v in data.items() if k in conhecidos and v is not None}
        if palette:
            return cls.from_palette(palette, **limpos)
        return cls(**limpos)


DEFAULT_KIT = BrandKit()
