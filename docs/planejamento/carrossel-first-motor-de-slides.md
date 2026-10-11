# Correção de arquitetura: carrossel é o formato padrão (motor de slides)

> **Status:** proposta · **Alvo:** Sprint 11 (fundação, junto com o Brand Kit)
> Corrige uma premissa dos documentos anteriores: eles herdaram do repositório uma
> orientação **vídeo-first**, mas na prática **a maioria dos posts de uma empresa é
> carrossel**. Entregável ilustrado:
> **[O Entregável](https://claude.ai/code/artifact/f07b8bbd-1fe1-463e-b695-e7953190d298)**.

## 1. O problema

O motor atual é construído em torno de **vídeo**:

| Peça | Hoje | Serve para carrossel? |
|---|---|---|
| `agents/video_pipeline.Scene` | `narration` + `visual_prompt` + `duration_s` | **Não** — carrossel não tem narração nem duração |
| `render.py::render_idea` | monta `.mp4` via FFmpeg (Ken Burns, legenda queimada, trilha) | **Não** — precisa de PNGs compostos |
| `render.py::render_thumbnail` | 1 imagem crua do provider | Parcial — não aplica template nem texto |
| `publishers/instagram.py` | `media_type=REELS` a partir de URL de vídeo | **Não** — carrossel usa outro fluxo |
| `agents/script_writer` | roteiro cena-a-cena (fala) | **Não** — copy de slide é outro registro |

Ou seja: manter carrossel como "um formato entre outros" esconde que **falta um motor de
produção inteiro**. Sem ele, o entregável principal da ferramenta não existe.

## 2. As três peças que faltam

### 2.1. Modelo `Slide` (paralelo a `Scene`)

```python
@dataclass
class Slide:
    role: str          # hook | content | summary | cta
    headline: str      # título grande do slide
    body: str = ""     # apoio, opcional
    visual_prompt: str = ""   # arte de fundo/ilustração
    image_path: str | None = None
    alt_text: str = ""        # acessibilidade, por slide
```

`Idea` ganha `slides: list[Slide]` ao lado de `scenes` — Reels continua usando `scenes`,
carrossel usa `slides`. `post_format` decide qual caminho a materialização segue.

**Estrutura narrativa** (o que o agente de copy deve produzir): `hook` (slide 1 — para o
scroll) → `content` × N (uma ideia por slide) → `summary` (salvável) → `cta`. Tipicamente
**6–10 slides**.

### 2.2. Motor de layout (`render_carousel`)

O núcleo novo: compõe **texto sobre imagem** aplicando o template do `BrandKit`.

```
Slide + BrandKit → PNG 1080×1350 (4:5)
   faixa/moldura da marca · logo · tipografia · paleta
   margens seguras · numeração (n/N) · hierarquia headline/body
```

- **Saída:** `output/carousels/<idea_id>/01.png … NN.png`.
- **Implementação sugerida:** Pillow (texto/composição) ou SVG → PNG. Determinístico e
  **testável sem GPU** — o layout é matemática, não modelo.
- **Onde entra o Brand Kit:** este é o **ponto 2** dos três de consistência
  (ver [arquitetura anual](./arquitetura-planejamento-anual.md), §1-bis). É aqui que "N posts
  com a mesma cara" acontece de fato.
- **Acessibilidade:** `alt_text` por slide acompanha o pacote.

### 2.3. Publisher de carrossel (Graph API)

Fluxo diferente do Reels — **N+1 chamadas**:

```
para cada slide:  POST /{ig-user-id}/media   (image_url=..., is_carousel_item=true) → child_id
POST /{ig-user-id}/media   (media_type=CAROUSEL, children=[child_ids...])           → creation_id
POST /{ig-user-id}/media_publish (creation_id=...)
```

- Limite da plataforma: **até 10 itens** por carrossel.
- **Rate limit:** o carrossel conta como **1 post** no teto de ~100/24h.
- Mantém a dependência já conhecida: cada imagem precisa de **URL pública**.

## 3. Impacto nos documentos anteriores

| Documento | Ajuste |
|---|---|
| [Calendário mensal](./calendario-posts-loja-instagram.md) | `post_format` passa a ter **carrossel como padrão**; `Idea.scenes` deixa de ser o caminho principal. |
| [Arquitetura anual](./arquitetura-planejamento-anual.md) | O passo "04 Produção" da linha de montagem bifurca: **slides** (carrossel/feed) ou **cenas** (Reels). O mix de formatos do plano deve refletir a realidade (maioria carrossel). |
| [IA local](./arquitetura-ia-modelos-locais.md) | Menos dependência de vídeo local (ComfyUI/AnimateDiff) e **mais** de imagem + composição. Carrossel roda bem **sem GPU pesada**: o texto vem do LLM e o layout é determinístico. |

**Efeito colateral positivo:** carrossel é *mais barato* que vídeo — sem TTS, sem FFmpeg de
vídeo, sem modelo de vídeo. O caminho padrão da ferramenta fica mais leve e mais rápido.

## 4. Cards (entram na Sprint 11)

1. **Modelo `Slide` + `Idea.slides`** (retrocompatível com `scenes`). `alta`, backend.
2. **Agente de copy de carrossel** — gera a estrutura hook→conteúdo→resumo→CTA em JSON;
   parsing **puro e testável**. `alta`, backend, conteúdo.
3. **Motor de layout `render_carousel`** — Slide + BrandKit → PNG 4:5, com template,
   numeração e margens seguras. `alta`, backend, conteúdo.
4. **Publisher de carrossel** — filhos + container pai + publish, teto de 10 itens. `alta`,
   backend, integração.
5. **UI de revisão do carrossel** — visualizar os N slides (swipe) antes de aprovar. `média`,
   frontend.
6. **Testes** — estrutura de slides, composição de layout, montagem das chamadas da API.
   `alta`, testes.

## 5. Critério de aceite

- [ ] Uma ideia de carrossel gera **6–10 slides** com papéis (hook/conteúdo/resumo/CTA).
- [ ] O motor exporta **PNG 1080×1350** com o template do Brand Kit aplicado em **todos** os
      slides (mesma faixa, marca, tipografia, paleta).
- [ ] Cada slide tem `alt_text`.
- [ ] O publisher monta o carrossel (filhos + pai) e respeita o teto de 10 itens.
- [ ] A revisão mostra os slides antes de aprovar.
- [ ] Núcleo de layout coberto por testes **sem GPU**; `python3 -m pytest -q` verde.
</content>
