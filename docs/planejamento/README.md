# Planejamento — Geração automática de posts (marketing + IA)

Índice da proposta: uma ferramenta que planeja e produz o conteúdo de **qualquer empresa**
para o **ano inteiro**, com um **time de marketing completo** modelado como agentes, rodando
com **modelos locais**.

> **Status:** planejamento fechado; **implementação iniciada**. O **motor de slides** já está
> entregue (ver [`docs/entregas/motor-de-slides.md`](../entregas/motor-de-slides.md)); o
> restante segue no board. Cada entrega vira um `docs/entregas/<slug>.md`
> (regra do [`CLAUDE.md`](../../CLAUDE.md)).

## Documentos

| # | Documento | O que cobre |
|---|---|---|
| 1 | [`calendario-posts-loja-instagram.md`](./calendario-posts-loja-instagram.md) | Escopo inicial: calendário **mensal** de uma loja no Instagram. Modelo de dados, agente de calendário, endpoints, aba Calendário. |
| 2 | [`arquitetura-planejamento-anual.md`](./arquitetura-planejamento-anual.md) | Arquitetura **anual**: hierarquia de 5 níveis, esqueleto barato + materialização *lazy*, **onboarding + Brand Kit**, **regionalização**, **trends**, **agência virtual** (17 papéis). |
| 3 | [`arquitetura-ia-modelos-locais.md`](./arquitetura-ia-modelos-locais.md) | **IA local-first**: capacidade → factory → providers, stack 100% offline, capacidades novas (**visão**, **referência de estilo**) e a **decisão de não fazer fine-tuning** (§8-bis). |
| 4 | [`carrossel-first-motor-de-slides.md`](./carrossel-first-motor-de-slides.md) | **Correção:** carrossel é o formato padrão (não vídeo). Modelo `Slide`, **motor de layout** e publisher de carrossel. |
| 5 | [`produto-agencia-exibicao-e-frontend.md`](./produto-agencia-exibicao-e-frontend.md) | **Produto:** barreira baixa → operação de agência (multi-tenant + revelação progressiva), `Activity`, aprovação por link, as 10 telas, os 3 ritmos e a stack de frontend (**Base UI**, Motion, R3F com escopo). |
| 6 | [`personas.md`](./personas.md) | **Personas** — as 6 pessoas que a ferramenta atende, o que cada uma nunca deve ver e como resolvem disputas de escopo. |
| 7 | [`paralelismo-de-modelos.md`](./paralelismo-de-modelos.md) | **Escala:** paralelizar chamadas de modelo numa **única GPU** — semáforo por classe, pipelining, **co-locação de dois modelos residentes** (time-slicing × MPS × MIG, faixas de VRAM, *thrashing*) e provider de serving trocável (vLLM). |
| 8 | [`requisitos-ui-ux.json`](./requisitos-ui-ux.json) | **Especificação de UI/UX** — 6 personas, 9 fluxos, 13 telas, 8 componentes e **115 requisitos** (79 funcionais + 31 transversais + 5 não-funcionais), com IDs rastreáveis. |
| — | [`referencias-artigos.md`](./referencias-artigos.md) | Artigos consultados, contribuição de cada um, mapeamento fonte→decisão e ressalvas de acesso. |

## Apresentações visuais (artefatos)

