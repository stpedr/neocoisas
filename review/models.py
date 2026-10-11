"""Modelo de dados de uma ideia de vídeo e seus estados de aprovação.

Uma `Idea` é um candidato gerado a partir de um prompt: tem um título/gancho,
um roteiro (lista de `Scene`) e, quando renderizado, o caminho do vídeo. Ela
percorre estados de aprovação — do modo "Tinder" (aprovar/rejeitar) até a
postagem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from agents.slides import Slide
from agents.video_pipeline import Scene


class IdeaStatus:
    """Estados possíveis de uma ideia na esteira de revisão."""

    PENDING = "pending"      # aguardando decisão (fila do "Tinder")
    APPROVED = "approved"    # aprovada — pronta para postar
    REJECTED = "rejected"    # descartada
    POSTED = "posted"        # já publicada

    ALL = frozenset({PENDING, APPROVED, REJECTED, POSTED})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Idea:
    """Um candidato a vídeo, com roteiro e estado de aprovação."""

    prompt: str
    title: str
    scenes: list[Scene] = field(default_factory=list)
    slides: list[Slide] = field(default_factory=list)   # carrossel (formato padrão)
    post_format: str = "reels"     # reels | carousel | feed | story
    caption: str = ""              # legenda pronta do post
    hashtags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    status: str = IdeaStatus.PENDING
    mode: str = "manual"           # "manual" (revisão) ou "auto" (prompta-e-posta)
    video_path: str | None = None
    thumbnail_path: str | None = None
    video_variants: dict = field(default_factory=dict)  # {idioma: caminho_mp4}
    metrics: dict = field(default_factory=dict)          # {views, likes, ...}
    score: float | None = None     # nota do agente crítico (0-10), se avaliado
    note: str = ""
    created_at: str = field(default_factory=_now_iso)
    decided_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "title": self.title,
            "scenes": [
                {
                    "narration": s.narration,
                    "visual_prompt": s.visual_prompt,
                    "duration_s": s.duration_s,
                }
                for s in self.scenes
            ],
            "slides": [s.to_dict() for s in self.slides],
            "post_format": self.post_format,
            "caption": self.caption,
            "hashtags": list(self.hashtags),
            "status": self.status,
            "mode": self.mode,
            "video_path": self.video_path,
            "thumbnail_path": self.thumbnail_path,
            "video_variants": dict(self.video_variants),
            "metrics": dict(self.metrics),
            "score": self.score,
            "note": self.note,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Idea":
        scenes = [
            Scene(
                narration=s.get("narration", ""),
                visual_prompt=s.get("visual_prompt", ""),
                duration_s=float(s.get("duration_s", 4.0)),
            )
            for s in data.get("scenes", [])
        ]
        return cls(
            prompt=data.get("prompt", ""),
            title=data.get("title", ""),
            scenes=scenes,
            slides=[Slide.from_dict(s) for s in data.get("slides", [])],
            post_format=data.get("post_format", "reels"),
            caption=data.get("caption", ""),
            hashtags=list(data.get("hashtags", [])),
            id=data.get("id", uuid4().hex[:12]),
            status=data.get("status", IdeaStatus.PENDING),
            mode=data.get("mode", "manual"),
            video_path=data.get("video_path"),
            thumbnail_path=data.get("thumbnail_path"),
            video_variants=dict(data.get("video_variants", {})),
            metrics=dict(data.get("metrics", {})),
            score=data.get("score"),
            note=data.get("note", ""),
            created_at=data.get("created_at", _now_iso()),
            decided_at=data.get("decided_at"),
        )

    @property
    def total_duration_s(self) -> float:
        return round(sum(s.duration_s for s in self.scenes), 1)
