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
        "column": "in_progress",
        "sprint": "Sprint 1 · Esteira de aprovação",
        "labels": ["frontend"],
    },
    {
        "title": "Interface Next.js — aba Kanban",
        "description": "Quadro de sprints com arrastar-e-soltar entre colunas.",
        "column": "in_progress",
        "sprint": "Sprint 1 · Esteira de aprovação",
        "labels": ["frontend"],
    },
    {
        "title": "Testes da fila de revisão e do gerador",
        "description": "Cobrir ReviewQueue (aprovar/rejeitar/postar/persistência) e "
        "build_idea_concepts.",
        "column": "todo",
        "sprint": "Sprint 1 · Esteira de aprovação",
        "labels": ["testes"],
    },
    # --------------------------------- Sprint 2 (geração de mídia) -----------
    {
        "title": "Gerador de imagem plugável",
        "description": "Conectar Stable Diffusion local ou API no hook "
        "image_generator do VideoPipeline.",
        "column": "todo",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["backend", "conteúdo"],
    },
    {
        "title": "Gerador de voz/TTS plugável",
        "description": "Conectar TTS (local ou API) no hook voice_generator.",
        "column": "todo",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["backend", "conteúdo"],
    },
    {
        "title": "Legendas / burn-in no vídeo",
        "description": "drawtext do FFmpeg para queimar as legendas por cena.",
        "column": "backlog",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["backend", "conteúdo"],
    },
    {
        "title": "Teste de integração do VideoPipeline",
        "description": "Cobrir render/concat mockando FFmpeg e os geradores.",
        "column": "backlog",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["testes"],
    },
    {
        "title": "Ligar geração de vídeo à esteira de ideias",
        "description": "Renderizar a Idea aprovada e anexar video_path para preview "
        "no frontend.",
        "column": "backlog",
        "sprint": "Sprint 2 · Geração de mídia",
        "labels": ["backend", "frontend"],
    },
    # ------------------------- Sprint 3 (publicação via APIs) ----------------
    {
        "title": "Publisher via API oficial (1 plataforma)",
        "description": "Começar por uma rede (ex: YouTube Data API) implementando o "
        "gancho Publisher — dentro das regras da plataforma.",
        "column": "backlog",
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
        "description": "Agendar publicação das ideias aprovadas.",
        "column": "backlog",
        "sprint": "Sprint 3 · Publicação",
        "labels": ["backend"],
    },
    # ---------------------- Sprint 4 (deploy e publicação do projeto) --------
    {
        "title": "Dockerfile do backend + build do frontend",
        "description": "Empacotar API (uvicorn) e gerar build de produção do Next.js.",
        "column": "backlog",
        "sprint": "Sprint 4 · Deploy & Publicação",
        "labels": ["infra"],
    },
    {
        "title": "CI no GitHub Actions",
        "description": "Rodar pytest e next build a cada push/PR.",
        "column": "backlog",
        "sprint": "Sprint 4 · Deploy & Publicação",
        "labels": ["infra", "testes"],
    },
    {
        "title": "Deploy do backend e do frontend",
        "description": "Publicar a API e a interface (ex: container + host de sua "
        "escolha). Observação: o Ollama roda na máquina do usuário.",
        "column": "backlog",
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
]