| Artefato | Ângulo |
|---|---|
| [Agência Virtual](https://claude.ai/code/artifact/b4480a28-0ccb-4450-ba3b-696e9aa739fe) | **Quem faz** — 17 papéis em 5 departamentos e a linha de montagem de todo post. |
| [IA Local-First](https://claude.ai/code/artifact/48336c86-bace-46f2-bb1a-34c15956ba8b) | **Com quê** — o stack de modelos locais por capacidade. |
| [Mapa de Conexões](https://claude.ai/code/artifact/01572022-66d9-489b-875c-ba82c3de2baa) | **Como se ligam** — orquestrador, estado, modelos, guardrails, feedback. |
| [O Entregável](https://claude.ai/code/artifact/f07b8bbd-1fe1-463e-b695-e7953190d298) | **O que o usuário recebe** — a jornada e um carrossel pronto de 8 slides. |
| [Solo até Agência](https://claude.ai/code/artifact/00392daf-35bb-4506-8932-8661606ea5eb) | **Produto e interface** — revelação progressiva, as telas, os 3 ritmos, o frontend. |
| [Uma GPU, Três Pistas](https://claude.ai/code/artifact/04f5eb2d-f7d3-4f27-aec4-61539cd819ca) | **Paralelismo** — onde o fan-out é legítimo e como sobrepor GPU, CPU e rede. |

## As decisões que sustentam a proposta

1. **Esqueleto barato + materialização *lazy*.** Planejar o ano é planejar a *estrutura*
   (campanhas + slots datados, sem LLM por slot) e materializar os posts numa **janela rolante
   de 2–4 semanas**. *(→ doc 2, §1)*
2. **Flex slots.** ~20–30% da cadência fica **vazia de propósito**, para absorver trends e
   conteúdo reativo. Calendário 100% preenchido não surfa trend. *(→ doc 2, §1)*
3. **O Brand Kit é o contrato visual.** Consistência é **imposta** em três pontos —
   condicionamento na geração, moldura no motor de slides e portão no critic. *(→ doc 2, §1-bis)*
4. **Local-first por contrato + factory.** Toda capacidade de IA tem provider local padrão;
   nuvem é troca opcional. Dados da marca não saem da máquina. *(→ doc 3)*
5. **Padrão arquitetural nomeado:** híbrido **orquestrador–trabalhador + pipeline sequencial +
   loop de feedback**. *(→ doc 3; diagrama no Mapa de Conexões)*
6. **Carrossel é o caminho padrão, não vídeo.** Exige um **motor de slides** que o repositório,
   vídeo-first, não tinha. *(→ doc 4 — **entregue**)*
7. **Multi-tenant no modelo, revelação progressiva na UI.** Solo é uma agência com um cliente —
   e nunca vê a palavra "cliente". *(→ doc 5)*
8. **Sem fine-tuning.** O gargalo é contexto de marca, não habilidade do modelo; o substituto é
   o **acervo próprio como few-shot** — dado primário, por cliente, agnóstico de provider.
   *(→ doc 3, §8-bis)*
9. **Paralelismo por classe de recurso.** Com **uma** GPU, fan-out ilimitado só vira fila: o
   ganho vem de separar GPU/CPU/rede e **sobrepor** os estágios. *(→ doc 7)*
10. **A pista da GPU se divide quando dois modelos cabem.** Texto + imagem residentes juntos
    fazem `copy` e `arte` rodarem simultaneamente — e o par é complementar (LLM é limitado por
    banda de memória, difusão por computação). Acima de ~85% da VRAM, porém, vira *thrashing*
    e fica **pior** que serializar. *(→ doc 7, §3-bis)*

## Sprints no board

Todos os cards estão semeados em `board/seed.py` (→ `/api/board`): **112 cards**.

| Sprint | Tema | Cards |
|---|---|---|
| 11 | Fundação: Marca & Carrossel | multi-tenant, `CompanyProfile`/`BrandKit`, onboarding + preview, presets, **`Slide`** ✅, copy de carrossel, **motor de layout** ✅, publisher de carrossel, condicionamento de estilo, portão de consistência, capacidade `vision`, URL pública, testes | 14 |
| 12 | Planejamento anual | `AnnualPlan`/`Campaign`/`PlanSlot`, calendário comercial, esqueleto + flex slots, materializador lazy, endpoints, agendador por data, aba Planejamento, testes | 8 |
| 13 | Regionalização & Trends | `Region` + localização, `trend_scout`, gate de brand-safety, acervo próprio como few-shot, re-planejamento trimestral, registry `vision`/IP-Adapter, testes | 7 |
| 14 | Operação de agência | `Activity`, tela **Hoje**, **link de aprovação**, tela de Campanha, Todos os clientes, relatório, testes | 7 |
| 15 | Frontend | rotas reais, **Base UI**, **Motion**, TanStack Query, dnd-kit, **R3F** (escopo restrito) | 6 |
| 16 | Escala e paralelismo | **ordem explícita 1→7**: medir · perfil de GPU + tuning · executor com semáforo (classe + modelo residente) · pipelining · anti-*thrashing* · materializador em lote · fronteira na delegação. Opcionais: `vllm`, MPS | 9 |

✅ = já entregue.

## Entregas realizadas

| Entrega | O que saiu |
|---|---|
| [`motor-de-slides.md`](../entregas/motor-de-slides.md) | `Slide` + `BrandKit` + `render_carousel` — carrossel em PNG 1080×1350 com a identidade da marca em todos os slides. 44 testes. |
</content>
