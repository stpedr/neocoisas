"""Arte de fundo dos slides — liga o `visual_prompt` ao provedor de imagem.

Separado de `render_carousel.py` de propósito: o motor de layout é
**determinístico e offline** (matemática + Pillow), enquanto a geração de arte
chama provedores que podem exigir GPU, rede ou chave. Misturar os dois tiraria
do layout a propriedade que o torna testável em qualquer máquina.

    Slide.visual_prompt + BrandKit -> provedor de imagem -> Slide.image_path

É aqui que acontece o **ponto 1 dos três de consistência de marca**: o prompt de
cada slide é condicionado pelas palavras de estilo do Brand Kit, para as artes de
um carrossel não parecerem oito ilustrações de origens diferentes.

`style_prompt` é puro e coberto por testes; a geração recebe o gerador
**injetado**, então também roda sem GPU nos testes.
"""

from __future__ import annotations

from pathlib import Path

from agents.slides import Slide
from brand import BrandKit

__all__ = ["style_prompt", "generate_slide_art", "ART_GUIDANCE"]

# O layout escreve a manchete por cima da arte; texto gerado pelo modelo brigaria
# com ela. Pedir arte limpa é mais barato que corrigir depois.
ART_GUIDANCE = "no text, no words, no watermark, no logo"


def style_prompt(visual_prompt: str, kit: BrandKit | None = None) -> str:
    """Condiciona o prompt visual do slide pelo estilo da marca.

    Junta a descrição da cena, as `style_keywords` do Brand Kit e a orientação de
    arte limpa. Sem kit (ou sem palavras de estilo), devolve o prompt original
    apenas com a orientação — nunca uma string vazia quando havia descrição.
    """
    partes = [(visual_prompt or "").strip()]
    if kit is not None:
        estilo = [str(k).strip() for k in (kit.style_keywords or []) if str(k).strip()]
        if estilo:
            partes.append(", ".join(estilo))
    partes.append(ART_GUIDANCE)
    return ", ".join(p for p in partes if p)


def generate_slide_art(
    slides: list[Slide],
    kit: BrandKit | None = None,
    config: dict | None = None,
    dest_dir: Path | str = "output/arte",
    generator=None,
) -> dict:
    """Gera a arte de cada slide e preenche `slide.image_path`.

    `generator` é um callable `(prompt, destino) -> Path` (o contrato de
    `agents.media`); quando omitido, vem do factory conforme a configuração.

    Falha de um slide **não derruba o carrossel**: aquele slide fica sem arte e o
    motor de layout cai na cor sólida da marca — mesmo contrato de tolerância do
    `post_approved` e do `run_scheduled_posts`. Devolve um resumo do lote.
    """
    if generator is None:
        from agents.media.factory import get_image_generator

        generator = get_image_generator(config or {})

    destino = Path(dest_dir)
    destino.mkdir(parents=True, exist_ok=True)

    detalhes: list[dict] = []
    gerados = pulados = falhas = 0

    for i, slide in enumerate(slides, start=1):
        if not (slide.visual_prompt or "").strip():
            pulados += 1
            detalhes.append({"slide": i, "status": "sem_prompt"})
            continue
        try:
            caminho = generator(style_prompt(slide.visual_prompt, kit), destino / f"{i:02d}.png")
            slide.image_path = str(caminho)
            gerados += 1
            detalhes.append({"slide": i, "status": "gerado", "arquivo": str(caminho)})
        except Exception as exc:  # noqa: BLE001 - provedor externo não derruba o lote
            falhas += 1
            detalhes.append({"slide": i, "status": "falha", "info": str(exc)})

    return {
        "total": len(slides),
        "gerados": gerados,
        "pulados": pulados,
        "falhas": falhas,
        "detalhes": detalhes,
    }
