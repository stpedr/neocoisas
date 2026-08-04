# Auto Niche Engine — Handoff / Contexto de Continuação

> Documento de passagem de bastão. Resume o objetivo, o que já foi construído,
> as decisões importantes e o que falta — para retomar o trabalho em outra
> sessão sem perder contexto.

---

## 1. Objetivo do projeto

Construir o **Auto Niche Engine**: um pipeline multi-agente que produz
conteúdo de nicho para redes sociais usando **IA local** (Ollama rodando na
GPU da própria máquina, custo zero de inferência). O sistema gera estratégia
de nicho + roteiros, monta vídeos curtos localmente (FFmpeg) e — futuramente —
publica nas plataformas.

Base: manual técnico `auto_niche_engine_manual.pdf` (em português), que
descreve 7 agentes (roteirista, prompt engineer, voz/TTS, analista, e
publishers de TikTok/Instagram/YouTube).

## 2. Repositório e branch

- **Repo:** `stpedr/neocoisas`
- **Branch de trabalho:** `claude/new-session-heke9n` (já com push feito)
- **Commit inicial:** `f2ead73` — "Scaffold Auto Niche Engine..."

## 3. Decisão de escopo importante (ler antes de continuar)

Foi implementado apenas o **núcleo legítimo de geração de conteúdo**.

**Deixado de fora de propósito** (viola os Termos de Uso das plataformas e
não será construído): a camada de *publicação automática em massa* com
*evasão de detecção* — fingerprint spoofing (AdsPower/Multilogin), proxies
residenciais por conta para evitar "bloqueios cruzados", automação de DM por
gatilho. O caminho sustentável para publicação é usar as **APIs oficiais**
(Meta Graph API, YouTube Data API, TikTok Content Posting API) dentro das
regras de cada rede.

## 4. Estrutura atual (o que já existe)

```
neocoisas/
├── main.py                   # Orquestrador CLI: estratégia + (--script) roteiro
├── server.py                 # ✅ API FastAPI (ideias + Kanban) p/ o frontend
├── engine.py                 # ✅ Orquestração: prompt → ideias → (revisão|post)
├── docker-compose.yml        # ✅ Stack: ollama + api + web
├── Dockerfile.api            # ✅ Imagem da API
├── config.example.json       # Modelo de config (copiar → config.json)
├── requirements.txt          # streamlit, requests, fastapi, uvicorn
├── requirements-api.txt      # deps enxutas da API (Docker)
├── requirements-dev.txt      # pytest (testes)
├── .github/workflows/ci.yml  # ✅ CI: pytest + next build
├── agents/
│   ├── ollama_client.py      # ✅ Cliente Ollama (query + parse JSON, overrides por env)
│   ├── niche_creator.py      # ✅ Agente de estratégia via Ollama
│   ├── script_writer.py      # ✅ Agente roteirista cena-a-cena
│   ├── idea_generator.py     # ✅ Brainstorm de conceitos + roteiro → list[Idea]
│   └── video_pipeline.py     # ✅ Esqueleto de montagem de vídeo (FFmpeg)
├── review/                   # ✅ Idea + ReviewQueue (fila de aprovação, JSON)
├── board/                    # ✅ Card + BoardStore + seed (Kanban de sprints)
├── dashboard/app.py          # ✅ Painel do Criador (Streamlit legado)
├── web/                      # ✅ Frontend Next.js 14 (abas Ideias/Tinder e Kanban)
└── tests/                    # ✅ 47 testes offline (parsing, fila, engine, board)
```

### Detalhes do que já está pronto

- **`agents/ollama_client.py`** — `OllamaClient`: encanamento comum a todos os
  agentes (carrega config, `generate()` com erros claros via `OllamaError`,
  `extract_json()` tolerante a cercas de código, texto extra e a topo `{}`/`[]`).
- **`agents/niche_creator.py`** — `LocalNicheAgent`: usa o `OllamaClient` para
  gerar o plano de estratégia em JSON (`account_profile`, `trending_topics`,
  `hashtags`). `OllamaError` segue reexportado daqui (compat. com `main.py`).
- **`agents/script_writer.py`** — `ScriptWriterAgent`: transforma um tópico num
  roteiro cena-a-cena. `write_script()` devolve `list[Scene]`; `build_video_job()`
  já embrulha num `VideoJob` pronto para o `VideoPipeline`. `build_scenes()` é a
  função pura (sem Ollama) que normaliza os campos e é coberta por testes.
