# Entrega: planejamento da geração automática de posts (marketing anual + IA local)

> Entrega de **documentação/arquitetura** — fase de escopo das Sprints 11–13.
> Nenhum código de produção foi alterado.

## Resumo

Documenta a proposta completa de uma ferramenta que planeja e produz o conteúdo de **qualquer
empresa** para o **ano inteiro**: onboarding com Brand Kit, calendário editorial anual com
regionalização e trends, um **time de marketing completo** modelado como agentes, e a
**arquitetura de IA local-first** que sustenta tudo — com três apresentações visuais e as
fontes que embasaram cada decisão.

## Motivação

O motor hoje gera **ideias soltas a partir de um prompt**. Uma empresa precisa de
**consistência, variedade e timing**: postar nos dias certos, variar formatos, cobrir datas
sazonais e manter a **identidade visual** em todo post. Antes de escrever código para isso,
era preciso fechar as decisões estruturais — especialmente **como planejar um ano sem gerar
300 posts de uma vez** e **como impor o padrão de marca** — e registrá-las de forma que
qualquer sessão futura (ou pessoa) continue de onde paramos.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `docs/planejamento/README.md` (novo) | Índice da proposta: documentos, artefatos, as 5 decisões que a sustentam e as sprints. |
| `docs/planejamento/calendario-posts-loja-instagram.md` (novo) | Escopo inicial: calendário **mensal** de uma loja (modelo de dados, agente, endpoints, aba Calendário). |
| `docs/planejamento/arquitetura-planejamento-anual.md` (novo) | Arquitetura **anual**: hierarquia de 5 níveis, esqueleto + materialização lazy, onboarding/Brand Kit, regionalização, trends, agência virtual (17 papéis). |
| `docs/planejamento/arquitetura-ia-modelos-locais.md` (novo) | Arquitetura de **IA local-first**: capacidade → factory → providers, stack offline, capacidades novas (visão, referência de estilo), modelos por VRAM. |
| `docs/planejamento/referencias-artigos.md` (novo) | Artigos consultados, contribuição de cada um, mapeamento fonte→decisão e ressalva de acesso. |
| `docs/entregas/planejamento-marketing-anual-ia.md` (novo) | Este documento. |

Artefatos publicados (fora do repo):
[Agência Virtual](https://claude.ai/code/artifact/b4480a28-0ccb-4450-ba3b-696e9aa739fe) ·
[IA Local-First](https://claude.ai/code/artifact/48336c86-bace-46f2-bb1a-34c15956ba8b) ·
[Mapa de Conexões](https://claude.ai/code/artifact/01572022-66d9-489b-875c-ba82c3de2baa)

## Como funciona

A proposta se apoia em cinco decisões:

1. **Esqueleto barato + materialização lazy** — o ano é planejado como *estrutura*
   (`AnnualPlan` → `Campaign` → `PlanSlot`, sem LLM por slot) e os posts só viram `Idea`
   completa numa **janela rolante de 2–4 semanas**. Reusa o `autogen_tick` do `scheduler.py`.
2. **Flex slots** — ~20–30% da cadência fica vazia para absorver **trends** e conteúdo reativo.
3. **Brand Kit como contrato visual** — consistência imposta em 3 pontos: condicionamento na
   geração (fotos da estética como referência de estilo), moldura no `render.py` e **portão**
   no `critic.py`.
4. **Local-first por contrato + factory** — todas as capacidades de IA têm provider local
   padrão (Ollama, A1111/ComfyUI, Piper); nuvem é troca opcional por chave no `.env`.
5. **Padrão arquitetural** — híbrido **orquestrador–trabalhador + pipeline sequencial + loop
   de feedback**, com guardrails explícitos e o analista fechando o ciclo.

Fluxo resumido: `onboarding → Brand Kit → esqueleto do ano → (janela) materializa → agentes
+ modelos locais → guardrails → render → publica na data/hora local → métricas → replaneja`.

## Como validar

```bash
# suíte atual (a documentação não altera comportamento)
python3 -m pytest -q          # 151 passed

# leitura da proposta, na ordem
docs/planejamento/README.md
docs/planejamento/arquitetura-planejamento-anual.md
docs/planejamento/arquitetura-ia-modelos-locais.md
docs/planejamento/referencias-artigos.md
```

> Nota: neste container o `pytest` do `PATH` é um tool isolado (uv) sem as dependências do
> projeto — rode `python3 -m pytest -q` (mesmo interpretador do `pip install -r requirements*.txt`).

## Critério de aceite

- [x] Escopo mensal documentado (modelo de dados, agente, endpoints, UI).
- [x] Arquitetura anual com hierarquia, materialização lazy e flex slots.
- [x] Onboarding para **qualquer segmento** + Brand Kit, com o padrão de marca imposto em 3 pontos.
- [x] Regionalização (fuso, feriados locais, tom, clima, idioma) e trends com **gate de brand-safety**.
- [x] Time de marketing completo mapeado (17 papéis → agentes; 14 já existentes).
- [x] Arquitetura de IA local-first documentada, com as 2 capacidades novas (visão, referência de estilo).
- [x] Diagrama de conexões e apresentações visuais publicados e linkados.
- [x] Fontes registradas com contribuição e ressalvas de acesso.
- [x] `python3 -m pytest -q` verde (151 testes).

## Pendências / próximos

- **Semear os cards das Sprints 11–13 em `board/seed.py`** (o roadmap ainda não está no board).
- Decidir a **fonte de trends** do MVP — recomendação: sinal interno (`analyst`) + curadoria
  manual, deixando API de terceiros plugável.
- Decidir se o modelo de texto padrão sobe de `llama3` para `llama3.1`/`qwen2.5` (PT-BR).
- Resolver a **hospedagem do criativo por URL pública** — bloqueia a publicação real na Graph API.
- Revalidar no texto original os números vindos de blogs bloqueados pelo proxy (janela de
  2–4 semanas, % de folga reativa).
</content>
