# Personas

> Derivadas de tudo que foi decidido nos documentos de planejamento. Servem para **decidir
> disputas de escopo**: quando duas soluções parecem boas, ganha a que serve a persona daquela
> tela. Cada uma traz o que **nunca** deve ver — é isso que sustenta a
> [revelação progressiva](./produto-agencia-exibicao-e-frontend.md).

## Mapa rápido

| Persona | Papel | Onde vive | Ritmo |
|---|---|---|---|
| **Marina** | dona de loja (solo) | Hoje · celular | 10 min/semana |
| **Rafa** | social media da agência | Hoje · Produção · Calendário | o dia todo |
| **Bia** | diretora de arte | Post · Marca | por lote |
| **Caio** | dono da agência | Todos os clientes · Desempenho | diário (visão) |
| **Dra. Helena** | cliente da agência | Aprovação (link) | por ciclo |
| **Léo** | operador técnico | Config · Modelos | na instalação |

---

## 1. Marina — dona de loja · *a barreira de entrada*

**Contexto.** Tem uma loja de velas artesanais, toca tudo sozinha. Sabe que precisa postar,
mas o Instagram é a última coisa do dia. Já tentou três ferramentas e abandonou todas no
cadastro.

- **Objetivo:** ter presença constante sem virar social media.
- **Dor:** não sabe *o que* postar; quando sabe, não tem tempo de fazer a arte.
- **Sucesso:** publicou 12 posts no mês sem pensar no assunto.
- **Usa:** onboarding, **Hoje**, Post (aprovar), Desempenho (superficial).
- **Nunca deve ver:** "cliente", "workspace", papéis, responsáveis, atividades da equipe,
  configuração de modelo de IA.
- **Decisão que ela dita:** o onboarding tem de caber em **uma tela** e entregar o
  **preview de 3 posts** antes de qualquer ajuste. Se ela precisar escolher um pilar de
  conteúdo para começar, perdemos.

## 2. Rafa — social media / atendimento de agência · *o usuário de maior frequência*

**Contexto.** Cuida de **12 clientes** numa agência de 6 pessoas. Vive entre briefings,
aprovações atrasadas e "posta hoje ainda?".

- **Objetivo:** fechar o dia sem nada pendente e sem cliente cobrando.
- **Dor:** trocar de contexto entre clientes; perder feedback espalhado em WhatsApp e e-mail.
- **Sucesso:** a caixa de entrada zerou e a semana seguinte já está aprovada.
- **Usa:** **Hoje** (tela inicial), Produção (Kanban), Calendário, Campanha, link de aprovação.
- **Precisa:** **densidade** — ver muita coisa num relance, estado codificado em forma *e* cor,
  atalhos de teclado, trocar de cliente sem recarregar o mundo.
- **Decisão que ele dita:** as telas operacionais são **2D e densas** — é o uso dele, dezenas
  de vezes ao dia, que desaconselha 3D fora da landing e da hélice do ano. Também é ele que
  exige que **todo comentário do cliente vire uma atividade** com responsável e prazo.

## 3. Bia — diretora de arte · *a guardiã do padrão*

**Contexto.** Responde pela cara de cada marca. Desconfia de conteúdo gerado por IA — e com
razão: já viu ferramentas entregarem 8 slides com 8 estilos diferentes.

- **Objetivo:** que todo post pareça feito pelo estúdio, não por um gerador.
- **Dor:** retrabalho — receber material fora do padrão e ter que refazer.
- **Sucesso:** aprovou o lote sem tocar em nada.
- **Usa:** **Marca** (Brand Kit), Post (ajustar slides), portão de consistência.
- **Decisão que ela dita:** os **três pontos de imposição do padrão** existem por causa dela —
  condicionamento na geração (fotos da estética), **moldura no motor de slides** e **portão
  no critic**. Ela é a razão de o carrossel ser renderizado por um **motor de layout
  determinístico**, e não deixado a cargo do modelo.

## 4. Caio — dono da agência · *quem decide a compra*

**Contexto.** Cresceu de 4 para 12 clientes e a operação começou a vazar. Avalia se a
ferramenta escala o time sem contratar mais gente.

- **Objetivo:** mais clientes por pessoa, sem cair a qualidade.
- **Dor:** não enxerga carga, atrasos nem quem está afogado.
- **Sucesso:** absorveu 3 clientes novos com a mesma equipe.
- **Usa:** **Todos os clientes**, Desempenho, Campanha (macro).
- **Decisão que ele dita:** **multi-tenant desde o dia 1**. Se a ferramenta obrigasse a migrar
  de conta ao crescer, ele não compraria. Também é dele a exigência de **relatório por cliente**
  para mostrar valor na renovação.

## 5. Dra. Helena — cliente da agência · *a usuária externa*

**Contexto.** Tem uma clínica; contratou a agência justamente para **não** cuidar disso.
Aprova no celular, entre consultas.

- **Objetivo:** aprovar rápido, sem aprender ferramenta nenhuma.
- **Dor:** receber PDF/print por WhatsApp e não saber o que já foi resolvido.
- **Sucesso:** abriu o link, deslizou os slides, aprovou. Levou 2 minutos.
- **Usa:** **só o link de aprovação**. Sem login, sem cadastro, sem app.
- **Nunca deve ver:** custo, plano anual, quem produziu, backlog, qualquer menção a IA.
- **Decisão que ela dita:** aprovação é **link público com token**, otimizado para **celular**,
  com **comentário por slide**. Ela é a razão de o cliente **não ser um assento** no sistema.

## 6. Léo — operador técnico · *quem instala*

**Contexto.** Dev/entusiasta que sobe o projeto na própria máquina com GPU. Pode ser o cara de
TI da agência ou o próprio dono técnico.

- **Objetivo:** rodar tudo local, sem chave de API e sem mandar dado da marca para fora.
- **Dor:** stacks que exigem 5 serviços na nuvem para funcionar.
- **Sucesso:** `docker compose up` e o pipeline roda offline.
- **Usa:** config, **Modelos** (registry), logs, `.env`.
- **Decisão que ele dita:** **local-first por contrato + factory**, degradação graciosa
  (`placeholder`/`none` quando falta GPU) e **nuvem como opt-in**. É por causa dele que
  privacidade ("os dados da marca não saem da máquina") é argumento de venda, não detalhe.

---

## Como as personas resolvem disputas

| Disputa | Quem ganha | Resultado |
|---|---|---|
| Onboarding completo × rápido | **Marina** | 1 tela + preview; ajuste fino é opcional |
| Tela bonita × densa (operação) | **Rafa** | densidade e varredura nas telas diárias |
| Velocidade de geração × padrão de marca | **Bia** | portão de consistência bloqueia o fora do padrão |
| Simples agora × escalar depois | **Caio** | modelo multi-tenant, UI progressiva |
| Cliente como usuário × como convidado | **Dra. Helena** | link sem login |
| Nuvem × local | **Léo** | local por padrão, nuvem opt-in |

## Anti-persona

**Quem a ferramenta não atende (por ora):** a marca que quer **conteúdo 100% autoral e
artesanal**, sem qualquer automação — e o operador que quer **crescimento por automação de
massa** (bots, DM em escala, múltiplas contas por fingerprint). O segundo caso é
**explicitamente fora de escopo** (ver [`CLAUDE.md`](../../CLAUDE.md)): publicação só por APIs
oficiais.
</content>
