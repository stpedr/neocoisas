"""Motor de slides — compõe um carrossel a partir de `Slide` + `BrandKit`.

    Slide + BrandKit  ->  PNG 1080x1350 (4:5)
        faixa da marca · manchete · apoio · arte · assinatura · numeração

É aqui que "N posts com a mesma cara" acontece de fato: o template vem do Brand
Kit, não do modelo. A composição é **determinística** (matemática de layout, sem
GPU e sem rede), então é testável offline.

Os núcleos de medida (`wrap_lines`, `fit_size`) recebem a função de medição
**injetada**, no mesmo espírito do `refine_loop`: dá para testá-los sem carregar
fonte nenhuma.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agents.slides import CTA, HOOK, SUMMARY, Slide
from brand import BrandKit, readable_on

__all__ = [
    "CarouselLayout",
    "wrap_lines",
    "fit_size",
    "slide_palette",
    "render_slide",
    "render_carousel",
]


# --------------------------------------------------------------- layout ---
@dataclass(frozen=True)
class CarouselLayout:
    """Geometria do slide. 4:5 é o formato de melhor aproveitamento no feed."""

    width: int = 1080
    height: int = 1350
    margin: int = 88          # área segura nas laterais
    band: int = 12            # faixa da marca no topo
    footer_h: int = 96        # faixa inferior (assinatura + numeração)
    gap: int = 28             # respiro entre manchete e apoio

    @property
    def content_width(self) -> int:
        return self.width - 2 * self.margin

    @property
    def content_top(self) -> int:
        return self.band + self.margin

    @property
    def content_bottom(self) -> int:
        return self.height - self.footer_h - self.margin // 2

    @property
    def content_height(self) -> int:
        return self.content_bottom - self.content_top


DEFAULT_LAYOUT = CarouselLayout()

# Escala tipográfica da manchete por papel (px, tentadas de cima para baixo).
_HEADLINE_SIZES = (108, 96, 84, 74, 64, 56, 48, 42, 36)
_BODY_SIZES = (40, 36, 32, 28, 24)


# ---------------------------------------------------------- puros/medida ---
def wrap_lines(text: str, max_width: int, measure) -> list[str]:
    """Quebra `text` em linhas que caibam em `max_width`.

    `measure(str) -> largura`. Palavras maiores que a linha ficam sozinhas (sem
    hifenização), em vez de estourar o laço.
    """
    palavras = (text or "").split()
    if not palavras:
        return []

    linhas: list[str] = []
    atual = palavras[0]
    for palavra in palavras[1:]:
        candidata = f"{atual} {palavra}"
        if measure(candidata) <= max_width:
            atual = candidata
        else:
            linhas.append(atual)
            atual = palavra
    linhas.append(atual)
    return linhas


def fit_size(
    text: str,
    max_width: int,
    max_height: int,
    measure,
    sizes=_HEADLINE_SIZES,
    line_spacing: float = 1.14,
) -> tuple[int, list[str]]:
    """Maior corpo de fonte (dentre `sizes`) em que o texto cabe na caixa.

    `measure(str, size) -> (largura, altura)`. Devolve `(tamanho, linhas)`. Se
    nada couber, usa o menor tamanho — o texto é preservado, nunca cortado.
    """
    if not (text or "").strip():
        return (sizes[-1], [])

    for size in sizes:
        linhas = wrap_lines(text, max_width, lambda t, s=size: measure(t, s)[0])
        altura_linha = max(measure(linha, size)[1] for linha in linhas)
        if altura_linha * line_spacing * len(linhas) <= max_height:
            return (size, linhas)

    menor = sizes[-1]
    return (menor, wrap_lines(text, max_width, lambda t: measure(t, menor)[0]))


def slide_palette(role: str, kit: BrandKit) -> tuple:
    """Cores do slide conforme o papel: `(fundo, texto, realce)`.

    O gancho usa o tom profundo (é a capa), o CTA usa o realce (é a ação) e os
    demais usam a superfície — variação suficiente para dar ritmo ao carrossel
    sem quebrar a unidade.
    """
    if role == HOOK:
        fundo = kit.rgb_deep
        return (fundo, readable_on(fundo), kit.rgb_accent)
    if role == CTA:
        fundo = kit.rgb_accent
        return (fundo, readable_on(fundo), readable_on(fundo))
    fundo = kit.rgb_surface
    realce = kit.rgb_accent
    if role == SUMMARY:
        return (fundo, kit.rgb_ink, realce)
    return (fundo, kit.rgb_ink, realce)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Interpola duas cores (t=0 → a, t=1 → b)."""
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))  # type: ignore[return-value]


