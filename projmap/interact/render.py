"""Renderer nativo da cena interativa (sem TouchDesigner) — desenha em RGBA.

Vira a fonte ``interactive`` das superfícies do ProjMap: o resultado passa
pelo mesmo warp/máscara/blend de qualquer vídeo. Sprites procedurais em
OpenCV (rápidos, sem assets):

- ``ghost``: fantasma original (corpo arredondado, barra ondulada, olhos que
  seguem o movimento). Tímido = cobre os olhos com as mãos e fica translúcido.
- ``orb``: esfera brilhante · ``firefly``: ponto com halo que pisca ·
  ``fish``: corpo + cauda orientados pela direção.

Fundo preto = sem luz na projeção (só os elementos acendem a parede).
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from .sim import Entity, Snapshot

SS = 4  # subpixel do OpenCV (shift=2): contornos suaves em movimento lento


def render_snapshot(snap: Snapshot, size: tuple[int, int] = (1280, 720), debug: bool = False) -> np.ndarray:
    w, h = size
    spec = snap.spec
    img = np.empty((h, w, 4), dtype=np.uint8)
    img[:] = np.array([*spec.background, 255], dtype=np.uint8)  # broadcast contíguo (rápido)
    kx, ky = w / spec.aspect, h  # 1 unidade do mundo = altura da imagem
    for e in snap.entities:
        g = spec.groups[e.group]
        cx, cy = e.x * kx, e.y * ky
        r = max(2.0, g.size * ky / 2)
        # Desenha só numa janela em volta do sprite: as mesclas (halo, translúcido)
        # custam a área da janela, não a da tela inteira.
        ext = r * 2.6
        x0, y0 = max(0, int(cx - ext)), max(0, int(cy - ext))
        x1, y1 = min(w, int(cx + ext) + 1), min(h, int(cy + ext) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        _SPRITES[g.sprite](img[y0:y1, x0:x1], cx - x0, cy - y0, r, g.color, e, snap.t)
    if debug:
        _draw_debug(img, snap, w, h)
    if snap.flash > 0:
        a = snap.flash * 0.75
        img[..., :3] = (img[..., :3] * (1 - a) + np.array([255, 70, 70]) * a).astype(np.uint8)
    return img


def _p(x: float, y: float) -> tuple[int, int]:
    return int(round(x * SS)), int(round(y * SS))


def _blend(img: np.ndarray, layer: np.ndarray, alpha: float) -> None:
    if alpha >= 0.999:
        np.copyto(img, layer)
    else:
        cv2.addWeighted(layer, alpha, img, 1 - alpha, 0, dst=img)


def _ghost(img, cx, cy, r, color, e: Entity, t: float) -> None:
    bob = math.sin(t * 2.4 + e.id * 1.3) * r * 0.08
    cy = cy + bob
    shy = e.state == "shy"
    col = (*color, 255)
    layer = img.copy()
    # corpo: cabeça redonda + saia com barra ondulada
    body = [(cx + r * math.cos(a), cy - r * 0.15 + r * 0.95 * math.sin(a)) for a in np.linspace(math.pi, 2 * math.pi, 24)]
    skirt_y = cy + r * 0.85
    waves = 4
    for i in range(waves * 6 + 1):
        u = i / (waves * 6)
        x = cx + r - 2 * r * u
        y = skirt_y + math.sin(u * waves * 2 * math.pi + t * 5 + e.id) * r * 0.12
        body.append((x, y))
    pts = np.array([_p(x, y) for x, y in body], np.int32)
    cv2.fillPoly(layer, [pts], col, cv2.LINE_AA, shift=2)
    # olhos olham para onde vai (ou para frente)
    look = (math.cos(e.heading), math.sin(e.heading)) if e.state == "move" else (0.0, 0.0)
    for side in (-1, 1):
        ex, ey = cx + side * r * 0.36 + look[0] * r * 0.1, cy - r * 0.2 + look[1] * r * 0.08
        cv2.ellipse(layer, _p(ex, ey), _p(r * 0.13, r * 0.2), 0, 0, 360, (20, 24, 40, 255), -1, cv2.LINE_AA, shift=2)
    if shy:
        # mãos sobre os olhos + bochechas rosadas: "envergonhado"
        for side in (-1, 1):
            hx, hy = cx + side * r * 0.34, cy - r * 0.14
            cv2.ellipse(layer, _p(hx, hy), _p(r * 0.24, r * 0.16), side * 20, 0, 360, col, -1, cv2.LINE_AA, shift=2)
            cv2.ellipse(layer, _p(hx, hy), _p(r * 0.24, r * 0.16), side * 20, 0, 360, (190, 195, 215, 255), 1,
                        cv2.LINE_AA, shift=2)
            cv2.circle(layer, _p(cx + side * r * 0.5, cy + r * 0.15), int(r * 0.09 * SS), (255, 150, 170, 255), -1,
                       cv2.LINE_AA, shift=2)
    else:
        # boca: aberta quando persegue
        mouth_h = r * (0.16 if e.state == "move" else 0.06)
        cv2.ellipse(layer, _p(cx, cy + r * 0.22), _p(r * 0.16, mouth_h), 0, 0, 360, (20, 24, 40, 255), -1,
                    cv2.LINE_AA, shift=2)
    _blend(img, layer, 0.55 if shy else 0.95)


def _orb(img, cx, cy, r, color, e, t) -> None:
    for k, a in ((1.8, 0.12), (1.3, 0.25), (1.0, 0.9)):
        layer = img.copy()
        cv2.circle(layer, _p(cx, cy), int(r * k * SS), (*color, 255), -1, cv2.LINE_AA, shift=2)
        _blend(img, layer, a)


def _firefly(img, cx, cy, r, color, e, t) -> None:
    flicker = 0.55 + 0.45 * math.sin(t * 7 + e.id * 2.1) ** 2
    layer = img.copy()
    cv2.circle(layer, _p(cx, cy), int(r * 2.2 * SS), (*color, 255), -1, cv2.LINE_AA, shift=2)
    _blend(img, layer, 0.18 * flicker)
    cv2.circle(img, _p(cx, cy), int(r * 0.6 * SS), (255, 255, 230, 255), -1, cv2.LINE_AA, shift=2)


def _fish(img, cx, cy, r, color, e, t) -> None:
    ang = e.heading
    ca, sa = math.cos(ang), math.sin(ang)
    wiggle = math.sin(t * 9 + e.id) * 0.35

    def rot(x, y):
        return cx + x * ca - y * sa, cy + x * sa + y * ca

    cv2.ellipse(img, _p(cx, cy), _p(r, r * 0.45), math.degrees(ang), 0, 360, (*color, 255), -1, cv2.LINE_AA, shift=2)
    tail = [rot(-r * 0.9, 0), rot(-r * 1.6, -r * (0.5 + wiggle)), rot(-r * 1.6, r * (0.5 - wiggle))]
    cv2.fillPoly(img, [np.array([_p(*p) for p in tail], np.int32)], (*color, 255), cv2.LINE_AA, shift=2)
    ex, ey = rot(r * 0.5, -r * 0.12)
    cv2.circle(img, _p(ex, ey), max(1, int(r * 0.1 * SS)), (10, 10, 30, 255), -1, cv2.LINE_AA, shift=2)


_SPRITES = {"ghost": _ghost, "orb": _orb, "firefly": _firefly, "fish": _fish}


def _draw_debug(img, snap: Snapshot, w: int, h: int) -> None:
    """Pessoa (ponto na parede à frente dela) e região do olhar — para calibrar."""
    k = w / snap.spec.aspect
    for p, g in zip(snap.players, snap.gazes):
        ax, ay = p.anchor
        cv2.drawMarker(img, (int(ax * k), int(ay * h)), (0, 255, 0, 255), cv2.MARKER_CROSS, 24, 2)
        if g.active:
            cv2.circle(img, (int(g.center[0] * k), int(g.center[1] * h)), int(g.radius * h), (0, 200, 255, 255), 2,
                       cv2.LINE_AA)
        label = "olhando" if g.active else ("de costas" if p.tracked else "sem pessoa")
        cv2.putText(img, label, (int(ax * k) + 14, int(ay * h) - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 255, 0, 255), 1, cv2.LINE_AA)
