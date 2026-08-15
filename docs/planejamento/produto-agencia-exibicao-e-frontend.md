# Produto: barreira baixa → operação de agência · exibição, fluxo e frontend

> **Status:** proposta · **Alvo:** Sprints 11–14
> Responde a três perguntas: (1) como ter **barreira de entrada baixa** e ainda servir
> **qualquer agência**; (2) como **campanhas e atividades** acompanham o dia a dia; (3) o que
> muda no **frontend** (exibição, fluxo, stack).

## 1. A tensão central — e como resolvê-la

| | Dono de loja (dia 1) | Agência (dia 100) |
|---|---|---|
| Quer | postar sem pensar | operar 15 clientes, com equipe e prazos |
| Tolera | ~5 min de setup | onboarding por cliente, papéis, aprovação |
| Mata o produto | qualquer ceremônia | qualquer teto de escala |

**Decisão:** o **modelo de dados é multi-tenant desde o dia 1; a interface esconde isso até
ser necessário.** Um usuário solo é, tecnicamente, uma agência com **um** cliente — e nunca vê
a palavra "cliente". Ao cadastrar o segundo, o **modo agência** aparece sozinho.

> Retrofit de multi-tenant é caro; esconder complexidade é barato. Por isso a hierarquia
> nasce completa e a UI **revela progressivamente**.

```
Workspace (conta)
└── Client (= CompanyProfile + BrandKit)   ← solo: existe 1, invisível na UI
    ├── AnnualPlan → Campaigns → PlanSlots → Ideas (posts)
    └── Activities (a operação)
```

### Revelação progressiva (o que aparece, e quando)

| Gatilho | O que a UI passa a mostrar |
|---|---|
| início | 1 formulário → calendário → posts. Sem menções a cliente/equipe. |
| 2º cliente | **seletor de cliente** no topo + visão "Todos os clientes" |
| 2º usuário | responsável nas atividades, filtro "meus" |
| 1º cliente externo | **link de aprovação** (o cliente não vira usuário do sistema) |

## 2. Campanhas e atividades — a camada operacional

O repositório **já tem um Kanban** (`board/models.py`: `Card`, colunas `backlog → todo →
in_progress → review → done`) que hoje rastreia as sprints do projeto. **É essa peça que
vira a operação de conteúdo** — reúso, não invenção.

### 2.1. `Activity` (generaliza `Card`)

```python
@dataclass
class Activity:
    id: str; client_id: str
    title: str
    kind: str            # briefing | produção | revisão | aprovação_cliente
                         # | ajuste | agendamento | publicação | relatório
    status: str          # backlog | fazendo | revisão | aguardando_cliente | pronto
    assignee: str | None = None
    due_date: str | None = None
    campaign_id: str | None = None   # ligada a uma campanha
    idea_id: str | None = None       # ligada a um post concreto
    source: str = "auto"             # auto (gerada pelo plano) | manual
```

**A ligação que importa:** cada `PlanSlot` materializado **gera atividades automaticamente**
(produzir → revisar → aprovar → agendar). A agência também **cria atividades manuais**
(reunião de briefing, relatório mensal, sessão de fotos) — as duas convivem no mesmo quadro.
É isso que faz o sistema acompanhar o dia a dia **por completo**, e não só o que a IA gerou.

### 2.2. Campanhas como unidade de trabalho

`Campaign` deixa de ser só uma âncora de calendário e ganha rosto operacional: prazo,
responsável, orçamento/meta, atividades e os posts que a compõem. Uma tela de campanha mostra
**arco (teaser→oferta→última chamada) + tarefas + status de aprovação** num lugar só.

### 2.3. Aprovação do cliente — o fluxo que as ferramentas erram

O cliente da agência **não é um assento** no sistema. Ele recebe um **link público de
aprovação** (token, sem login) onde vê os posts do período, **aprova ou comenta por slide**.
Cada comentário vira uma `Activity` de ajuste atribuída a alguém da equipe.

## 3. Formas de exibição (as telas)