- **`agents/video_pipeline.py`** — `VideoPipeline` + dataclasses `Scene` e
  `VideoJob`. Sequência real com FFmpeg: imagem + narração → clipe →
  concatenação em 1080×1920. Geradores de **imagem** e **voz** são pontos de
  extensão (`hooks`) a conectar. Ainda **não** tem geradores reais plugados.
- **`dashboard/app.py`** — painel Streamlit: define nicho, salva config,
  dispara geração de estratégia, mostra o JSON.
- **`main.py`** — entrada CLI: `python main.py "Nicho"`. Com `--script`, encadeia
  estratégia → roteiro do 1º `trending_topic`.
- **`review/`** — `Idea` (com estados) + `ReviewQueue` (persistência JSON,
  aprovar/rejeitar/postar). **`board/`** — `Card` + `BoardStore` + `seed` do
  Kanban (auto-semeia o plano de sprints).
- **`engine.py`** — `generate_and_enqueue` + `post_approved` (modos manual/auto;
  `publisher` é gancho para APIs oficiais). **`server.py`** — API FastAPI.
- **`agents/idea_generator.py`** — `IdeaGenerator` (brainstorm + roteiro por
  conceito); `build_idea_concepts` puro/testado.
- **`web/`** — frontend Next.js 14: aba **Ideias** (Tinder: aprovar/rejeitar,
  modos manual/auto) e aba **Kanban** (arrastar-e-soltar, plano de sprints).
- **Docker** — `docker compose up -d --build` sobe ollama + api + web.
- **`tests/`** — 47 testes offline (pytest): parsing, `ReviewQueue`, `engine`,
  `BoardStore`, `build_idea_concepts`. Rodar: `pytest`.

Estado: tudo compila; os testes passam (`47 passed`); stack roda em Docker com
o Ollama containerizado; geração validada ponta-a-ponta.

## 5. Ponto de atenção: Ollama roda no PC do usuário

O código aponta para `http://localhost:11434` — a **máquina do usuário**. A
sessão do Claude Code roda num container na nuvem e **não** enxerga o Ollama
local. Portanto, o passo de "falar com o Ollama de fato" é executado pelo
usuário, na máquina dele:

```bash
ollama run llama3
cp config.example.json config.json
pip install -r requirements.txt
python main.py            # ou: streamlit run dashboard/app.py
```

Verificação rápida se o Ollama está no ar: `curl http://localhost:11434/api/tags`

Tudo que **não** depende do Ollama ligado pode ser construído na sessão em
nuvem e deixado pronto.

## 6. Próximos passos (candidatos)

Concluído nesta fase (Sprints 0–1):

- [x] **Agente de roteiro cena-a-cena** (`agents/script_writer.py`).
- [x] **Esteira de aprovação** — `review/`, `agents/idea_generator.py`, `engine.py`
      (modos manual/auto).
- [x] **API FastAPI** (`server.py`) + **frontend Next.js** (`web/`): abas
      Ideias (Tinder) e Kanban.
- [x] **Kanban** com o plano de sprints (`board/`).
- [x] **Docker** (ollama + api + web) — `docker compose up -d --build`.
- [x] **Testes** — 47 passando (parsing, fila, engine, board).
- [x] **CI** — GitHub Actions (`.github/workflows/ci.yml`).

Próximas fases (Sprints 2–4 — dependem de serviços/credenciais externas):

- [ ] **Gerador de imagem plugável** no hook `image_generator` (Stable Diffusion / API).
- [ ] **Gerador de voz/TTS plugável** no hook `voice_generator`.
- [ ] **Legendas/burn-in** (drawtext do FFmpeg) e **teste de integração** do
      `VideoPipeline` (mockando FFmpeg).
- [ ] **Ligar a renderização à esteira** — render da `Idea` aprovada → `video_path`.
- [ ] **Publicação via API oficial** (o gancho `publisher` do `engine.py`) —
      começar por uma plataforma; + OAuth e agendamento.
- [ ] **Deploy** do backend e do frontend (o Ollama roda na máquina do usuário).

## 7. Convenções

- Código e docs em **português**.
- Commits terminam com o rodapé `Co-Authored-By` / `Claude-Session`.
- `config.json` nunca é commitado (está no `.gitignore`).
- Nada de camada de evasão de detecção (ver seção 3).
