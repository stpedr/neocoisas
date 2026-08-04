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
]
