# Planejamento: Calendário automático de posts para loja no Instagram

> **Status:** proposta (planejamento) · **Alvo:** Sprint 11 · Loja & Calendário editorial
> Documento de escopo. Não é uma entrega concluída — vira `docs/entregas/*.md` quando for implementado.

## 1. Resumo

Nova capacidade: dado o **perfil de uma loja** e um **mês/ano** de referência, gerar
automaticamente um **calendário editorial completo** de posts para o Instagram —
distribuídos ao longo do mês, ancorados em **datas comemorativas** e em **pilares de
conteúdo**, cada post já com **formato** (feed/carrossel/Reels/story), **legenda**,
**hashtags**, **conceito visual** e **CTA**. O calendário entra na esteira de revisão
existente (Tinder/Kanban) e alimenta o **agendador** para publicação via **API oficial
(Meta Graph API)**.

Em uma frase: hoje o motor gera **ideias soltas a partir de um prompt**; esta feature
gera um **plano mensal coerente para uma marca**, pronto para revisar, renderizar e postar.

## 2. Motivação

- O fluxo atual (`IdeaGenerator` + `engine.run_prompt`) é ótimo para conteúdo de
  nicho "avulso", mas uma **loja** precisa de **consistência, variedade e timing**:
  postar nos dias certos, variar formatos e cobrir datas sazonais (Dia das Mães, Namorados,
  Black Friday, Natal…). Fazer isso manualmente prompt a prompt é trabalhoso e inconsistente.
