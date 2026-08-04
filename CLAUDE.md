# CLAUDE.md — Convenções do Auto Niche Engine

Instruções para qualquer sessão de IA trabalhando neste repositório.

## Regra de entrega (obrigatória)

**Toda entrega** (feature, correção relevante ou card de sprint concluído) **deve
incluir um arquivo Markdown estilo mensagem de Pull Request** em
`docs/entregas/<slug>.md`, contendo:

1. **Resumo** — o que foi entregue, em 1–2 frases.
2. **Motivação** — por que foi feito.
3. **O que mudou** — tabela de arquivos e mudanças.
4. **Como funciona** — visão técnica / fluxo.
5. **Como validar** — comandos (testes e/ou verificação ao vivo).
6. **Critério de aceite** — checklist do que define "pronto".
7. **Pendências / próximos** — o que fica para depois.

O MD é commitado **junto** com a entrega e seu caminho é citado na resposta.

## Fluxo de trabalho

- **Testes antes do commit**: rode `pytest -q` (deve ficar verde) e, no frontend,
  `cd web && npm run build`.
- **Kanban como fonte de verdade do roadmap**: reflita o estado no board
  (`board/seed.py` + API `/api/board`). Ao concluir um card, mova-o para `done`.
- **Commits**: mensagem em português, terminando com o rodapé
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Branches**: `main` e `claude/new-session-heke9n` (ambas recebem push).

## Segurança e escopo

- **Segredos nunca no git nem no chat**: chaves/tokens só no `.env` (que está no
  `.gitignore`). Ao pedir credenciais, oriente o uso do `.env`.
- **Sem automação de evasão de detecção** (fingerprint spoofing, proxies por
  conta, DM em massa). Publicação **apenas via APIs oficiais**, nas regras de
  cada rede.

## Arquitetura (padrão a seguir)

Cada capacidade externa é um **contrato + factory selecionável por config/env**
(veja `agents/media/factory.py` e `publishers/factory.py`):

| Capacidade | Factory | Providers |
|---|---|---|
| imagem | `get_image_generator` | placeholder \| stability \| gemini |
| voz | `get_voice_generator` | placeholder \| elevenlabs |
| vídeo | `get_video_generator` | none \| gemini (Veo) |
| publicação | `get_publisher` | none \| youtube \| instagram \| tiktok |

Novos provedores/modelos entram por esse mesmo padrão (ver Sprint 9 no board).

## Como rodar

```bash
docker compose up -d --build          # ollama + api + web
docker compose --profile bot up -d    # + bot do Telegram (opcional)
```

- Web: http://localhost:3000 · API: http://localhost:8000 · Ollama: :11434
- Testes: `pytest -q` (raiz). Config de exemplo: `config.example.json` → `config.json`.
