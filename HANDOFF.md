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
├── config.example.json       # Modelo de config (copiar → config.json)
├── requirements.txt          # streamlit, requests
├── requirements-dev.txt      # pytest (testes)
├── .gitignore                # ignora config.json, output/, __pycache__
├── README.md
├── HANDOFF.md                # este arquivo
├── agents/
│   ├── __init__.py
│   ├── ollama_client.py      # ✅ Cliente Ollama compartilhado (query + parse JSON)
│   ├── niche_creator.py      # ✅ Agente de estratégia via Ollama (GPU local)
│   ├── script_writer.py      # ✅ Agente roteirista cena-a-cena (Ollama)
│   └── video_pipeline.py     # ✅ Esqueleto de montagem de vídeo (FFmpeg)
├── dashboard/
│   └── app.py                # ✅ Painel do Criador (Streamlit)
└── tests/                    # ✅ Testes offline (14) de parsing JSON e de cenas
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
- **`tests/`** — 14 testes offline (pytest) do parsing de JSON (`OllamaClient`)
  e da montagem de cenas (`build_scenes`). Rodar: `pytest`.

Estado: tudo compila; os testes passam (`14 passed`); CLI falha de forma limpa
quando o Ollama não está no ar.

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

- [x] **Agente de roteiro cena-a-cena** — feito em `agents/script_writer.py`
      (`ScriptWriterAgent` → `list[Scene]` / `VideoJob`).
- [x] **Testes automatizados dos parses de JSON** — feito em `tests/`
      (`OllamaClient.extract_json` e `build_scenes`).
- [ ] **Gerador de imagem plugável** (ex: Stable Diffusion local / API) no hook
      `image_generator`.
- [ ] **Gerador de voz plugável** (TTS: ElevenLabs ou alternativa local) no
      hook `voice_generator`.
- [ ] **Legendas/burn-in** de texto no vídeo (drawtext do FFmpeg).
- [ ] **Publicação via API oficial** de uma plataforma (começar por uma só).
- [ ] Testes do **fluxo do pipeline** (render/concat) — hoje só o parsing tem
      cobertura; falta um teste de integração do `VideoPipeline` (mockando
      FFmpeg ou os geradores).

## 7. Convenções

- Código e docs em **português**.
- Commits terminam com o rodapé `Co-Authored-By` / `Claude-Session`.
- `config.json` nunca é commitado (está no `.gitignore`).
- Nada de camada de evasão de detecção (ver seção 3).
