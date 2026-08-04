"""Planejamento inicial do quadro Kanban (sprints até publicar o projeto).

Este é o estado semente do board: reflete o que já está pronto, o que está em
andamento e o que falta para **finalizar e publicar** o Auto Niche Engine.
O usuário edita/move os cartões livremente depois — a partir daí o board vive
no arquivo persistido, não aqui.
"""

# Cada item vira um Card. `column` posiciona no fluxo; `sprint` agrupa por fase.
SEED_CARDS: list[dict] = [
    # ---------------------------------------------------- Sprint 0 (feito) ---
    {
        "title": "Scaffold do projeto (agentes, pipeline, painel)",
        "description": "Estrutura inicial: agente de estratégia (Ollama), esqueleto "
        "do pipeline de vídeo e painel Streamlit.",
        "column": "done",
        "sprint": "Sprint 0 · Fundação",
        "labels": ["backend"],
    },
    {
        "title": "Cliente Ollama compartilhado",
        "description": "OllamaClient com generate() e extract_json() (tolerante a "
        "cercas de código e a topo {}/[]). Remove duplicação entre agentes.",
        "column": "done",
        "sprint": "Sprint 0 · Fundação",
        "labels": ["backend"],
    },
    {
        "title": "Agente roteirista cena-a-cena",
        "description": "ScriptWriterAgent: trending_topic → list[Scene]/VideoJob "
        "pronto para o VideoPipeline.",
        "column": "done",
        "sprint": "Sprint 0 · Fundação",
        "labels": ["backend"],
    },
    {
        "title": "Testes de parsing (JSON + cenas)",
        "description": "14 testes offline de extract_json e build_scenes.",
        "column": "done",
        "sprint": "Sprint 0 · Fundação",
        "labels": ["testes"],
    },
    # ------------------------------- Sprint 1 (esteira de aprovação) ---------
    {
        "title": "Modelo de ideia + fila de revisão",
        "description": "Idea (com estados) e ReviewQueue persistida em JSON.",
        "column": "done",
        "sprint": "Sprint 1 · Esteira de aprovação",
        "labels": ["backend"],
    },
    {
        "title": "Gerador de ideias a partir de prompt",
        "description": "IdeaGenerator: brainstorm de conceitos + roteiro por "
        "conceito → lista de Idea.",
        "column": "done",
        "sprint": "Sprint 1 · Esteira de aprovação",
        "labels": ["backend"],
    },
    {
        "title": "Engine: modos manual e auto",
        "description": "generate_and_enqueue + post_approved. Manual = fila Tinder; "
        "auto = prompta-e-posta (publisher via API oficial, ainda desconectado).",
        "column": "done",
        "sprint": "Sprint 1 · Esteira de aprovação",
        "labels": ["backend"],
    },
    {
        "title": "API HTTP (FastAPI)",
        "description": "Endpoints de gerar/listar/aprovar/rejeitar/postar e do board.",
        "column": "done",
        "sprint": "Sprint 1 · Esteira de aprovação",
        "labels": ["backend"],
    },
    {
        "title": "Interface Next.js — aba Ideias (Tinder)",
        "description": "Prompt + modo (manual/auto), cartões de aprovação (❌/✅), "
        "lista de aprovadas prontas para postar.",
        "column": "done",
        "sprint": "Sprint 1 · Esteira de aprovação",
        "labels": ["frontend"],
    },
    {
        "title": "Interface Next.js — aba Kanban",
        "description": "Quadro de sprints com arrastar-e-soltar entre colunas.",
        "column": "done",
        "sprint": "Sprint 1 · Esteira de aprovação",
        "labels": ["frontend"],
    },
    {
        "title": "Testes da fila de revisão e do gerador",
        "description": "ReviewQueue, engine, BoardStore e build_idea_concepts — "
        "47 testes no total.",
        "column": "done",
        "sprint": "Sprint 1 · Esteira de aprovação",
        "labels": ["testes"],
    },
    # --------------------------------- Sprint 2 (geração de mídia) -----------
    {
        "title": "Gerador de imagem plugável",
        "description": "Fábrica agents/media: placeholder (FFmpeg) por padrão + "
        "stub Stability (STABILITY_API_KEY). Selecionável por config/env.",
        "column": "done",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["backend", "conteúdo"],
    },
    {
        "title": "Gerador de voz/TTS plugável",
        "description": "Fábrica agents/media: placeholder (áudio) por padrão + "
        "stub ElevenLabs (ELEVENLABS_API_KEY).",
        "column": "done",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["backend", "conteúdo"],
    },
    {
        "title": "Provedor Gemini (imagem e vídeo)",
        "description": "image_provider=gemini (Imagen) e video_provider=gemini (Veo, "
        "clipe por cena com muxagem de narração/legenda). GEMINI_API_KEY no .env.",
        "column": "done",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["backend", "conteúdo", "integração"],
    },
    {
        "title": "Legendas / burn-in no vídeo",
        "description": "drawtext do FFmpeg queima a narração por cena (config "
        "burn_subtitles); escape de fonte cross-platform (Windows/Linux).",
        "column": "done",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["backend", "conteúdo"],
    },
    {
        "title": "Teste de integração do VideoPipeline",
        "description": "tests/test_video_pipeline.py cobre render/concat/legendas "
        "mockando FFmpeg e os geradores.",
        "column": "done",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["testes"],
    },
    {
        "title": "Ligar geração de vídeo à esteira de ideias",
        "description": "render.py + POST /api/ideas/{id}/render anexa video_path; "
        "frontend tem botão Renderizar e player de preview.",
        "column": "done",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["backend", "frontend"],
    },
    # ------------------------- Sprint 3 (publicação via APIs) ----------------
    {
        "title": "Publisher via API oficial (1 plataforma)",
        "description": "YouTube Data API v3 implementado (upload real via "
        "google-api-python-client). Em revisão até validar com o token OAuth no .env.",
        "column": "review",
        "sprint": "Sprint 3 · Publicação",
        "labels": ["backend", "integração"],
    },
    {
        "title": "OAuth / credenciais das plataformas",
        "description": "Fluxo de autenticação e armazenamento seguro de tokens.",
        "column": "backlog",
        "sprint": "Sprint 3 · Publicação",
        "labels": ["backend", "integração"],
    },
    {
        "title": "Agendamento de postagens",
        "description": "Scheduler local (APScheduler) publica ideias aprovadas por "
        "intervalo; aba Agendamento no frontend + endpoints. Modo simulado sem token.",
        "column": "done",
        "sprint": "Sprint 3 · Publicação",
        "labels": ["backend", "frontend"],
    },
    # ---------------------- Sprint 4 (deploy e publicação do projeto) --------
    {
        "title": "Dockerfile do backend + build do frontend",
        "description": "API (uvicorn) + build standalone do Next.js + docker-compose "
        "com o Ollama containerizado.",
        "column": "done",
        "sprint": "Sprint 4 · Deploy & Publicação",
        "labels": ["infra"],
    },
    {
        "title": "CI no GitHub Actions",
        "description": "Roda pytest e next build a cada push/PR (.github/workflows/ci.yml).",
        "column": "done",
        "sprint": "Sprint 4 · Deploy & Publicação",
        "labels": ["infra", "testes"],
    },
    {
        "title": "Deploy do backend e do frontend",
        "description": "Hospedagem 100% local via docker compose (restart: "
        "unless-stopped) — ollama + api + web + Ollama, tudo na máquina do usuário.",
        "column": "done",
        "sprint": "Sprint 4 · Deploy & Publicação",
        "labels": ["infra"],
    },
    {
        "title": "Documentação final e publicação do projeto",
        "description": "README completo, licença, instruções de execução e "
        "abertura/merge na main.",
        "column": "backlog",
        "sprint": "Sprint 4 · Deploy & Publicação",
        "labels": ["docs"],
    },
    # ---------------------- Sprint 5 (bot do Telegram) ----------------------
    {
        "title": "Bot do Telegram — operar a arquitetura completa",
        "description": "telegram_bot.py: /gerar e /auto <prompt>, /pendentes, "
        "/aprovadas — reusa a API. Serviço opt-in no compose (profile bot). "
        "No ar e validado (@bot conectado à API).",
        "column": "done",
        "sprint": "Sprint 5 · Bot do Telegram",
        "labels": ["backend", "integração"],
    },
    {
        "title": "Bot do Telegram — aprovação por botões inline",
        "description": "Cada ideia vira mensagem com botões ✅/❌ (approve/reject) e "
        "🎬/🚀 (render/post) via callbacks para a API.",
        "column": "done",
        "sprint": "Sprint 5 · Bot do Telegram",
        "labels": ["backend", "integração"],
    },
    # --------------------------- Sprint 6 (automações) ----------------------
    {
        "title": "Agente crítico (quality gate)",
        "description": "agents/critic.py dá nota 0-10 à ideia; abaixo do limiar "
        "(critic_min_score) é auto-rejeitada antes da revisão. Liga por critic_enabled.",
        "column": "done",
        "sprint": "Sprint 6 · Automações",
        "labels": ["backend", "conteúdo"],
    },
    {
        "title": "Geração automática de ideias (agendada)",
        "description": "Scheduler gera ideias sozinho por intervalo a partir de um "
        "prompt fixo (autogen_*), mantendo a esteira cheia. Aba Agendamento.",
        "column": "done",
        "sprint": "Sprint 6 · Automações",
        "labels": ["backend", "frontend"],
    },
    {
        "title": "Notificações no Telegram",
        "description": "Bot avisa proativamente quando surgem ideias pendentes "
        "(JobQueue + TELEGRAM_NOTIFY_CHAT_ID).",
        "column": "done",
        "sprint": "Sprint 6 · Automações",
        "labels": ["backend", "integração"],
    },
    {
        "title": "Publisher Instagram Reels",
        "description": "publishers/instagram.py (Graph API) — scaffold; falta URL "
        "pública do vídeo + chamada final. IG_USER_ID/IG_ACCESS_TOKEN.",
        "column": "review",
        "sprint": "Sprint 6 · Automações",
        "labels": ["backend", "integração"],
    },
    {
        "title": "Publisher TikTok",
        "description": "publishers/tiktok.py (Content Posting API) — scaffold; falta "
        "completar o fluxo de upload. TIKTOK_ACCESS_TOKEN.",
        "column": "review",
        "sprint": "Sprint 6 · Automações",
        "labels": ["backend", "integração"],
    },
    {
        "title": "Agente analista (feedback loop)",
        "description": "Puxa métricas dos posts (views/engajamento) e realimenta a "
        "estratégia de nicho, favorecendo formatos que performam.",
        "column": "backlog",
        "sprint": "Sprint 6 · Automações",
        "labels": ["backend", "integração"],
    },
    {
        "title": "Thumbnails + A/B de títulos",
        "description": "Gerar capa (provedor de imagem) e 2-3 títulos alternativos; "
        "escolher via agente analista/crítico.",
        "column": "backlog",
        "sprint": "Sprint 6 · Automações",
        "labels": ["backend", "conteúdo"],
    },
    {
        "title": "Legendas multi-idioma",
        "description": "Traduzir a narração (LLM) e renderizar variantes localizadas "
        "(PT/EN/ES) para canais diferentes.",
        "column": "backlog",
        "sprint": "Sprint 6 · Automações",
        "labels": ["backend", "conteúdo"],
    },
    {
        "title": "Trilha sonora royalty-free",
        "description": "Adicionar música de fundo por cena/vídeo (mix com a narração).",
        "column": "backlog",
        "sprint": "Sprint 6 · Automações",
        "labels": ["backend", "conteúdo"],
    },
    # --------------------- Sprint 7 (robustez & produção) -------------------
    {
        "title": "Autenticação da API/web",
        "description": "Token/login para proteger a API e o painel caso saiam do "
        "localhost.",
        "column": "backlog",
        "sprint": "Sprint 7 · Robustez",
        "labels": ["backend", "infra"],
    },
    {
        "title": "Geração assíncrona (jobs + status)",
        "description": "Tornar /api/generate um job em background com polling de "
        "status, evitando timeouts em lotes grandes.",
        "column": "backlog",
        "sprint": "Sprint 7 · Robustez",
        "labels": ["backend"],
    },
    {
        "title": "Testes de integração HTTP",
        "description": "Cobrir os endpoints do server.py ponta a ponta (TestClient).",
        "column": "backlog",
        "sprint": "Sprint 7 · Robustez",
        "labels": ["testes"],
    },
    {
        "title": "Persistência em SQLite",
        "description": "Migrar fila/board dos JSON para SQLite, evitando corridas sob "
        "concorrência.",
        "column": "backlog",
        "sprint": "Sprint 7 · Robustez",
        "labels": ["backend"],
    },
    {
        "title": "Retry/backoff nas APIs externas",
        "description": "Reexecução com backoff em Ollama/Gemini/publishers e "
        "tratamento de falha de render.",
        "column": "backlog",
        "sprint": "Sprint 7 · Robustez",
        "labels": ["backend"],
    },
]
