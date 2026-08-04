# Entrega: Documentação final e publicação do projeto

> Sprint 4 · Deploy & Publicação — prioridade baixa.

## Resumo

Consolida a documentação do projeto: README reescrito como referência única (com
diagrama de arquitetura Mermaid, estrutura atual, guia de execução, troca de
modelos, automações e bot), arquivo **LICENSE (MIT)** e seção de convenções
apontando para o `CLAUDE.md`.

## Motivação

O README refletia um estágio inicial (foco em Streamlit/CLI). O projeto cresceu
muito (API, Next.js com 5 abas, factories de modelo, SQLite, bot, automações) e
precisava de um documento que permitisse rodar e entender tudo do zero.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `README.md` | Reescrito: diagrama Mermaid, tabela de factories por capacidade, estrutura atual, 5 abas, seção "Troca de modelos", nota de testes/CI, convenções e licença. |
| `LICENSE` (novo) | MIT. |

## Conteúdo do README

- **Arquitetura** em Mermaid (fluxo prompt → ideias → curadoria → revisão →
  render → agenda → publicação → analista) + o padrão *factory por capacidade*.
- **Execução**: Docker (`docker compose up -d --build`), dev sem Docker, CLI e
  Streamlit legado.
- **Troca de modelos** (endpoints `/api/models*` e aba ⚙️ Modelos).
- **Geração de mídia/publicação**, **automações**, **bot do Telegram**, **testes/CI**.

## Como validar

- Abrir o `README.md` (o diagrama Mermaid renderiza no GitHub).
- Seguir o guia "Rodar com Docker" do zero.

## Critério de aceite

- [x] README completo e reprodutível do zero.
- [x] Diagrama de arquitetura.
- [x] Licença definida (MIT).
- [x] Convenções documentadas (`CLAUDE.md`).

## Pendências / próximos

- Tornar `main` o branch **default** no GitHub (requer admin do dono `stpedr`).
- Cards restantes dependem de credenciais das plataformas (OAuth, coleta de
  métricas, publishers Instagram/TikTok, mais plataformas).
