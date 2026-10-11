"""Sugestões de mídia por superfície.

Critérios, todos explicáveis (cada sugestão vem com os motivos):

- **Proporção:** a mídia com o formato da superfície aparece sem cortar nem
  esticar. É o critério que mais pesa (diferença em log da razão w/h).
- **Resolução:** a mídia precisa ter pixels suficientes para o tamanho que a
  superfície ocupa no projetor. Abaixo disso, perde pontos.
- **Tipo:** vídeo ganha um pouco em superfícies grandes (movimento chama
  atenção); imagem ganha um pouco nas pequenas.
- **Variedade** (no "sugerir para todas"): a mesma mídia não se repete enquanto
  houver outra razoável.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .mapping.warp import quad_aspect


@dataclass
class MediaRef:
    ref: str  # "lib:<id>" (biblioteca) ou "sha:<sha256>" (já no projeto)
    name: str
    kind: str
    width: int
    height: int
    folder: str = ""

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.width and self.height else 0.0


@dataclass
class Suggestion:
    ref: str
    name: str
    kind: str
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ref": self.ref, "name": self.name, "kind": self.kind,
                "score": round(self.score, 3), "reasons": self.reasons}


def surface_size_px(quad) -> tuple[float, float]:
    q = np.asarray(quad, float)
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    return float(w), float(h)


def score(media: MediaRef, quad, out_area: float) -> Suggestion:
    reasons: list[str] = []
    a_s = quad_aspect(quad)
    s = 0.0
    if media.aspect > 0:
        diff = abs(math.log(media.aspect / a_s))
        s += 0.6 * math.exp(-diff * 2.5)
        if diff < 0.15:
            reasons.append("formato igual ao da superfície")
        elif diff < 0.45:
            reasons.append("formato parecido")
        else:
            reasons.append("formato diferente (vai cortar ou esticar)")
        w, h = surface_size_px(quad)
        need = max(w, h)
        have = max(media.width, media.height)
        res = min(1.0, have / need) if need > 0 else 1.0
        s += 0.25 * res
        if res < 0.6:
            reasons.append("resolução baixa para o tamanho")
    else:
        s += 0.2
        reasons.append("tamanho desconhecido")
    big = (surface_size_px(quad)[0] * surface_size_px(quad)[1]) / out_area if out_area else 0
    if media.kind == "video":
        s += 0.15 if big > 0.08 else 0.07
        if big > 0.08:
            reasons.append("vídeo numa superfície grande")
    elif media.kind == "gif":
        s += 0.1
    else:
        s += 0.12 if big <= 0.08 else 0.05
    return Suggestion(media.ref, media.name, media.kind, s, reasons)


def suggest_for_surface(quad, medias: list[MediaRef], out_area: float, top: int = 6) -> list[Suggestion]:
    ranked = sorted((score(m, quad, out_area) for m in medias), key=lambda x: -x.score)
    return ranked[:top]


def suggest_all(surfaces: list[tuple[str, list]], medias: list[MediaRef], out_area: float,
                top: int = 6) -> dict[str, dict]:
    """Por superfície: ranking + a escolha sugerida (sem repetir mídias se possível).

    Escolha gulosa: as superfícies maiores escolhem primeiro (são as que mais
    aparecem); cada uma pega a melhor mídia ainda não usada, desde que a nota
    não caia mais de 40% em relação à melhor absoluta. Só repete se não houver
    alternativa razoável.
    """
    out: dict[str, dict] = {}
    ranks = {sid: suggest_for_surface(q, medias, out_area, top=max(top, 12)) for sid, q in surfaces}
    order = sorted(surfaces, key=lambda sq: -np.prod(surface_size_px(sq[1])))
    used: set[str] = set()
    for sid, _ in order:
        rk = ranks[sid]
        pick: Optional[Suggestion] = None
        if rk:
            best = rk[0].score
            pick = next((x for x in rk if x.ref not in used and x.score >= 0.6 * best), rk[0])
            used.add(pick.ref)
        out[sid] = {"pick": pick.to_dict() if pick else None, "ranking": [x.to_dict() for x in rk[:top]]}
    return out