| Tela | Para quê | Uso |
|---|---|---|
| **Hoje / Caixa de entrada** | "o que precisa de mim agora": aprovações pendentes, feedback do cliente, prazos de hoje | **tela inicial** · diário |
| **Calendário (mês)** | grade do mês; arrastar para replanejar; badge de pilar/formato/status | diário/semanal |
| **Ano / Linha do tempo** | 12 meses, campanhas e sazonalidade numa só vista | mensal/trimestral |
| **Produção (Kanban)** | atividades por status, responsável e prazo | diário |
| **Post (detalhe)** | slides do carrossel, legenda, hashtags, variantes por região | ao revisar |
| **Campanha** | arco, posts, tarefas, resultado | por campanha |
| **Marca / Cliente** | Brand Kit, perfil, regiões, presets | raro |
| **Aprovação (externa)** | link sem login para o cliente aprovar/comentar | por ciclo |
| **Desempenho** | métricas por post/campanha/cliente; insights do analista | semanal/mensal |
| **Todos os clientes** *(agência)* | carga por cliente/pessoa, o que está atrasado | diário (gestor) |

**Princípio de exibição:** as telas de **operação** (Hoje, Kanban, Calendário) priorizam
**densidade e varredura** — muitos itens legíveis num relance, estado codificado em forma
**e** cor. As telas de **apresentação** (Ano, Campanha, Aprovação) podem ser mais generosas
visualmente, porque são vistas com menos frequência e por mais gente.

## 4. Fluxo — os três ritmos

```
DIÁRIO      Hoje → aprova/ajusta o que chegou → responde feedback do cliente
SEMANAL     revisa a semana materializada → dispara aprovação do cliente (link)
TRIMESTRAL  Ano → analista mostra o que performou → replaneja pilares e campanhas
```

E o **fluxo de entrada** (a barreira baixa), com meta de **≤ 5 minutos**:

```
formulário (1 tela, campos essenciais + fotos)
   → Brand Kit gerado automaticamente (paleta/estilo extraídos das fotos)
   → prévia: 3 posts de exemplo na hora        ← o "aha" antes de qualquer configuração
   → aceitar → calendário do ano montado
```

> O **preview imediato** é o que derruba a barreira: o usuário vê a marca dele aplicada
> **antes** de configurar qualquer coisa. Configuração fina (pilares, cadência, regiões) fica
> em "ajustes avançados", nunca no caminho crítico.

## 5. Frontend — o que muda de fato

### 5.1. Next.js: **já é**

`web/` roda **Next 14.2.15 (App Router) + React 18**, com `next`/`react`/`react-dom` e nada
mais — **zero bibliotecas** de UI, estado ou animação. Então a questão não é "mudar para
Next", e sim **o que colocar em cima**. As 5 telas atuais são abas trocadas em `page.tsx`
(103 linhas); a evolução pede **rotas reais** (`/hoje`, `/calendario`, `/ano`,
`/producao`, `/cliente/[id]`, `/aprovacao/[token]`) e Server Components onde couber.

### 5.2. Animação: **Motion** (ex-Framer Motion) — recomendação clara

É a melhor opção para React/Next hoje, e aqui ela **trabalha**, não decora:

| Recurso | Onde serve |
|---|---|
| `layoutId` (transição compartilhada) | card do calendário **vira** a tela do post |
| gestos + `drag` | arrastar post entre dias; Kanban de atividades |
| `AnimatePresence` | entrada/saída de itens da caixa de entrada |
| swipe | revisar carrossel slide a slide; aprovar/rejeitar |

Regra: toda animação respeita `prefers-reduced-motion` e nenhuma bloqueia a ação.

### 5.3. Three.js: **sim, mas com escopo cirúrgico**

Aqui vai minha recomendação honesta, e a decisão é sua. **3D numa ferramenta operacional de
uso diário atrapalha** — custa performance, prejudica varredura e acessibilidade, e pesa no
mobile, que é onde a aprovação acontece. Uma agência que abre o Kanban 40×/dia não quer
render 3D.

Onde o 3D **ganha o lugar** (via **React Three Fiber** + drei, que integra ao ciclo do React):

1. **Entrada / landing / onboarding** — primeira impressão. Reforça exatamente a sensação de
   "barreira baixa": algo vivo antes de qualquer formulário.
2. **Ano — a hélice do calendário** *(o melhor caso real)*: 365 dias não cabem numa grade
   legível; uma **espiral/hélice** mostra o ano inteiro num quadro só, com campanhas
   destacadas ao longo da curva. Aqui o 3D resolve um problema de densidade que o 2D não
   resolve bem.
3. **Cena da marca** *(opcional)* — os posts do mês flutuando com a paleta do cliente, para
   apresentação/reunião.

Onde **não** entra: Hoje, Kanban, Calendário-mês, Post, Aprovação. Todas com fallback 2D.

