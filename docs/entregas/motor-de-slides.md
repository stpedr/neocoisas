# Entrega: motor de slides (carrossel)

> Sprint 11 · Fundação: Marca & Carrossel — cards **"Modelo `Slide` + `Idea.slides`"** e
> **"Motor de layout: `render_carousel`"**.

## Resumo

Implementa o **motor de slides**: dado um `Slide` e um `BrandKit`, compõe um **PNG 1080×1350
(4:5)** com o template da marca aplicado — faixa, manchete ajustada automaticamente, apoio,
assinatura e numeração. É a peça que faltava para o carrossel, formato da maioria dos posts.

## Motivação

O repositório era **vídeo-first** (`Scene` → narração → FFmpeg → `.mp4`), mas a maioria dos
posts de uma empresa é **carrossel** — outro artefato: texto composto sobre imagem, em N telas
com a mesma identidade. Sem esse motor, o entregável principal da ferramenta não existia
(ver [`carrossel-first-motor-de-slides.md`](../planejamento/carrossel-first-motor-de-slides.md)).

É também o **ponto 2 dos três de consistência de marca**: é aqui que "N posts com a mesma
cara" deixa de depender do acaso do modelo e vira template determinístico.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `agents/slides.py` (novo) | `Slide` (papel gancho/conteúdo/resumo/CTA) + `build_slides` **puro** (normaliza a saída do LLM) + `normalize_role`. |
| `brand.py` (novo) | `BrandKit` — contrato visual com cores **semânticas**, `hex_to_rgb`, `readable_on` (contraste automático) e `from_palette`/`from_dict` tolerantes. |
| `render_carousel.py` (novo) | Motor de layout: `wrap_lines`/`fit_size` (**medida injetada**), `slide_palette`, `render_slide`, `render_carousel`. |
| `review/models.py` | `Idea` ganha `slides`, `post_format`, `caption`, `hashtags` — **retrocompatível** (`from_dict` mantém `reels` como padrão). |
| `requirements.txt`, `requirements-api.txt` | `pillow>=10.0` (composição). |
| `tests/test_slides.py`, `tests/test_render_carousel.py` (novos) | 44 testes — **195 no total**. |

## Como funciona

```
Slide + BrandKit ──> render_slide ──> PNG 1080x1350
   papel              faixa (accent)
   manchete           manchete auto-ajustada (fit_size)
   apoio              apoio em tom derivado
   arte (opcional)    arte com véu para legibilidade
                      assinatura da marca + n/N
```

- **Auto-ajuste tipográfico:** `fit_size` escolhe o **maior** corpo (108→36px) em que a
  manchete cabe na caixa; nunca corta texto — se nada couber, usa o menor corpo.
- **Cor por papel:** gancho usa o tom profundo (é a capa), CTA usa o realce (é a ação),
  conteúdo/resumo usam a superfície. `readable_on` escolhe texto claro ou escuro por
  **contraste calculado** (luminância relativa), então uma paleta escura não gera texto ilegível.
- **Núcleos puros com dependência injetada:** `wrap_lines(texto, largura, measure)` e
  `fit_size(..., measure)` recebem a função de medição — testáveis **sem carregar fonte**,
  no mesmo espírito do `refine_loop`.
- **Determinístico:** só matemática de layout + Pillow. Sem GPU, sem rede.
- **Degrada com elegância:** arte ilegível cai na cor sólida; sem fonte da marca, usa a fonte
  detectada no sistema (reusa `_detect_font` do `video_pipeline`) e por fim a padrão do Pillow.

## Como validar

```bash
python3 -m pytest -q tests/test_slides.py tests/test_render_carousel.py   # 44 passed
python3 -m pytest -q                                                      # 195 passed
```

Gerar um carrossel de verdade:

```python
from pathlib import Path
from agents.slides import build_slides
from brand import BrandKit
from render_carousel import render_carousel

kit = BrandKit(name="Doce Aroma", handle="@docearoma",
               surface="#EFE2D4", ink="#2A1710", accent="#C4632F", deep="#40241A")
slides = build_slides([
    {"role": "gancho", "titulo": "5 erros que fazem sua vela durar menos",
     "corpo": "O nº 3 quase todo mundo comete."},
    {"titulo": "Apagar soprando", "corpo": "Espalha fuligem e altera o aroma."},
    {"role": "cta", "titulo": "Feitas à mão, para durar", "corpo": "Ver a coleção →"},
])
render_carousel(slides, kit, Path("output/carrossel"))   # 01.png, 02.png, 03.png
```

## Critério de aceite

- [x] `Slide` com papéis (gancho/conteúdo/resumo/CTA) e arco inferido quando o modelo não marca.
- [x] `build_slides` tolerante (strings, campos pt/en, descarte de inválidos, teto de 10 itens).
- [x] Exporta **PNG 1080×1350** com o template do Brand Kit em **todos** os slides.
- [x] **Mesma faixa/assinatura** em todo o carrossel (teste compara pixels entre slides).
- [x] Manchete nunca invade a **área segura** — invariante travada com o medidor real.
- [x] Texto nunca é cortado; layout não quebra com manchete/apoio absurdamente longos.
- [x] Núcleos de medida testáveis **sem fonte**; renderização **sem GPU**.
- [x] `Idea` estendida de forma retrocompatível.
- [x] `python3 -m pytest -q` verde (195).

## Pendências / próximos

- **Agente de copy de carrossel** — hoje os slides chegam prontos; falta o agente que gera o
  arco (gancho→conteúdo→resumo→CTA) + legenda + hashtags a partir do brief.
- **Arte por slide** — ligar o `visual_prompt` ao provider de imagem (`agents/media`) para
  preencher `image_path` antes de compor.
- **`alt_text` automático** — depende da capacidade de **visão** (Sprint 11).
- **Publisher de carrossel** — containers filhos + pai na Graph API.
- **Logo no rodapé** — o `logo_path` do kit ainda não é desenhado (hoje usa ponto + handle).
- Ajuste fino de respiro: manchetes longas ficam a ~98% da largura útil; cabem, mas um
  designer pediria mais folga.
</content>
