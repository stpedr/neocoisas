"""Simulação: aplica os comportamentos da cena às entidades, passo a passo.

Determinística (RNG com semente da cena, ``dt`` explícito): os testes
reproduzem exatamente a mesma partida. O laço em tempo real fica em
``runtime.py``; aqui não há relógio nem threads.

Ordem por passo, para cada entidade:
1. comportamentos de movimento somam uma velocidade desejada
   (perseguir, fugir, vagar, ir até o olhar);
2. ``freeze_when_watched`` zera a velocidade se alguém a está olhando;
3. integra a posição, mantém dentro da parede;
4. perseguidor que encosta na pessoa dispara o evento ``caught``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from .scene import ChasePlayer, EntityGroup, FleePlayer, FreezeWhenWatched, SceneSpec, SeekGaze, Wander
from .world import Gaze, Player, WorldState, gaze_of


@dataclass
class Entity:
    id: int
    group: int
    x: float
    y: float
    heading: float = 0.0  # rad, direção do último movimento (para o sprite olhar)
    state: str = "idle"  # idle | move | frozen | shy
    vx: float = 0.0
    vy: float = 0.0
    wander_dir: float = 0.0


@dataclass
class Event:
    name: str
    entity_id: int
    t: float


@dataclass
class Snapshot:
    """Estado público de um instante (o que renderers e saídas recebem)."""

    tick: int
    t: float
    spec: SceneSpec
    entities: list[Entity]
    players: list[Player]
    gazes: list[Gaze]
    events: list[Event] = field(default_factory=list)
    flash: float = 0.0  # 0..1, decai após "caught"


class Simulation:
    def __init__(self, spec: SceneSpec):
        self.spec = spec
        self.world = WorldState(aspect=spec.aspect)
        self.rng = random.Random(spec.seed)
        self.t = 0.0
        self.tick = 0
        self.flash = 0.0
        self.entities: list[Entity] = []
        self._events: list[Event] = []
        self._spawn_all(players=[])

    # ------------------------------------------------------------------ spawn
    def _spawn_point(self, group: EntityGroup, players: list[Player]) -> tuple[float, float]:
        a = self.spec.aspect
        r = group.size / 2
        if group.spawn == "center":
            return a / 2 + self.rng.uniform(-0.1, 0.1), 0.5 + self.rng.uniform(-0.1, 0.1)
        if group.spawn == "edges":
            side = self.rng.choice(["left", "right", "top"])
            if side == "left":
                return r, self.rng.uniform(r, 1 - r)
            if side == "right":
                return a - r, self.rng.uniform(r, 1 - r)
            return self.rng.uniform(r, a - r), r
        if group.spawn == "far_from_player" and players:
            px = players[0].x
            x = r if px > a / 2 else a - r
            return x, self.rng.uniform(r, 1 - r)
        return self.rng.uniform(r, a - r), self.rng.uniform(r, 1 - r)

    def _spawn_all(self, players: list[Player]) -> None:
        self.entities = []
        for gi, group in enumerate(self.spec.groups):
            for _ in range(group.count):
                x, y = self._spawn_point(group, players)
                self.entities.append(
                    Entity(id=len(self.entities), group=gi, x=x, y=y, wander_dir=self.rng.uniform(0, 2 * math.pi))
                )

    def reset(self, players: Optional[list[Player]] = None) -> None:
        self._spawn_all(players or [])

    # ------------------------------------------------------------------- passo
    def step(self, dt: float, players: list[Player]) -> Snapshot:
        dt = max(0.0, min(dt, 0.1))  # um engasgo não teletransporta ninguém
        self.t += dt
        self.tick += 1
        self.world.players = players
        fov = math.radians(self.spec.fov_deg)
        gazes = [gaze_of(p, fov) for p in players]
        tracked = [p for p in players if p.tracked] or players  # sem ninguém: alvo "fantasma" = último conhecido
        caught: list[int] = []

        for e in self.entities:
            group = self.spec.groups[e.group]
            vx = vy = 0.0
            for b in group.behaviors:
                dx, dy = self._behavior_velocity(b, e, tracked, gazes, dt)
                vx += dx
                vy += dy
            watched = any(g.sees((e.x, e.y)) for g in gazes)
            frozen = False
            for b in group.behaviors:
                if isinstance(b, FreezeWhenWatched) and watched:
                    frozen = True
                    e.state = "shy" if b.shy else "frozen"
            if frozen:
                vx = vy = 0.0
            else:
                e.state = "move" if (vx or vy) else "idle"
                sx, sy = self._separation(e, group)
                vx, vy = vx + sx, vy + sy
            e.vx, e.vy = vx, vy
            if vx or vy:
                e.heading = math.atan2(vy, vx)
            r = group.size / 2
            e.x, e.y = self.world.clamp((e.x + vx * dt, e.y + vy * dt), margin=r * 0.5)

            really = [p for p in players if p.tracked]  # só "pega" quem o sensor está vendo
            if not frozen and really and any(isinstance(b, ChasePlayer) for b in group.behaviors):
                target = _nearest(e, really).anchor
                if math.dist((e.x, e.y), target) <= self.spec.catch_radius + r * 0.5:
                    caught.append(e.id)

        events = [Event("caught", eid, self.t) for eid in caught]
        if caught:
            if "flash" in self.spec.on_caught:
                self.flash = 1.0
            if "reset" in self.spec.on_caught:
                self.reset(tracked)
        self.flash = max(0.0, self.flash - dt / 0.6)
        return Snapshot(self.tick, self.t, self.spec, [_copy(e) for e in self.entities], list(players), gazes,
                        events, self.flash)

    def _separation(self, e: Entity, group: EntityGroup) -> tuple[float, float]:
        """Empurrão suave para longe de vizinhos do mesmo grupo que se sobrepõem.

        Sem isso, perseguidores convergem para o mesmo ponto e viram um borrão.
        O(n²) por grupo: só para grupos pequenos (≤ 40), onde se nota a sobreposição.
        """
        if group.count > 40:
            return 0.0, 0.0
        min_d = group.size * 0.9
        sx = sy = 0.0
        for o in self.entities:
            if o is e or o.group != e.group:
                continue
            dx, dy = e.x - o.x, e.y - o.y
            d = math.hypot(dx, dy)
            if d < min_d:
                if d < 1e-6:  # exatamente sobrepostos: separa numa direção determinística
                    dx, dy, d = math.cos(e.id), math.sin(e.id), 1.0
                push = (min_d - d) / min_d * 0.6
                sx += dx / d * push
                sy += dy / d * push
        return sx, sy

    def _behavior_velocity(self, b, e: Entity, players: list[Player], gazes: list[Gaze], dt: float):
        if isinstance(b, ChasePlayer) and players:
            return _toward((e.x, e.y), _nearest(e, players).anchor, b.speed)
        if isinstance(b, FleePlayer) and players:
            p = _nearest(e, players)
            d = math.dist((e.x, e.y), p.anchor)
            if d < b.radius:
                vx, vy = _toward(p.anchor, (e.x, e.y), b.speed * (1 - d / b.radius) + 1e-6)
                return vx, vy
            return 0.0, 0.0
        if isinstance(b, Wander):
            e.wander_dir += self.rng.uniform(-b.turn, b.turn) * dt
            # perto da borda, vira para dentro
            cx, cy = self.spec.aspect / 2, 0.5
            if not (0.1 < e.x < self.spec.aspect - 0.1 and 0.1 < e.y < 0.9):
                e.wander_dir = math.atan2(cy - e.y, cx - e.x) + self.rng.uniform(-0.5, 0.5)
            return math.cos(e.wander_dir) * b.speed, math.sin(e.wander_dir) * b.speed
        if isinstance(b, SeekGaze):
            active = [g for g in gazes if g.active]
            if active:
                g = min(active, key=lambda g: math.dist(g.center, (e.x, e.y)))
                return _toward((e.x, e.y), g.center, b.speed, slow_radius=g.radius * 0.6)
        return 0.0, 0.0


def _nearest(e: Entity, players: list[Player]) -> Player:
    return min(players, key=lambda p: math.dist((e.x, e.y), p.anchor))


def _toward(a, b, speed: float, slow_radius: float = 0.0):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return 0.0, 0.0
    s = speed * (min(1.0, d / slow_radius) if slow_radius > 0 else 1.0)
    return dx / d * s, dy / d * s


def _copy(e: Entity) -> Entity:
    return Entity(e.id, e.group, e.x, e.y, e.heading, e.state, e.vx, e.vy, e.wander_dir)
