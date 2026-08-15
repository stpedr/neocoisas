# Entrega: agente de copy de carrossel

> Sprint 11 · Fundação: Marca & Carrossel — card **"Agente de copy de carrossel"**.
> Fecha o caminho automático **brief → slides prontos para renderizar**.

## Resumo

Adiciona o agente que transforma um **brief** (tema + pilar + contexto da marca) no
**pacote de texto** de um carrossel: os slides com arco narrativo, a legenda e as hashtags —
tudo normalizado e pronto para o [motor de slides](./motor-de-slides.md).

## Motivação

O motor de slides já compunha PNGs com a identidade da marca, mas **os slides precisavam
chegar prontos**. Faltava a peça que escreve. Com ela, a cadeia
`brief → copy → slides → PNG` fecha e o post deixa de exigir redação manual.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `agents/carousel_writer.py` (novo) | `CarouselWriterAgent` + os núcleos **puros** `build_carousel`, `build_brand_block`, `normalize_hashtags`, `clean_caption`. |
| `registry.py` | `carousel` entra em `AGENTS` — ganha override de modelo por agente. |
| `tests/test_carousel_writer.py` (novo) | 33 testes — **228 no total**. |

## Como funciona

```
brief + pilar + contexto da marca
      │
      ▼  1 chamada ao LLM (factory, agent="carousel")
   JSON { slides[], caption, hashtags }
      │
      ▼  normalização pura
   { slides: list[Slide], caption: str, hashtags: list[str] }
```

**O arco é imposto pelo prompt**, não sugerido: slide 1 é o **gancho**, os do meio entregam
**uma ideia distinta cada**, o penúltimo é o **resumo** (motivo para salvar) e o último é o
**CTA**.

**Fronteira explícita entre slides.** O prompt diz textualmente que *"nenhum slide pode repetir
o assunto de outro"* — a mesma correção que sistemas multi-agente aplicam para trabalhadores
paralelos não duplicarem trabalho (ver
[`paralelismo-de-modelos.md`](../planejamento/paralelismo-de-modelos.md), §3.3). Sem isso, o
carrossel sai com três slides dizendo a mesma coisa.

**Contexto da marca condicionado.** `build_brand_block` monta o bloco do prompt **só com os
campos presentes** (nome, segmento, público, tom, produtos, do's & don'ts) — uma marca com
pouca informação gera um bloco curto em vez de linhas vazias que confundem o modelo.

**Normalização defensiva**, no espírito do resto do repo:

- **hashtags** — vira `#`, minúscula, sem duplicata, preservando ordem e acentos. Numa **lista**,
  cada elemento é **uma** tag (`"Velas Artesanais"` → `#velasartesanais`); só uma **string solta**
  é fatiada, ou um item que traga várias tags (`"#um #dois"`).
- **legenda** — remove aspas envolventes (inclusive as **tipográficas**, que abrem e fecham com
  caracteres diferentes), colapsa espaços e respeita o limite de 2200 caracteres do Instagram.
- **slides** — reusa `build_slides`, tolerando campos em pt/en e respeitando o teto de 10 itens.

`write_idea(idea)` preenche `slides`, `caption`, `hashtags` e marca `post_format="carousel"`.

## Como validar

```bash
python3 -m pytest -q tests/test_carousel_writer.py   # 33 passed
python3 -m pytest -q                                 # 228 passed
```

Ao vivo (precisa do Ollama):

```python
from agents.carousel_writer import CarouselWriterAgent

agente = CarouselWriterAgent()
pacote = agente.write(
    "erros que fazem sua vela durar menos",
    num_slides=8,
    pillar="educativo",
    brand={"name": "Doce Aroma", "tone": "acolhedor", "products": ["velas de soja"]},
)
```

E a cadeia completa até o PNG:

```python
from brand import BrandKit
from render_carousel import render_carousel

render_carousel(pacote["slides"], BrandKit(name="Doce Aroma", handle="@docearoma"), "output/post")
```

## Critério de aceite

- [x] Gera de 3 a 10 slides com o arco gancho → conteúdo → resumo → CTA.
- [x] `num_slides` fora da faixa é limitado ao teto da plataforma.
- [x] Prompt carrega contexto da marca e pilar, e exige **ideias distintas por slide**.
- [x] Legenda e hashtags normalizadas (duplicatas, pontuação, aspas, limites).
- [x] `write_idea` preenche a `Idea` e sobrevive ao ida-e-volta de serialização.
- [x] JSON inválido e resposta sem slides viram `ValueError` com mensagem útil.
- [x] Núcleos puros testados **sem LLM**; integração com cliente falso.
- [x] `python3 -m pytest -q` verde (228).

## Pendências / próximos

- **Arte por slide** — ligar o `visual_prompt` ao provider de imagem para preencher
  `image_path` antes de compor (hoje os slides saem sem arte de fundo).
- **Endpoint e UI** — expor a geração de carrossel na API e na aba de revisão.
- **Portão de marca no texto** — passar a copy pelo `critic` antes de aprovar.
- **`alt_text` de verdade** — hoje vem do modelo; com a capacidade de **visão**, poderá ser
  gerado a partir da arte final.
- Avaliar `num_slides` automático pelo tema, em vez de fixo em 8.