# ------------------------------------------------------------- tipografia ---
def _font_candidates(kit: BrandKit) -> list[str]:
    from agents.video_pipeline import _FONT_CANDIDATES, _detect_font

    achada = _detect_font()
    return [c for c in ([kit.font_path, achada, *_FONT_CANDIDATES]) if c]


def _load_font(kit: BrandKit, size: int, bold_path: str | None = None):
    """Carrega a fonte no tamanho pedido, caindo na fonte padrão do Pillow."""
    from PIL import ImageFont

    for caminho in ([bold_path] if bold_path else []) + _font_candidates(kit):
        try:
            return ImageFont.truetype(caminho, size)
        except (OSError, ValueError):
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow antigo: sem tamanho na fonte padrão
        return ImageFont.load_default()


def _measurer(kit: BrandKit, font_path: str | None = None):
    """Devolve `measure(texto, tamanho) -> (largura, altura)` usando Pillow."""
    from PIL import Image, ImageDraw

    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    cache: dict[int, object] = {}

    def measure(texto: str, tamanho: int) -> tuple[int, int]:
        fonte = cache.get(tamanho)
        if fonte is None:
            fonte = _load_font(kit, tamanho, font_path)
            cache[tamanho] = fonte
        esquerda, topo, direita, base = draw.textbbox((0, 0), texto or "M", font=fonte)
        return (int(direita - esquerda), int(base - topo))

    return measure, cache


# ----------------------------------------------------------------- arte ---
def _cover(img, size: tuple[int, int]):
    """Redimensiona cobrindo a caixa e corta o excedente pelo centro."""
    from PIL import Image

    largura, altura = size
    escala = max(largura / img.width, altura / img.height)
    nova = (max(1, int(img.width * escala)), max(1, int(img.height * escala)))
    img = img.resize(nova, Image.LANCZOS)
    esquerda = (img.width - largura) // 2
    topo = (img.height - altura) // 2
    return img.crop((esquerda, topo, esquerda + largura, topo + altura))


def _draw_background(canvas, slide: Slide, fundo, layout: CarouselLayout):
    """Pinta o fundo: arte do slide (com véu para legibilidade) ou cor sólida."""
    from PIL import Image, ImageDraw

    canvas.paste(Image.new("RGB", (layout.width, layout.height), fundo), (0, 0))
    caminho = slide.image_path
    if not caminho or not Path(caminho).exists():
        return

    try:
        arte = Image.open(caminho).convert("RGB")
    except OSError:
        return  # arte ilegível não derruba o slide — segue com a cor sólida

    canvas.paste(_cover(arte, (layout.width, layout.height)), (0, 0))

    # Véu vertical: preserva a arte no topo e garante contraste embaixo.
    veu = Image.new("L", (1, layout.height))
    desenho = ImageDraw.Draw(veu)
    for y in range(layout.height):
        t = y / max(1, layout.height - 1)
        desenho.point((0, y), fill=int(40 + 180 * (t ** 1.6)))
    mascara = veu.resize((layout.width, layout.height))
    canvas.paste(Image.new("RGB", (layout.width, layout.height), fundo), (0, 0), mascara)


