"""API HTTP do Auto Niche Engine (FastAPI).

Expõe a esteira de ideias para o frontend Next.js: gerar ideias a partir de um
prompt, listar/contar, aprovar/rejeitar (modo "Tinder") e marcar como postadas.
A geração usa o Ollama local, então este servidor deve rodar na máquina do
usuário (mesmo host do Ollama).

Executar:
    pip install -r requirements.txt
    uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from board.store import BoardStore
from engine import generate_and_enqueue, post_approved
from review.models import IdeaStatus
from review.queue import ReviewQueue
from scheduler import ScheduleStore, manager, run_tick

CONFIG_PATH = os.environ.get("ANE_CONFIG", "config.json")
QUEUE_PATH = os.environ.get("ANE_QUEUE", "output/review_queue.json")
BOARD_PATH = os.environ.get("ANE_BOARD", "output/board.json")

# Autenticação opcional: se ANE_API_KEY estiver definido, exige o cabeçalho
# X-API-Key em todas as rotas (exceto health/docs). Vazio = aberto (local).
_PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


def require_key(request: Request) -> None:
    api_key = os.environ.get("ANE_API_KEY")
    if not api_key:
        return
    if request.url.path in _PUBLIC_PATHS:
        return
    if request.headers.get("x-api-key") != api_key:
        raise HTTPException(401, "Chave de API inválida ou ausente (X-API-Key).")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reaplica a seleção de modelos salva (troca via UI) no ambiente do processo.
    try:
        import settings as _settings

        _settings.apply_saved()
    except Exception:  # noqa: BLE001 - não impede o start
        pass
    # Sobe o agendador de postagens (job periódico conforme output/schedule.json).
    manager.start()
    yield
    manager.shutdown()


app = FastAPI(
    title="Auto Niche Engine API",
    version="1.0",
    lifespan=lifespan,
    dependencies=[Depends(require_key)],
)

# Libera o frontend Next.js em desenvolvimento.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "ANE_CORS_ORIGINS", "http://localhost:3000"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_queue() -> ReviewQueue:
    """Recarrega a fila do disco a cada request (estado compartilhado simples)."""
    return ReviewQueue(QUEUE_PATH)


def get_board() -> BoardStore:
    """Recarrega o quadro do disco a cada request (semeia se estiver vazio)."""
    return BoardStore(BOARD_PATH)


# ------------------------------------------------------------------ schemas ---
class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    mode: str = Field("manual", pattern="^(manual|auto)$")
    count: int = Field(5, ge=1, le=12)
    num_scenes: int = Field(5, ge=1, le=12)


class CardCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    column: str = "backlog"
    sprint: str = ""
    labels: list[str] = Field(default_factory=list)


class CardUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    column: str | None = None
    sprint: str | None = None
    labels: list[str] | None = None
    order: float | None = None


class ScheduleUpdate(BaseModel):
    enabled: bool | None = None
    every_minutes: int | None = Field(None, ge=1, le=1440)
    max_per_run: int | None = Field(None, ge=1, le=20)
    render_before: bool | None = None
    simulate: bool | None = None
    # Geração automática de ideias
    autogen_enabled: bool | None = None
    autogen_prompt: str | None = None
    autogen_every_minutes: int | None = Field(None, ge=1, le=1440)
    autogen_count: int | None = Field(None, ge=1, le=12)
    autogen_mode: str | None = Field(None, pattern="^(manual|auto)$")


# -------------------------------------------------------------------- rotas ---
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/models")
def models() -> dict:
    """Registry unificado: capacidades, providers, modelos e seleção atual."""
    from registry import describe

    return describe(_app_config())


@app.get("/api/models/available")
def models_available() -> dict:
    """Modelos disponíveis ao vivo (Ollama /api/tags) + conhecidos dos provedores."""
    from registry import available_models

    return available_models(_app_config())


class ModelSelect(BaseModel):
    capability: str
    provider: str
    model: str | None = None


@app.put("/api/models/select")
def select_model(sel: ModelSelect) -> dict:
    """Troca provider/modelo de uma capacidade (persiste e aplica em runtime)."""
    import settings as _settings
    from registry import describe, validate

    if not validate(sel.capability, sel.provider):
        raise HTTPException(400, f"Seleção inválida: {sel.capability}/{sel.provider}.")
    _settings.set_selection(sel.capability, sel.provider, sel.model)
    return describe(_app_config())


@app.get("/api/ideas")
def list_ideas(status: str | None = None) -> dict:
    queue = get_queue()
    if status is not None:
        if status not in IdeaStatus.ALL:
            raise HTTPException(400, f"Status inválido: '{status}'.")
        ideas = queue.by_status(status)
    else:
        ideas = queue.all()
    return {"ideas": [i.to_dict() for i in ideas], "counts": queue.counts()}


@app.get("/api/counts")
def counts() -> dict:
    return get_queue().counts()


def _run_generation(req: GenerateRequest) -> dict:
    """Lógica de geração compartilhada pelos endpoints síncrono e assíncrono."""
    from agents.idea_generator import IdeaGenerator

    queue = get_queue()
    generator = IdeaGenerator(CONFIG_PATH)

    # Agente crítico (quality gate) opcional, ligado por config.
    scorer = None
    min_score = 0.0
    cfg = generator.config
    if cfg.get("critic_enabled"):
        from agents.critic import ScriptCriticAgent

        critic = ScriptCriticAgent(CONFIG_PATH)
        scorer = lambda idea: critic.score_idea(idea.title, idea.scenes)  # noqa: E731
        min_score = float(cfg.get("critic_min_score", 6.0))

    # Agente revisor/editor (loop de melhoria) opcional — substitui o gate simples.
    editor = None
    if cfg.get("editor_enabled"):
        from agents.editor import ScriptEditorAgent

        editor = ScriptEditorAgent(CONFIG_PATH)
        min_score = float(cfg.get("critic_min_score", 6.0))

    ideas = generate_and_enqueue(
        req.prompt, queue, generator,
        count=req.count, num_scenes=req.num_scenes, mode=req.mode,
        scorer=scorer, min_score=min_score,
        editor=editor, editor_max_iterations=int(cfg.get("editor_max_iterations", 2)),
    )
    posted = 0
    if req.mode == "auto":
        posted = len(post_approved(queue, publisher=None))
    return {
        "mode": req.mode,
        "generated": len(ideas),
        "posted": posted,
        "ideas": [i.to_dict() for i in ideas],
    }


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    from agents.idea_generator import OllamaError

    try:
        return _run_generation(req)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except OllamaError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/generate/async")
def generate_async(req: GenerateRequest) -> dict:
    """Gera em background e devolve um job_id (acompanhe em /api/jobs/{id})."""
    from jobs import jobs

    job_id = jobs.submit(lambda: _run_generation(req))
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    from jobs import jobs

    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' não encontrado.")
    return job


@app.post("/api/ideas/{idea_id}/approve")
def approve(idea_id: str) -> dict:
    try:
        return get_queue().approve(idea_id).to_dict()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/ideas/{idea_id}/reject")
def reject(idea_id: str) -> dict:
    try:
        return get_queue().reject(idea_id).to_dict()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/ideas/{idea_id}/post")
def mark_posted(idea_id: str) -> dict:
    queue = get_queue()
    try:
        return queue.mark_posted(idea_id).to_dict()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def _app_config() -> dict:
    import json

    path = CONFIG_PATH
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@app.post("/api/ideas/{idea_id}/render")
def render(idea_id: str, lang: str | None = None) -> dict:
    from render import render_idea

    queue = get_queue()
    try:
        idea = queue.get(idea_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    try:
        path = render_idea(idea, _app_config(), lang=lang)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        raise HTTPException(500, str(exc)) from exc
    if lang:
        return queue.add_variant(idea_id, lang, str(path)).to_dict()
    return queue.attach_video(idea_id, str(path)).to_dict()


@app.get("/api/ideas/{idea_id}/video")
def get_video(idea_id: str, lang: str | None = None):
    queue = get_queue()
    try:
        idea = queue.get(idea_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    path = idea.video_variants.get(lang) if lang else idea.video_path
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Vídeo ainda não renderizado para esta ideia/idioma.")
    return FileResponse(path, media_type="video/mp4")


@app.post("/api/ideas/{idea_id}/refine")
def refine_idea(idea_id: str) -> dict:
    from agents.editor import OllamaError as _OE
    from agents.editor import ScriptEditorAgent

    queue = get_queue()
    try:
        idea = queue.get(idea_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cfg = _app_config()
    try:
        result = ScriptEditorAgent(CONFIG_PATH).refine(
            idea.title, idea.scenes,
            min_score=float(cfg.get("critic_min_score", 6.0)),
            max_iterations=int(cfg.get("editor_max_iterations", 2)),
        )
    except _OE as exc:
        raise HTTPException(502, str(exc)) from exc
    idea.scenes = result["scenes"]
    idea.score = result["score"]
    idea.note = f"Editado: nota {result['score']} em {result['iterations']} iteração(ões)."
    queue._save()
    return idea.to_dict()


@app.post("/api/ideas/{idea_id}/titles")
def suggest_titles(idea_id: str, n: int = 3) -> dict:
    from agents.titler import OllamaError as _OE
    from agents.titler import TitlerAgent

    queue = get_queue()
    try:
        idea = queue.get(idea_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    try:
        titulos = TitlerAgent(CONFIG_PATH).suggest_titles(idea.title, n=n)
    except _OE as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"titles": titulos}


@app.post("/api/ideas/{idea_id}/thumbnail")
def make_thumbnail(idea_id: str) -> dict:
    from render import render_thumbnail

    queue = get_queue()
    try:
        idea = queue.get(idea_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    try:
        path = render_thumbnail(idea, _app_config())
    except (RuntimeError, OSError) as exc:
        raise HTTPException(500, str(exc)) from exc
    return queue.attach_thumbnail(idea_id, str(path)).to_dict()


@app.get("/api/ideas/{idea_id}/thumbnail")
def get_thumbnail(idea_id: str):
    queue = get_queue()
    try:
        idea = queue.get(idea_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not idea.thumbnail_path or not os.path.exists(idea.thumbnail_path):
        raise HTTPException(404, "Thumbnail ainda não gerada.")
    return FileResponse(idea.thumbnail_path, media_type="image/png")


@app.post("/api/ideas/{idea_id}/metrics")
def set_metrics(idea_id: str, metrics: dict) -> dict:
    queue = get_queue()
    try:
        return queue.set_metrics(idea_id, metrics).to_dict()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/analyze")
def analyze() -> dict:
    from agents.analyst import AnalystAgent
    from agents.analyst import OllamaError as _OE

    queue = get_queue()
    performances = [
        {"title": i.title, "metrics": i.metrics}
        for i in queue.all()
        if i.metrics
    ]
    try:
        return AnalystAgent(CONFIG_PATH).analyze(performances)
    except _OE as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/api/ideas/decided")
def clear_decided() -> dict:
    removed = get_queue().clear_decided()
    return {"removed": removed}


# ------------------------------------------------------------- Kanban board ---
@app.get("/api/board")
def get_board_state() -> dict:
    return get_board().as_payload()


@app.post("/api/board/cards")
def create_card(card: CardCreate) -> dict:
    board = get_board()
    try:
        created = board.add(
            title=card.title,
            description=card.description,
            column=card.column,
            sprint=card.sprint,
            labels=card.labels,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return created.to_dict()


@app.patch("/api/board/cards/{card_id}")
def update_card(card_id: str, patch: CardUpdate) -> dict:
    board = get_board()
    try:
        updated = board.update(card_id, **patch.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return updated.to_dict()


@app.delete("/api/board/cards/{card_id}")
def delete_card(card_id: str) -> dict:
    board = get_board()
    try:
        board.delete(card_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": card_id}


@app.post("/api/board/reset")
def reset_board() -> dict:
    board = get_board()
    board.seed(force=True)
    return board.as_payload()


# --------------------------------------------------------- Agendamento -------
def _schedule_payload() -> dict:
    data = ScheduleStore().get()
    data["running"] = manager._sched is not None
    data["next_run"] = manager.next_run()
    data["next_autogen"] = manager.next_autogen()
    return data


@app.get("/api/schedule")
def get_schedule() -> dict:
    return _schedule_payload()


@app.put("/api/schedule")
def update_schedule(patch: ScheduleUpdate) -> dict:
    ScheduleStore().update(**patch.model_dump(exclude_none=True))
    manager.reconfigure()
    return _schedule_payload()


@app.post("/api/schedule/run-now")
def run_schedule_now() -> dict:
    return run_tick()


@app.post("/api/schedule/autogen-now")
def run_autogen_now() -> dict:
    from scheduler import run_autogen_tick

    return run_autogen_tick()