### 5.4. Biblioteca de UI: **Base UI** (headless, open-source)

O projeto já tem **identidade visual própria** (tokens, tema claro/escuro, a11y — Sprint 10) e
as telas propostas são densas e específicas (calendário, Kanban, carrossel). Então o que falta
**não é aparência** — é **comportamento acessível**: dropdown, dialog, popover, tabs, tooltip,
select, foco preso, navegação por teclado, ARIA correto. Reescrever isso à mão é onde
projetos quebram acessibilidade sem perceber.

Por isso a escolha é uma biblioteca **headless** (sem estilo), não uma "temada":

| Opção | Situação (2026) | Veredito |
|---|---|---|
| **Base UI** | do **criador do Radix** + Floating UI, mantida pela MUI; **v1.0 estável em 2026**; hoje a camada de primitivos **mais ativa** | **recomendada** |
| Radix Primitives | **adquirida pela WorkOS**; atualizações desaceleraram em vários componentes | evitar como aposta nova |
| shadcn/ui | forma mais comum de consumir primitivos, mas **exige Tailwind**; desde 2025 aceita Base UI por opt-in | só se adotarmos Tailwind |
| Headless UI | boa, porém escopo menor de componentes | insuficiente |
| Mantine / MUI / HeroUI | trazem **design próprio** | conflita com o nosso |

**Decisão:** adotar **Base UI** e **estilizar com os tokens CSS já existentes**. Ganhamos
acessibilidade de primeira linha sem herdar visual de terceiros e sem migrar para Tailwind —
a aparência continua sendo a nossa, igual à das apresentações.

> Se um dia o time preferir Tailwind, `shadcn/ui` roda **sobre Base UI** — o caminho continua
> aberto sem retrabalho de primitivos.

### 5.5. Stack proposta

| Camada | Escolha | Por quê |
|---|---|---|
| Framework | **Next 14+ App Router** (já existe) | rotas reais + Server Components |
| Componentes | **Base UI** (headless) | a11y pronta, estilizada pelos nossos tokens |
| Animação | **Motion** | transições compartilhadas, drag, gestos |
| 3D | **React Three Fiber + drei** | só na landing e na hélice do ano |
| Estado servidor | **TanStack Query** | polling de jobs, cache, revalidação |
| Drag & drop | **dnd-kit** | acessível (teclado), melhor que HTML5 DnD |
| Estilo | manter **CSS tokens** da Sprint 10 | design system já existe; não recomeçar |

> Não recomendo trocar o CSS por Tailwind agora: a Sprint 10 já entregou tokens, tema
> claro/escuro e a11y. Trocar seria custo sem ganho.

## 6. Cards

**Sprint 11-bis · Fundação de produto**
1. `Workspace`/`Client` (multi-tenant) + revelação progressiva na UI. `alta`, backend, frontend.
2. Onboarding em 1 tela + **preview de 3 posts na hora**. `alta`, frontend, backend.

**Sprint 14 · Operação de agência**
3. `Activity` (generaliza `Card`) + geração automática a partir dos slots. `alta`, backend.
4. Tela **Hoje / Caixa de entrada**. `alta`, frontend.
5. Tela de **Campanha** (arco + tarefas + posts). `média`, frontend.
6. **Link de aprovação do cliente** (token, sem login, comentário por slide). `alta`, backend, frontend.
7. Visão **Todos os clientes** (carga, atrasos). `média`, frontend.

**Sprint 15 · Frontend**
8. Rotas reais + Server Components. `alta`, frontend.
9. **Motion**: transições compartilhadas, drag, swipe do carrossel. `alta`, frontend.
10. **dnd-kit** no calendário e no Kanban (acessível). `média`, frontend.
11. **R3F**: hélice do ano + landing, com fallback 2D. `baixa`, frontend.

## 7. Critério de aceite

- [ ] Usuário novo publica o primeiro calendário em **≤ 5 min**, sem ver conceito de agência.
- [ ] Ao cadastrar o 2º cliente, o modo agência aparece **sem migração**.
- [ ] Atividades nascem automaticamente dos posts **e** podem ser criadas à mão.
- [ ] Cliente externo aprova por **link, sem login**, e comentários viram atividades.
- [ ] Telas operacionais mantêm densidade e funcionam **sem** 3D; 3D só na landing/hélice,
      com fallback e `prefers-reduced-motion` respeitado.
</content>
