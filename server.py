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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from board.store import BoardStore
from engine import generate_and_enqueue, post_approved
from review.models import IdeaStatus
from review.queue import ReviewQueue

CONFIG_PATH = os.environ.get("ANE_CONFIG", "config.json")
QUEUE_PATH = os.environ.get("ANE_QUEUE", "output/review_queue.json")
BOARD_PATH = os.environ.get("ANE_BOARD", "output/board.json")

app = FastAPI(title="Auto Niche Engine API", version="1.0")

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


# -------------------------------------------------------------------- rotas ---
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


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


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    # Import tardio: só precisa do Ollama quando de fato vai gerar.
    from agents.idea_generator import IdeaGenerator, OllamaError

    queue = get_queue()
    try:
        generator = IdeaGenerator(CONFIG_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        ideas = generate_and_enqueue(
            req.prompt,
            queue,
            generator,
            count=req.count,
            num_scenes=req.num_scenes,
            mode=req.mode,
        )
    except OllamaError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    posted = 0
    if req.mode == "auto":
        # Sem publisher conectado (APIs oficiais): as ideias ficam aprovadas.
        posted = len(post_approved(queue, publisher=None))

    return {
        "mode": req.mode,
        "generated": len(ideas),
        "posted": posted,
        "ideas": [i.to_dict() for i in ideas],
    }


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