# --------------------------------------------------------------- render ---
def render_slide(
    slide: Slide,
    kit: BrandKit,
    index: int,
    total: int,
    dest: Path,
    layout: CarouselLayout = DEFAULT_LAYOUT,
) -> Path:
    """Compõe **um** slide e grava o PNG em `dest`. Devolve o caminho."""
    from PIL import Image, ImageDraw

    fundo, texto_cor, realce = slide_palette(slide.role, kit)
    canvas = Image.new("RGB", (layout.width, layout.height), fundo)
    _draw_background(canvas, slide, fundo, layout)
    draw = ImageDraw.Draw(canvas)

    # Faixa da marca no topo — presente em todos os slides (a "assinatura").
    draw.rectangle([0, 0, layout.width, layout.band], fill=realce)

    measure, _ = _measurer(kit)
    disponivel = layout.content_height

    # Apoio primeiro (ocupa o rodapé do bloco de texto), manchete leva o resto.
    corpo_linhas: list[str] = []
    corpo_size = _BODY_SIZES[-1]
    if slide.body.strip():
        corpo_size, corpo_linhas = fit_size(
            slide.body, layout.content_width, int(disponivel * 0.32), measure, _BODY_SIZES
        )
    altura_corpo = int(corpo_size * 1.34 * len(corpo_linhas))
    espaco_manchete = disponivel - altura_corpo - (layout.gap if corpo_linhas else 0)

    titulo_size, titulo_linhas = fit_size(
        slide.headline, layout.content_width, max(80, espaco_manchete), measure, _HEADLINE_SIZES
    )

    fonte_titulo = _load_font(kit, titulo_size)
    fonte_corpo = _load_font(kit, corpo_size)

    altura_titulo = int(titulo_size * 1.14 * len(titulo_linhas))
    bloco = altura_titulo + (layout.gap + altura_corpo if corpo_linhas else 0)
    y = layout.content_top + max(0, (disponivel - bloco) // 2)

    for linha in titulo_linhas:
        draw.text((layout.margin, y), linha, font=fonte_titulo, fill=texto_cor)
        y += int(titulo_size * 1.14)

    if corpo_linhas:
        y += layout.gap
        cor_corpo = _mix(texto_cor, fundo, 0.28)
        for linha in corpo_linhas:
            draw.text((layout.margin, y), linha, font=fonte_corpo, fill=cor_corpo)
            y += int(corpo_size * 1.34)

    _draw_footer(draw, kit, index, total, texto_cor, fundo, realce, layout)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, "PNG")
    return dest


def _draw_footer(draw, kit, index, total, texto_cor, fundo, realce, layout):
    """Assinatura da marca à esquerda, numeração à direita."""
    base_y = layout.height - layout.footer_h + 18
    fonte = _load_font(kit, 26)

    marca = (kit.handle or kit.name or "").strip()
    if marca:
        ponto = 15
        draw.ellipse(
            [layout.margin, base_y + 6, layout.margin + ponto, base_y + 6 + ponto],
            fill=realce,
        )
        draw.text((layout.margin + ponto + 12, base_y), marca.upper(), font=fonte, fill=texto_cor)

    etiqueta = f"{index}/{total}"
    largura = draw.textbbox((0, 0), etiqueta, font=fonte)[2]
    draw.text(
        (layout.width - layout.margin - largura, base_y),
        etiqueta,
        font=fonte,
        fill=_mix(texto_cor, fundo, 0.45),
    )


def render_carousel(
    slides: list[Slide],
    kit: BrandKit,
    dest_dir: Path | str,
    layout: CarouselLayout = DEFAULT_LAYOUT,
) -> list[Path]:
    """Compõe o carrossel inteiro. Devolve os PNGs, na ordem dos slides.

    Levanta `ValueError` sem slides — um carrossel vazio é erro de chamada, não
    algo a mascarar.
    """
    if not slides:
        raise ValueError("Nenhum slide para renderizar.")

    destino = Path(dest_dir)
    total = len(slides)
    return [
        render_slide(slide, kit, i, total, destino / f"{i:02d}.png", layout)
        for i, slide in enumerate(slides, start=1)
    ]
