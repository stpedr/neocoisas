# Planejamento — Geração automática de posts (marketing + IA)

Índice da proposta: uma ferramenta que planeja e produz o conteúdo de **qualquer empresa**
para o **ano inteiro**, com um **time de marketing completo** modelado como agentes, rodando
com **modelos locais**.

> **Status:** planejamento aprovado para detalhamento — nada implementado ainda.
> Quando os cards forem executados, cada entrega vira um `docs/entregas/<slug>.md`
> (regra do [`CLAUDE.md`](../../CLAUDE.md)).

## Documentos

| # | Documento | O que cobre |
|---|---|---|
| 1 | [`calendario-posts-loja-instagram.md`](./calendario-posts-loja-instagram.md) | Escopo inicial: calendário **mensal** de uma loja no Instagram. Modelo de dados (`StoreProfile`, extensão da `Idea`), agente de calendário, endpoints, aba Calendário. |
| 2 | [`arquitetura-planejamento-anual.md`](./arquitetura-planejamento-anual.md) | Arquitetura **anual**: hierarquia de 5 níveis, esqueleto barato + materialização *lazy*, **onboarding + Brand Kit**, **regionalização**, **trends**, **agência virtual** (17 papéis). |
| 3 | [`arquitetura-ia-modelos-locais.md`](./arquitetura-ia-modelos-locais.md) | Arquitetura de **IA local-first**: capacidade → factory → providers, stack 100% offline, capacidades novas (**visão**, **referência de estilo**), modelos por VRAM. |
| 4 | [`carrossel-first-motor-de-slides.md`](./carrossel-first-motor-de-slides.md) | **Correção:** carrossel é o formato padrão (não vídeo). Modelo `Slide`, **motor de layout** (Slide + BrandKit → PNG 4:5) e publisher de carrossel. |
| 5 | [`produto-agencia-exibicao-e-frontend.md`](./produto-agencia-exibicao-e-frontend.md) | **Produto:** barreira baixa → operação de agência (multi-tenant + revelação progressiva), `Activity`, aprovação por link, as telas, os 3 ritmos e a stack de frontend (**Base UI**, Motion, R3F com escopo). |
| 7 | [`paralelismo-de-modelos.md`](./paralelismo-de-modelos.md) | **Escala:** como paralelizar chamadas de modelo numa única GPU — semáforo por classe de recurso, pipelining das etapas e provider de serving trocável (vLLM). |
| 6 | [`personas.md`](./personas.md) | **Personas** — as 6 pessoas que a ferramenta atende, o que cada uma nunca deve ver e como elas resolvem disputas de escopo. |

## Apresentações visuais (artefatos)

| Artefato | Ângulo |
|---|---|
| [Agência Virtual](https://claude.ai/code/artifact/b4480a28-0ccb-4450-ba3b-696e9aa739fe) | **Quem faz** — 17 papéis em 5 departamentos e a linha de montagem de todo post. |
| [IA Local-First](https://claude.ai/code/artifact/48336c86-bace-46f2-bb1a-34c15956ba8b) | **Com quê** — o stack de modelos locais por capacidade. |
| [Mapa de Conexões](https://claude.ai/code/artifact/01572022-66d9-489b-875c-ba82c3de2baa) | **Como se ligam** — diagrama de conexões (orquestrador, estado, modelos, guardrails, feedback). |
| [O Entregável](https://claude.ai/code/artifact/f07b8bbd-1fe1-463e-b695-e7953190d298) | **O que o usuário recebe** — a jornada e um carrossel pronto de 8 slides com legenda, hashtags e data. |
| [Solo até Agência](https://claude.ai/code/artifact/00392daf-35bb-4506-8932-8661606ea5eb) | **Produto e interface** — revelação progressiva, as telas, os 3 ritmos e a stack de frontend. |
| [Uma GPU, Três Pistas](https://claude.ai/code/artifact/04f5eb2d-f7d3-4f27-aec4-61539cd819ca) | **Paralelismo** — onde o fan-out é legítimo e como sobrepor GPU, CPU e rede. |

## As decisões que sustentam a proposta

1. **Esqueleto barato + materialização *lazy*.** Planejar o ano inteiro é planejar a
   *estrutura* (campanhas + slots datados, sem LLM por slot) e materializar os posts numa
   **janela rolante de 2–4 semanas**. Controla custo, evita conteúdo velho e deixa as
   métricas influenciarem o que ainda não foi gerado. *(→ doc 2, §1)*
2. **Flex slots.** ~20–30% da cadência fica **vazia de propósito**, para absorver trends e
   conteúdo reativo. Calendário 100% preenchido não surfa trend. *(→ doc 2, §1)*
3. **O Brand Kit é o contrato visual.** Consistência é **imposta** em três pontos —
   condicionamento na geração, moldura no render e portão no critic — não deixada ao acaso
   do modelo. *(→ doc 2, §1-bis)*
4. **Local-first por contrato + factory.** Toda capacidade de IA tem provider local padrão;
   nuvem é troca opcional. Dados da marca não saem da máquina. *(→ doc 3)*
5. **Padrão arquitetural nomeado:** híbrido **orquestrador–trabalhador + pipeline sequencial
   + loop de feedback**. *(→ doc 3, cabeçalho; diagrama no Mapa de Conexões)*
6. **Carrossel é o caminho padrão, não vídeo.** A maioria dos posts de empresa é carrossel —
   o que exige um **motor de slides** (modelo `Slide` + layout com o Brand Kit + publisher de
   carrossel) que o repositório, hoje vídeo-first, não tem. *(→ doc 4)*
7. **Multi-tenant no modelo, revelação progressiva na UI.** Solo é uma agência com um cliente
   — e nunca vê a palavra "cliente". Retrofit de multi-tenant é caro; esconder complexidade é
   barato. *(→ doc 5)*

## Sprints propostas

**Todos os cards já estão semeados no board** (`board/seed.py` → `/api/board`): 102 cards, dos
quais **41 novos** nas sprints abaixo, todos em `backlog`.

| Sprint | Tema | Cards |
|---|---|---|
| 11 | Fundação: Marca & Carrossel | multi-tenant, `CompanyProfile`/`BrandKit`, onboarding + preview, presets, modelo `Slide`, copy de carrossel, **motor de layout**, publisher de carrossel, condicionamento de estilo, portão de consistência, capacidade `vision`, URL pública, testes | 14 |
| 12 | Planejamento anual | `AnnualPlan`/`Campaign`/`PlanSlot`, calendário comercial, esqueleto + flex slots, materializador lazy, endpoints, agendador por data, aba Planejamento, testes | 8 |
| 13 | Regionalização & Trends | `Region` + localização, `trend_scout`, gate de brand-safety, re-planejamento trimestral, registry `vision`/IP-Adapter, testes | 6 |
| 14 | Operação de agência | `Activity`, tela **Hoje**, **link de aprovação**, tela de Campanha, Todos os clientes, relatório, testes | 7 |
| 15 | Frontend | rotas reais, **Base UI**, **Motion**, TanStack Query, dnd-kit, **R3F** (escopo restrito) | 6 |
| 16 | Escala e paralelismo | executor com semáforo por classe, materializador em lote, pipelining, fronteira na delegação, provider `vllm`, tuning do Ollama, medição | 7 |

## Referências

Ver [`referencias-artigos.md`](./referencias-artigos.md) — artigos consultados, o que cada um
contribuiu e as ressalvas de acesso.
</content>
