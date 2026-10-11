# Referências — artigos consultados

Fontes que embasaram os documentos de planejamento, agrupadas por tema, com **o que cada uma
contribuiu** para as decisões de arquitetura.

> **Ressalva de acesso (honestidade metodológica).** A documentação da Meta e as fontes de
> arquitetura multi-agente foram consultadas normalmente. Já a maior parte dos **blogs de
> marketing** (Sprout Social, SocialBee, Postiz, Hootsuite, Sked Social, upGrad) está
> **bloqueada pelo proxy de egresso** deste ambiente: deles foram usados os **resumos de
> busca**, não o texto integral. As conclusões que dependem desses blogs (janela de 2–4
> semanas, pilares, folga para conteúdo reativo) são **convergentes entre várias fontes**,
> mas convém revalidar no texto original antes de tratar como número fechado.

## 1. Publicação no Instagram (API oficial)

| Fonte | Contribuição |
|---|---|
| [Meta — Publish Content (Instagram Platform)](https://developers.facebook.com/docs/instagram-platform/content-publishing/) | **Base normativa.** Fluxo em 2 passos (criar container → `media_publish`); formatos suportados (imagem, carrossel, Reels, stories); exigência de conta Business/Creator. |
| [Meta — IG User `/media` (referência)](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/) | Parâmetros do container; carrossel exige `is_carousel_item=true` nos filhos + container pai `media_type=CAROUSEL`. |
| [Postproxy — Instagram Reels API Publishing Guide (2026)](https://postproxy.dev/blog/instagram-reels-api-publishing-guide/) | **Rate limit de ~100 posts publicados por API em 24h** (carrossel conta como 1) — restrição que o materializador/scheduler respeita. |
| [Postproxy — Post to Instagram via API (2026)](https://postproxy.dev/blog/post-to-instagram-via-api/) | Confirmação do fluxo e requisito de **URL pública** do criativo. |
| [bundle.social — Instagram Graph API: Production Guide](https://bundle.social/blog/instagram-graph-api) | Considerações de produção (erros, containers pendentes). |

**Onde entrou:** doc 1 §10 (conformidade), doc 2 §9. Sustenta a regra de *só APIs oficiais*
do [`CLAUDE.md`](../../CLAUDE.md) e a dependência técnica de hospedar o criativo por URL pública.

## 2. Calendário editorial e pilares de conteúdo

| Fonte | Contribuição |
|---|---|
| [Sprout Social — Social media calendar](https://sproutsocial.com/insights/social-media-calendar/) | **Janela de detalhamento de 2–4 semanas** (menos = reativo; mais = conteúdo "stale"). Base da decisão de **materialização lazy**. |
| [SocialBee — Content calendar + template anual](https://socialbee.com/blog/social-media-content-calendar/) | Estrutura de calendário **anual** por mês; evergreen vs sazonal; reciclagem. |
| [Postiz — Content pillars for social media](https://postiz.com/blog/content-pillars-for-social-media) | **2–4 pilares recorrentes** rotacionando por semana; mix educativo/promocional/comunidade/inspiracional. |
| [Hootsuite — Social media calendar](https://blog.hootsuite.com/social-media-calendar/) | Ferramentas/templates; campanhas atravessando múltiplos posts. |
| [Sked Social — 15 content ideas by pillar](https://skedsocial.com/blog/15-content-ideas-you-can-plan-and-execute-this-week-by-content-pillar) | Exemplos concretos de post por pilar e por formato. |
| [upGrad](https://www.upgrad.com/blog/social-media-content-calendar/) · [Sproutbox](https://sproutbox.co/how-to-create-a-social-media-content-calendar) · [Balistro](https://www.balistro.com/blog/social-media-content-calendar-guide) · [Worcester State](https://www.worcester.edu/about/communications-and-marketing/web-digital-and-social-media/social-media/training-resouces/content-calendar-guide/) | Colunas típicas de um calendário (data, plataforma, pilar, formato, legenda, hashtags, status) → base dos campos de `PlanSlot`/`Idea`. |

**Onde entrou:** doc 1 (§5 pilares, §7 grade) e doc 2 (§1 as três premissas, §2 hierarquia,
§3 janela rolante). Também a ideia de **folga para conteúdo reativo** (~20–30%), que virou os
**flex slots**.

## 3. Arquitetura multi-agente / pipelines agênticos

| Fonte | Contribuição |
|---|---|
| [Beam — 6 Multi-Agent Orchestration Patterns for Production (2026)](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production) | **Nomeia os padrões** que usamos: Supervisor/Worker, Pipeline/Sequencial, Hierárquico, Peer-to-Peer, Marketplace. |
| [MachineLearningMastery — The End-to-End Agentic AI Pipeline](https://machinelearningmastery.com/the-end-to-end-agentic-ai-pipeline/) | Anatomia ponta a ponta de um pipeline agêntico; planejar antes de agir; validação por passo. |
| [arXiv 2512.08769 — Designing, Developing and Deploying Production-Grade Agentic AI Workflows](https://arxiv.org/html/2512.08769v1) | **7 componentes** de um sistema agêntico de produção: percepção, memória, raciocínio/planejamento, execução de ferramentas, orquestração, **guardrails**, observabilidade. |
| [Ajay Verma — Multi-Agent AI Architecture: Patterns, Protocols, Workflows](https://medium.com/@ajayverma23/multi-agent-ai-architecture-patterns-protocols-and-workflows-that-actually-scale-abc7152b7764) | **Orquestrador–trabalhador** e **loop de feedback** (agente produz → crítico avalia → revisa) como espinha dorsal de sistemas onde acerto importa mais que velocidade. |
| [Dataiku — Agent orchestration explained](https://www.dataiku.com/blog/agent-orchestration-explained) | Orquestração em contexto corporativo; roteamento e agregação. |
| [MindStudio — Multi-agent orchestration patterns](https://www.mindstudio.ai/blog/multi-agent-orchestration-patterns) · [Parallel content production](https://www.mindstudio.ai/blog/multi-agent-workflows-parallel-content-production) | Fan-out de agentes para produção de conteúdo em escala; **custo de coordenação** (overhead por salto). |
| [Contentful — What is agentic architecture](https://www.contentful.com/blog/agentic-architecture/) | Agentes de ação chamando ferramentas/APIs externas para publicar conteúdo. |
| [Writer — Agentic AI for marketing teams](https://writer.com/blog/agentic-ai-marketing/) · [Width.ai — Agentic AI in Digital Marketing](https://www.width.ai/post/agentic-ai-in-digital-marketing) | Casos de uso de marketing: geração de conteúdo → orquestração de campanha. |
| [arXiv 2508.10146 — Agentic AI Frameworks: Architectures, Protocols, Design Challenges](https://arxiv.org/pdf/2508.10146) | Panorama de frameworks; modelos heterogêneos atrás de uma camada de orquestração. |

**Onde entrou:** doc 3 (cabeçalho — o padrão nomeado) e o
[Mapa de Conexões](https://claude.ai/code/artifact/01572022-66d9-489b-875c-ba82c3de2baa).

### Mapeamento: os 7 componentes → nosso sistema

| Componente (arXiv 2512.08769) | No Auto Niche Engine |
|---|---|
| Percepção | Onboarding/fotos, `trend_scout`, capacidade `vision` |
| Memória | SQLite: `ReviewQueue`, `PlanStore`, Board, `BrandKit` |
| Raciocínio & planejamento | `calendar_planner`, `niche_creator` |
| Execução de ferramentas | `agents/media`, `render.py`, publishers |
| Orquestração | `engine.py` + `scheduler.py` |
| **Guardrails** | `critic.py` (nota + brand-safety) + revisão humana |
| Observabilidade | `analyst.py` + dashboard de métricas |

## 4. Como as fontes viraram decisão

| Decisão | Fonte principal |
|---|---|
| Materialização **lazy** em janela de 2–4 semanas | Sprout Social (horizonte de detalhamento) |
| **Flex slots** (~20–30% reservados) | convergência dos blogs de calendário (folga reativa) |
| **Pilares** rotacionados + campanhas sazonais | Postiz, SocialBee |
| **Rate limit** respeitado no agendador | Postproxy / Meta |
| **Guardrails** como etapa explícita do pipeline | arXiv 2512.08769, Verma |
| Padrão **orquestrador–trabalhador + pipeline + feedback** | Beam, Verma, MLMastery |
| **Registry/factory** para modelos heterogêneos | arXiv 2508.10146 (+ padrão já existente no repo) |
</content>
