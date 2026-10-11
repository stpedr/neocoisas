# Entrega: arte por slide + contraste sobre imagem

> Sprint 11 · Fundação: Marca & Carrossel — resolve a pendência **"arte por slide"** do
> [motor de slides](./motor-de-slides.md) e entrega o **nível leve** do card
> *"Condicionamento de estilo pelas fotos da marca"*.

## Resumo

Liga o `visual_prompt` de cada slide ao **provedor de imagem**, condicionando o prompt pelo
estilo do Brand Kit — e corrige um defeito que só apareceu com arte real: **texto sobre imagem
não tinha contraste garantido**.

## Motivação

O agente de copy já produzia o `visual_prompt` de cada slide, mas ele **não ia a lugar nenhum**:
os carrosséis saíam com fundo de cor sólida. Faltava a ponte até `agents/media`.

E ao gerar o primeiro carrossel com arte, ficou visível que a cor do texto — escolhida a partir
da **paleta da marca** — deixa de fazer sentido quando uma imagem cobre o slide: o fundo real
passa a ser a arte, não a cor do kit.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `carousel_art.py` (novo) | `style_prompt` (**puro**) + `generate_slide_art` com gerador **injetável**. |
| `render_carousel.py` | `_draw_background` devolve se aplicou arte; com arte, a cor do texto vem da **cor média real** atrás dele. Véu com piso alto (`_VEU_PISO`). |
| `tests/test_carousel_art.py` (novo) | 14 testes. |
| `tests/test_render_carousel.py` | +3 testes de contraste sobre arte. **245 no total**. |

## Como funciona

```
Slide.visual_prompt + BrandKit.style_keywords + "no text, no words"
        │
        ▼  provedor de imagem (a1111 | comfyui | gemini | placeholder)
   Slide.image_path
        │
        ▼  render_carousel
   PNG com arte de fundo + texto legível por cima
```

**Módulo separado de propósito.** O motor de layout é **determinístico e offline**; a geração de
arte chama provedores que podem exigir GPU, rede ou chave. Juntar os dois tiraria do layout a
propriedade que o torna testável em qualquer máquina.

**Condicionamento de estilo (ponto 1 dos três de consistência).** `style_prompt` junta a cena +
as `style_keywords` do kit + a orientação de arte limpa. Como o **sufixo é idêntico em todos os
slides**, as oito artes de um carrossel não parecem vir de origens diferentes — há teste
verificando exatamente isso.

**"no text, no words, no watermark, no logo".** O layout escreve a manchete por cima; arte com
texto brigaria com ela. Pedir arte limpa é mais barato que corrigir depois.

**Contraste garantido, em duas camadas:**

1. **Véu com piso alto** — o gradiente sobre a arte não começa em zero. Arte de alto contraste
   atrás da manchete tornaria o texto ilegível; o piso também puxa a arte para a paleta da
   marca, o que reforça a unidade do carrossel.
2. **Cor do texto medida, não presumida** — havendo arte, o motor amostra a **cor média da faixa
   onde a manchete cai** e escolhe preto ou branco por contraste (reusa `readable_on`).

**Falha isolada por slide.** Provedor fora do ar em um slide não derruba o carrossel: aquele
slide fica sem arte e cai na cor sólida da marca — mesmo contrato de tolerância do
`post_approved` e do `run_scheduled_posts`. O resumo devolve `{total, gerados, pulados, falhas,
detalhes}`.

## Como validar

```bash
python3 -m pytest -q tests/test_carousel_art.py   # 14 passed
python3 -m pytest -q                              # 245 passed
```

Ao vivo (com A1111 ou ComfyUI no ar):

```python
from brand import BrandKit
from carousel_art import generate_slide_art
from render_carousel import render_carousel

kit = BrandKit(name="Doce Aroma", handle="@docearoma",
               style_keywords=["warm artisanal photography", "soft natural light"])
generate_slide_art(idea.slides, kit, config={"image_provider": "a1111"}, dest_dir="output/arte")
render_carousel(idea.slides, kit, "output/post")
```

## Critério de aceite

- [x] `visual_prompt` de cada slide gera arte e preenche `image_path`.
- [x] Prompt condicionado pelas `style_keywords` — **sufixo idêntico** em todos os slides.
- [x] Arte pedida sem texto/marca-d'água (o layout é quem escreve).
- [x] Falha de um slide não derruba o lote; resumo informa o que falhou.
- [x] Slide sem `visual_prompt` é pulado sem chamar o provedor.
- [x] **Texto legível sobre arte clara e sobre arte escura** (testado nos dois extremos).
- [x] Sem arte, a cor da marca continua valendo (nenhuma regressão).
- [x] Núcleos puros e geração testados **sem GPU, rede ou chave**.
- [x] `python3 -m pytest -q` verde (245).

## Pendências / próximos

- **`style_keywords` automáticas** — hoje vêm preenchidas à mão no kit; com a capacidade de
  **visão** serão extraídas das fotos da estética enviadas no onboarding.
- **Nível forte do condicionamento** — referência visual real (IP-Adapter/img2img no ComfyUI),
  para a arte herdar a estética das fotos e não só as palavras.
- **Endpoint e UI** — expor geração de arte e regeneração por slide no painel.
- Ajuste fino do véu: `_VEU_PISO` privilegia legibilidade e unidade de marca; uma marca que
  queira arte mais presente vai querer isso configurável no Brand Kit.