- Boas práticas de mercado convergem em **calendário mensal + pilares de conteúdo +
  mix de formatos** ([Sprout Social](https://sproutsocial.com/insights/social-media-calendar/),
  [SocialBee](https://socialbee.com/blog/social-media-content-calendar/)). É exatamente
  esse artefato que queremos gerar automaticamente.
- Reaproveita quase toda a arquitetura já pronta (fila, scheduler, publisher, geração de
  mídia). O que falta é a **camada de planejamento de marca** por cima.

## 3. Como se encaixa na arquitetura atual (reúso)

| Já existe | Reúso nesta feature |
|---|---|
| `review/models.Idea` + `review/queue.ReviewQueue` (SQLite) | Cada post do calendário **é uma `Idea`** estendida (novos campos opcionais); a fila continua sendo a fonte de verdade. |
| `agents/llm` (`get_text_client`, factory por agente) | Novo agente de calendário usa o mesmo factory/override de modelo. |
| `agents/media` + `render.py` | Geração de imagem/vídeo do post permanece idêntica. |
| `scheduler.py` (APScheduler, `run_tick`, autogen) | O agendamento passa a respeitar a **data planejada** de cada post (hoje é só "próximo aprovado"). |
| `publishers/instagram.py` (Graph API, scaffold) | Publicação real de **imagem/carrossel/Reels** por post. |
| `engine.py` (modos manual/auto) | Ganha um caminho "calendário": gera N posts datados de uma vez. |
| `board/seed.py` + `/api/board` | Novos cards da Sprint 11. |

**Princípio do repo mantido:** cada capacidade externa é contrato + factory selecionável
por config/env (ver `CLAUDE.md`). O gerador de calendário segue o mesmo padrão dos demais agentes.

## 4. Modelo de dados

### 4.1. `StoreProfile` (novo)
Perfil persistente da loja — a "identidade" que guia todo o calendário.

```python
@dataclass
class StoreProfile:
    id: str
    name: str                     # "Doce Aroma Velas"
    niche: str                    # "velas artesanais e aromaterapia"
    audience: str                 # público-alvo
    tone: str                     # voz da marca: "acolhedor, sofisticado"
    products: list[str]           # itens/coleções em destaque
    keywords: list[str]           # termos e hashtags-base
    links: dict                   # {site, whatsapp, linktree}
    region: str = "BR"            # calendário de datas comemorativas
    posting_days: list[str]       # ["seg","qua","sex"] — cadência
    posts_per_week: int = 3
    handle: str | None = None     # @ da loja (referência)
```

Persistência: nova tabela `store_profiles` na mesma base SQLite (ou `stores.py` espelhando
`board/store.py`). Sem segredos aqui — tokens continuam no `.env`.

### 4.2. Extensão de `Idea` (campos opcionais, retrocompatíveis)
Para não quebrar nada, adicionamos campos **opcionais** com defaults (o `from_dict`/`to_dict`
já tolera ausência):

| Campo | Tipo | Uso |
|---|---|---|
| `store_id` | `str \| None` | vincula o post à loja |
| `scheduled_date` | `str \| None` (ISO) | dia planejado de publicação |
| `post_format` | `str` | `feed` \| `carousel` \| `reels` \| `story` |
| `pillar` | `str \| None` | pilar de conteúdo (ver §5) |
| `caption` | `str` | legenda pronta |
| `hashtags` | `list[str]` | hashtags sugeridas |
| `occasion` | `str \| None` | data comemorativa âncora, se houver |

> `Idea.scenes` continua servindo para Reels (roteiro cena-a-cena). Para feed/carrossel,
> usamos `caption` + `visual_prompt` das cenas como conceito de imagem.

## 5. Agente gerador de calendário (`agents/calendar_planner.py`, novo)

Responsável por transformar `StoreProfile + (mês, ano)` numa lista de posts datados.

**Pilares de conteúdo** (rotacionados ao longo do mês — configurável):
`produto` · `educativo` · `bastidores` · `prova_social` · `promocional` · `engajamento`.

**Pipeline:**
1. **Datas comemorativas** (`agents/calendar_dates.py`): tabela de datas do `region`
   (BR por padrão) para o mês — ex.: Dia das Mães, Namorados (12/jun), Black Friday, Natal,
   além de datas de nicho. Núcleo **puro e testável** (sem LLM).
2. **Distribuição**: dado `posting_days`/`posts_per_week`, calcula os dias do mês que terão
   post; casa datas comemorativas com o dia mais próximo. Núcleo **puro e testável**.
3. **Briefing por post** (LLM, via `get_text_client(agent="calendar")`): para cada slot,
   escolhe pilar + formato e gera `title`, `caption`, `hashtags`, `visual_prompt`.
   Retorna **JSON** normalizado (reusa `extract_json` do cliente).
4. **Montagem**: vira `list[Idea]` (com os campos de §4.2 preenchidos), pronta para a fila.

Assim como `build_idea_concepts`, as funções de **datas** e **distribuição** são puras →
cobertas por testes offline; só o passo 3 depende do Ollama.

## 6. Fluxo end-to-end

```
StoreProfile + (mês/ano)
        │
        ▼
calendar_planner.plan_month()          # datas + distribuição + briefing (LLM)
        │   → list[Idea] datadas (pillar, format, caption, hashtags)
        ▼
ReviewQueue.add_many()                 # entram como pending (manual) ou approved (auto)
        │
        ├── Revisão (Tinder/Kanban) — aba "Calendário": grade do mês
        │
        ▼
render.render_idea()                   # imagem/carrossel/Reels por post (mídia atual)
        │
        ▼
scheduler.run_tick()                   # publica no dia planejado (scheduled_date)
        │
        ▼
publishers/instagram.py (Graph API)    # container → media_publish (2 passos)
```

## 7. Superfície de API (novos endpoints em `server.py`)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/stores` | cria/atualiza `StoreProfile` |
| `GET` | `/api/stores` | lista lojas |
| `POST` | `/api/stores/{id}/calendar` | gera o calendário de `{month, year, mode}` → posts na fila |
| `GET` | `/api/calendar?store_id&month&year` | retorna os posts do mês (grade) |
| `PATCH` | `/api/ideas/{id}/schedule` | ajusta `scheduled_date`/`post_format` de um post |

Geração pesada segue o padrão já existente de **job assíncrono + polling** (`jobs.py`),
evitando timeout ao gerar ~12–20 posts de uma vez.

## 8. Frontend — aba "Calendário" (`web/app`)

- **Setup da loja**: formulário do `StoreProfile` (nicho, tom, produtos, cadência, links).
- **Gerar mês**: seletor de mês/ano + botão "Gerar calendário" (modo manual/auto).
- **Grade mensal**: visão de calendário com cada dia mostrando os posts (badge de pilar +
  ícone de formato). Reusa tokens/design system da Sprint 10 (tema, a11y, toasts, skeletons).
- **Card do post**: legenda, hashtags, conceito visual, botões Renderizar / Aprovar / Agendar.
- Mobile-first e acessível, coerente com o restante do painel.

## 9. Integração com o agendador

Hoje `run_scheduled_posts` pega "os próximos aprovados". Ajuste mínimo: ao selecionar o
lote, **priorizar/filtrar por `scheduled_date <= agora`** (posts com data respeitam o dia
planejado; posts sem data mantêm o comportamento atual). Mantém retrocompatibilidade e o
**modo simulado** sem token.

## 10. Escopo, limites e conformidade (obrigatório — ver `CLAUDE.md`)

- **Somente APIs oficiais.** Publicação via **Meta Graph API / Instagram Content Publishing**
  ([docs Meta](https://developers.facebook.com/docs/instagram-platform/content-publishing/)):
  conta Business/Creator, fluxo em **2 passos** (criar container → `media_publish`).
- **Formatos suportados pela API:** imagem única, **carrossel**, **Reels** e (com ressalvas)
  **stories**. O vídeo/imagem precisa estar acessível por **URL pública** — ponto já sinalizado
  em `publishers/instagram.py` e que esta feature precisa resolver (hospedagem do arquivo).
- **Rate limit:** ~**100 posts publicados/24h por conta** (carrossel conta como 1). O agendador
  deve respeitar esse teto — trivial para uma loja (~12–30 posts/mês).
- **Nada de evasão de detecção:** sem fingerprint spoofing, proxies por conta ou DM em massa.
- **Segredos só no `.env`** (`IG_USER_ID`, `IG_ACCESS_TOKEN`) — nunca no git nem no chat.

## 11. Cards para o board (Sprint 11 · Loja & Calendário editorial)

Adicionar a `board/seed.py` (padrão dos cards existentes):

1. **`StoreProfile` + persistência** — modelo da loja + tabela SQLite + CRUD. `prioridade:alta`, `backend`.
2. **Tabela de datas comemorativas (BR)** — núcleo puro por mês/região, testável. `prioridade:alta`, `backend`, `conteúdo`.
3. **Distribuição de posts no mês** — cadência + casamento com datas, puro/testável. `prioridade:alta`, `backend`.
4. **Agente gerador de calendário** — briefing por post via LLM (pilar/formato/legenda/hashtags). `prioridade:alta`, `backend`, `conteúdo`.
5. **Extensão de `Idea` + endpoints** — campos novos + `/api/stores` e `/api/calendar`. `prioridade:média`, `backend`.
6. **Aba Calendário (frontend)** — setup da loja + grade mensal + cards. `prioridade:média`, `frontend`.
7. **Agendador por data planejada** — respeitar `scheduled_date` no `run_tick`. `prioridade:média`, `backend`.
8. **Publicar feed/carrossel no Instagram** — completar `publishers/instagram.py` (URL pública + Graph API). `prioridade:média`, `backend`, `integração`. *(Depende de OAuth/credenciais — já no backlog.)*
9. **Testes** — datas, distribuição, montagem de `Idea`, endpoints (TestClient). `prioridade:alta`, `testes`.

## 12. Riscos e decisões em aberto

- **URL pública do vídeo/imagem** para a Graph API (hospedagem): decidir entre volume servido
  pela API, bucket S3/compatível ou túnel. **Bloqueia a publicação real** (não a geração/planejamento).
- **OAuth/credenciais** (card já no backlog): publicação depende de token válido; até lá, roda em
  **modo simulado**.
- **Qualidade das datas comemorativas**: começar com tabela curada (BR) e permitir override por loja.
- **Um post = uma `Idea`?** Alternativa seria um modelo `CalendarPost` dedicado. Proposta: **estender
  `Idea`** (menos atrito, reúso total de fila/render/scheduler). Reavaliar se a fila ficar poluída.

## 13. Critério de aceite (da feature completa)

- [ ] Cadastrar uma loja pelo painel e gerar um calendário mensal (≥1 post por dia de postagem).
- [ ] Cada post traz pilar, formato, legenda e hashtags; datas comemorativas do mês aparecem ancoradas.
- [ ] Posts entram na fila e são revisáveis na grade mensal (aba Calendário).
- [ ] Agendador publica (ou simula) respeitando `scheduled_date`.
- [ ] Núcleos puros (datas + distribuição) cobertos por testes; `pytest -q` verde; `cd web && npm run build` ok.
- [ ] Entrega documentada em `docs/entregas/calendario-posts-loja.md` (regra do `CLAUDE.md`).

## 14. Como validar (quando implementado)

```bash
# offline (núcleos puros + endpoints)
pytest -q tests/test_calendar_planner.py tests/test_calendar_dates.py tests/test_server_http.py

# ao vivo (precisa do Ollama): gerar um mês para uma loja
curl -X POST http://localhost:8000/api/stores -d '{...perfil...}'
curl -X POST http://localhost:8000/api/stores/<ID>/calendar -d '{"month":9,"year":2026,"mode":"manual"}'
curl "http://localhost:8000/api/calendar?store_id=<ID>&month=9&year=2026"
```

## 15. Referências

- [Meta — Publish Content (Instagram Platform)](https://developers.facebook.com/docs/instagram-platform/content-publishing/)
- [Instagram Reels API Publishing Guide (2026)](https://postproxy.dev/blog/instagram-reels-api-publishing-guide/)
- [Sprout Social — Social media calendar](https://sproutsocial.com/insights/social-media-calendar/)
- [SocialBee — Content calendar template & pillars](https://socialbee.com/blog/social-media-content-calendar/)
- [Postiz — Content pillars for social media](https://postiz.com/blog/content-pillars-for-social-media)
</content>
</invoke>
