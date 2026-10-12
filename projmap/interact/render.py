"""Renderer nativo da cena interativa (sem TouchDesigner) — desenha em RGBA.

Vira a fonte ``interactive`` das superfícies do ProjMap: o resultado passa
pelo mesmo warp/máscara/blend de qualquer vídeo. Sprites procedurais em
OpenCV (rápidos, sem assets):

- ``ghost``: fantasma original (corpo arredondado, barra ondulada, olhos que
  seguem o movimento). Tímido = cobre os olhos com as mãos e fica translúcido.
- ``orb``: esfera brilhante · ``firefly``: ponto com halo que pisca ·
  ``fish``: corpo + cauda orientados pela direção.
- ``image``: PNG do usuário (``EntityGroup.skins``). Persegue opaco; quando é
  olhado, troca para a imagem "com vergonha" e fica translúcido
  (``shy_alpha``). Vira para o lado em que anda. Pixel art ampliada sem borrar.

Fundo: cor (``background``) ou imagem (``background_image``, em
``~/.projmap/scenes``).

Fundo preto = sem luz na projeção (só os elementos acendem a parede).
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import Optional

import cv2
import numpy as np

from .scene import asset_path
from .sim import Entity, Snapshot

log = logging.getLogger(__name__)

SS = 4  # subpixel do OpenCV (shift=2): contornos suaves em movimento lento


def render_snapshot(snap: Snapshot, size: tuple[int, int] = (1280, 720), debug: bool = False) -> np.ndarray:
    w, h = size
    spec = snap.spec
    img = np.empty((h, w, 4), dtype=np.uint8)
    img[:] = np.array([*spec.background, 255], dtype=np.uint8)  # broadcast contíguo (rápido)
    if spec.background_image:
        bg = _background(spec.background_image, w, h, spec.background_fit)
        if bg is not None:
            y0, x0 = (h - bg.shape[0]) // 2, (w - bg.shape[1]) // 2
            img[y0:y0 + bg.shape[0], x0:x0 + bg.shape[1], :3] = bg
    kx, ky = w / spec.aspect, h  # 1 unidade do mundo = altura da imagem
    for e in snap.entities:
        g = spec.groups[e.group]
        cx, cy = e.x * kx, e.y * ky
        r = max(2.0, g.size * ky / 2)
        if e.state == "defeated":
            age = snap.t - e.defeated_t
            if 0 <= age < 0.5:
                _poof(img, cx, cy, r, age / 0.5)
            continue
        # Desenha só numa janela em volta do sprite: as mesclas (halo, translúcido)
        # custam a área da janela, não a da tela inteira.
        ext = r * 2.6
        x0, y0 = max(0, int(cx - ext)), max(0, int(cy - ext))
        x1, y1 = min(w, int(cx + ext) + 1), min(h, int(cy + ext) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        if g.sprite == "image":
            if _image_sprite(img, cx, cy, r, g, e, snap.t):
                continue
            # sem imagem válida: cai no fantasma desenhado
            _ghost(img[y0:y1, x0:x1], cx - x0, cy - y0, r, g.color, e, snap.t)
            continue
        _SPRITES[g.sprite](img[y0:y1, x0:x1], cx - x0, cy - y0, r, g.color, e, snap.t)
    if snap.star is not None and spec.star is not None:
        _star(img, snap.star.x * kx, snap.star.y * ky, max(4.0, spec.star.size * ky / 2), spec.star.image,
              snap.t - snap.star.born)
    if snap.power > 0:
        _power_frame(img, snap.power, snap.t)
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


# ------------------------------------------------------------ imagens do usuário
@lru_cache(maxsize=64)
def _load_rgba(rel: str) -> Optional[np.ndarray]:
    path = asset_path(rel)
    try:
        data = np.fromfile(str(path), dtype=np.uint8)  # aceita caminho com acento no Windows
        im = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    except OSError:
        im = None
    if im is None:
        log.warning("cena: imagem não encontrada ou ilegível: %s", path)
        return None
    if im.ndim == 2:
        return cv2.cvtColor(im, cv2.COLOR_GRAY2RGBA)
    if im.shape[2] == 3:
        return cv2.cvtColor(im, cv2.COLOR_BGR2RGBA)
    return cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA)


@lru_cache(maxsize=8)
def _background(rel: str, w: int, h: int, fit: str) -> Optional[np.ndarray]:
    im = _load_rgba(rel)
    if im is None:
        return None
    ih, iw = im.shape[:2]
    if fit == "stretch":
        nw, nh = w, h
    else:
        k = max(w / iw, h / ih) if fit == "cover" else min(w / iw, h / ih)
        nw, nh = max(1, round(iw * k)), max(1, round(ih * k))
    # pixel art (fundo pequeno ampliado muito) fica nítida; foto fica suave
    interp = cv2.INTER_NEAREST if max(nw / iw, nh / ih) >= 2 else cv2.INTER_AREA
    rgb = cv2.resize(im[..., :3], (nw, nh), interpolation=interp)
    if fit == "cover":  # recorta o centro
        y0, x0 = (nh - h) // 2, (nw - w) // 2
        rgb = rgb[y0:y0 + h, x0:x0 + w]
    return np.ascontiguousarray(rgb)


@lru_cache(maxsize=128)
def _scaled(rel: str, size: int, pixelated: bool, flip: bool) -> Optional[np.ndarray]:
    im = _load_rgba(rel)
    if im is None:
        return None
    ih, iw = im.shape[:2]
    k = size / max(ih, iw)
    out = cv2.resize(im, (max(1, round(iw * k)), max(1, round(ih * k))),
                     interpolation=cv2.INTER_NEAREST if pixelated else cv2.INTER_AREA)
    return np.ascontiguousarray(out[:, ::-1] if flip else out)


def _image_sprite(img: np.ndarray, cx: float, cy: float, r: float, g, e: Entity, t: float) -> bool:
    """Desenha o PNG da entidade; devolve False se não houver imagem utilizável."""
    if not g.skins:
        return False
    skin = g.skins[e.id % len(g.skins)]
    scared = e.state == "scared"  # estrela ativa: foge piscando
    watched = e.state in ("shy", "frozen") or scared
    rel = skin.shy_image if (watched and skin.shy_image) else skin.image
    # vira para o lado em que anda (as imagens originais olham para a esquerda/frente)
    flip = math.cos(e.heading) > 0.2 and e.state == "move"
    sprite = _scaled(rel, max(4, int(round(r * 2))), g.pixelated, flip)
    if sprite is None:
        return False
    alpha_k = g.shy_alpha if watched else 1.0
    if scared:
        alpha_k = 0.35 + 0.45 * (0.5 + 0.5 * math.sin(t * 18 + e.id))  # pisca
        cx += math.sin(t * 40 + e.id) * r * 0.06  # treme
    bob = math.sin(t * 2.4 + e.id * 1.3) * r * 0.08  # flutua
    sh, sw = sprite.shape[:2]
    x0, y0 = int(round(cx - sw / 2)), int(round(cy + bob - sh / 2))
    H, W = img.shape[:2]
    ax0, ay0, ax1, ay1 = max(0, x0), max(0, y0), min(W, x0 + sw), min(H, y0 + sh)
    if ax1 <= ax0 or ay1 <= ay0:
        return True
    src = sprite[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0]
    a = (src[..., 3:4].astype(np.float32) / 255.0) * alpha_k
    dst = img[ay0:ay1, ax0:ax1, :3]
    dst[:] = (src[..., :3] * a + dst * (1.0 - a)).astype(np.uint8)
    return True


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


# ------------------------------------------------------------------ estrela
RAINBOW = [(255, 0, 0), (255, 96, 0), (255, 240, 0), (32, 255, 0), (0, 220, 255), (0, 40, 255), (170, 0, 255),
           (255, 20, 200)]


@lru_cache(maxsize=1)
def _pixel_star() -> np.ndarray:
    """Estrela pixelada com faixas de arco-íris e contorno preto (fallback sem PNG)."""
    n = 25
    c = n / 2 - 0.5
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = 12.0 if i % 2 == 0 else 5.2
        pts.append((c + rad * math.cos(ang), c + 1.2 + rad * math.sin(ang)))
    mask = np.zeros((n, n), np.uint8)
    cv2.fillPoly(mask, [np.round(np.array(pts)).astype(np.int32)], 1)
    out = np.zeros((n, n, 4), np.uint8)
    yy, xx = np.mgrid[0:n, 0:n]
    band = ((xx - yy + n) * len(RAINBOW) // (2 * n)) % len(RAINBOW)
    for i, col in enumerate(RAINBOW):
        sel = (mask == 1) & (band == i)
        out[sel] = (*col, 255)
    edge = cv2.dilate(mask, np.ones((3, 3), np.uint8)) - mask
    out[edge == 1] = (0, 0, 0, 255)
    for ex in (c - 2, c + 2):  # olhos
        out[int(c), int(ex)] = (0, 0, 0, 255)
        out[int(c) + 1, int(ex)] = (0, 0, 0, 255)
    return out


def _star_sprite(rel: Optional[str], size: int) -> np.ndarray:
    if rel:
        sp = _scaled(rel, size, True, False)
        if sp is not None:
            return sp
    base = _pixel_star()
    return cv2.resize(base, (size, size), interpolation=cv2.INTER_NEAREST)


def _paste(img: np.ndarray, sprite: np.ndarray, cx: float, cy: float, alpha: float = 1.0) -> None:
    sh, sw = sprite.shape[:2]
    x0, y0 = int(round(cx - sw / 2)), int(round(cy - sh / 2))
    H, W = img.shape[:2]
    ax0, ay0, ax1, ay1 = max(0, x0), max(0, y0), min(W, x0 + sw), min(H, y0 + sh)
    if ax1 <= ax0 or ay1 <= ay0:
        return
    src = sprite[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0]
    a = (src[..., 3:4].astype(np.float32) / 255.0) * alpha
    dst = img[ay0:ay1, ax0:ax1, :3]
    dst[:] = (src[..., :3] * a + dst * (1.0 - a)).astype(np.uint8)


def _star(img, cx, cy, r, rel: Optional[str], age: float) -> None:
    pulse = 1.0 + 0.08 * math.sin(age * 10)
    # brilho dourado em volta
    H, W = img.shape[:2]
    ext = int(r * 2.2)
    x0, y0, x1, y1 = max(0, int(cx - ext)), max(0, int(cy - ext)), min(W, int(cx + ext)), min(H, int(cy + ext))
    if x1 > x0 and y1 > y0:
        win = img[y0:y1, x0:x1]
        layer = win.copy()
        cv2.circle(layer, _p(cx - x0, cy - y0), int(r * 1.5 * SS), (255, 240, 140, 255), -1, cv2.LINE_AA, shift=2)
        _blend(win, layer, 0.38 + 0.12 * math.sin(age * 8))
    # faíscas de arco-íris girando
    for k in range(6):
        ang = age * 3 + k * math.pi / 3
        sx, sy = cx + math.cos(ang) * r * 1.35, cy + math.sin(ang) * r * 1.35
        col = RAINBOW[(k + int(age * 8)) % len(RAINBOW)]
        cv2.circle(img, _p(sx, sy), max(1, int(r * 0.12 * SS)), (*col, 255), -1, cv2.LINE_AA, shift=2)
    _paste(img, _star_sprite(rel, max(6, int(r * 2 * pulse))), cx, cy)


def _poof(img, cx, cy, r, k: float) -> None:
    """Fantasma derrotado: anel que se expande e some + estrelinhas."""
    H, W = img.shape[:2]
    ext = int(r * 2.5)
    x0, y0, x1, y1 = max(0, int(cx - ext)), max(0, int(cy - ext)), min(W, int(cx + ext)), min(H, int(cy + ext))
    if x1 <= x0 or y1 <= y0:
        return
    win = img[y0:y1, x0:x1]
    layer = win.copy()
    rad = r * (0.6 + 1.4 * k)
    cv2.circle(layer, _p(cx - x0, cy - y0), int(rad * SS), (255, 255, 255, 255), max(1, int(r * 0.15)), cv2.LINE_AA, shift=2)
    for i in range(5):
        ang = i * 2 * math.pi / 5
        cv2.circle(layer, _p(cx - x0 + math.cos(ang) * rad, cy - y0 + math.sin(ang) * rad),
                   max(1, int(r * 0.1 * SS)), (*RAINBOW[i * 2 % len(RAINBOW)], 255), -1, cv2.LINE_AA, shift=2)
    _blend(win, layer, 1.0 - k)


def _power_frame(img, power: float, t: float) -> None:
    """Invencível: borda de arco-íris pulsando + barra do tempo restante no topo."""
    H, W = img.shape[:2]
    th = max(4, H // 60)
    col = RAINBOW[int(t * 10) % len(RAINBOW)]
    a = 0.55 + 0.25 * math.sin(t * 12)
    for sl in (np.s_[:th, :], np.s_[-th:, :], np.s_[:, :th], np.s_[:, -th:]):
        region = img[sl][..., :3]
        region[:] = (np.array(col) * a + region * (1 - a)).astype(np.uint8)
    bw = int((W - 4 * th) * power)
    if bw > 0:
        img[th * 2:th * 3, th * 2:th * 2 + bw, :3] = RAINBOW[int(t * 6 + 3) % len(RAINBOW)]
