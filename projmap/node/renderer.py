"""Renderer do nó (moderngl): superfícies → composite → framebuffer do projetor.

Funciona com qualquer framebuffer: a tela do projetor (janela pyglet), um FBO
offscreen (testes, modo *baked*) ou uma janela de preview menor — o espaço de
coordenadas é sempre o da saída do projeto (``output.width × height``), e o
shader escala para o framebuffer real.

Ciclo por frame (BLUEPRINT §5.3)::

    sync(projeto) só quando a revisão muda
    para cada superfície (z crescente):
        frame = fonte.frame_at(t) → textura (só se a chave mudou)
        draw quad com u_hinv (homografia inversa) + fit + feather + blend
    overlay de contornos (opcional)

Os shaders estão em GLSL ES 3.00 com o ``#version`` injetado: no desktop
roda como 330 core; no Raspberry Pi 5 o mesmo corpo vira ``300 es``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import cv2
import moderngl
import numpy as np

from ..content.base import FrameSource, StaticSource
from ..content.factory import get_source
from ..content.patterns import edges_pattern, grid_pattern, solid
from ..core.geometry import rect_quad
from ..core.project import ColorAdjust, Layer, Node, Project, SourceSpec, Surface
from ..mapping.warp import UvTransform, fit_transform, hinv_for, layer_uvx

log = logging.getLogger(__name__)

SHADER_DIR = Path(__file__).parent / "shaders"
DESKTOP_HEADER = "#version 330 core\n"
GLES_HEADER = "#version 300 es\nprecision highp float;\nprecision highp int;\n"

NEUTRAL = ColorAdjust()

MediaResolver = Callable[[str], Path]
PathResolver = Callable[[Optional[str]], Optional[Path]]


def shader_source(name: str, gles: bool = False) -> str:
    return (GLES_HEADER if gles else DESKTOP_HEADER) + (SHADER_DIR / name).read_text(encoding="utf-8")


def _quad_triangles(quad) -> np.ndarray:
    q = np.asarray(quad, dtype="f4")
    return np.array([q[0], q[1], q[2], q[0], q[2], q[3]], dtype="f4")


@dataclass
class _Item:
    """Uma coisa desenhável: o fundo de uma superfície ou uma das camadas dela (F9)."""

    surface: Surface
    source_key: str
    source: Optional[FrameSource]
    vbo: moderngl.Buffer
    vao: moderngl.VertexArray
    hinv: np.ndarray
    texture: Optional[moderngl.Texture] = None
    frame_key: Optional[int] = None
    uvx: UvTransform = field(default_factory=UvTransform)
    layer: Optional[Layer] = None

    @property
    def spec(self) -> SourceSpec:
        return self.layer.source if self.layer is not None else self.surface.source

    @property
    def opacity(self) -> float:
        return self.surface.opacity * (self.layer.opacity if self.layer is not None else 1.0)

    def fit_uvx(self) -> UvTransform:
        if self.source is None:
            return UvTransform()
        quad = self.surface.warp.base
        if self.layer is not None:
            return layer_uvx(self.layer.rect, self.layer.source.fit, self.source.size, quad)
        return fit_transform(self.surface.source.fit, self.source.size, quad)


class Renderer:
    def __init__(self, ctx: moderngl.Context, media_path: MediaResolver, resolve_path: PathResolver,
                 gles: bool = False):
        self.ctx = ctx
        self._media_path = media_path
        self._resolve_path = resolve_path
        self.surface_prog = ctx.program(
            vertex_shader=shader_source("surface.vert", gles),
            fragment_shader=shader_source("surface.frag", gles),
        )
        self.line_prog = ctx.program(
            vertex_shader=shader_source("surface.vert", gles),
            fragment_shader=shader_source("line.frag", gles),
        )
        self._items: list[_Item] = []
        self._surfaces: list[Surface] = []
        self._node: Optional[Node] = None
        self._pattern_key: Optional[tuple] = None
        self._pattern: Optional[_Item] = None
        self._outline_vbo = ctx.buffer(reserve=4096, dynamic=True)
        self._outline_vao = ctx.vertex_array(self.line_prog, [(self._outline_vbo, "2f", "in_pos")])

    # ------------------------------------------------------------------- sync
    def sync(self, project: Project, node_id: str) -> None:
        """Reconstrói a lista de desenho. Fontes são reaproveitadas pela chave da
        especificação: mover um canto não reinicia o vídeo daquela superfície.

        Cada superfície vira o fundo (``source``) e, por cima, as camadas visíveis
        (F9), na ordem da lista."""
        self._node = project.node(node_id)
        old = {(i.surface.id, i.source_key): i for i in self._items}
        items: list[_Item] = []
        for surf in project.surfaces_for(node_id):
            parts: list[tuple[Optional[Layer], SourceSpec]] = [(None, surf.source)]
            parts += [(layer, layer.source) for layer in surf.layers if layer.visible]
            for layer, spec in parts:
                key = (f"layer:{layer.id}:" if layer else "base:") + json.dumps(spec.model_dump(mode="json"), sort_keys=True)
                prev = old.pop((surf.id, key), None)
                if prev is not None:
                    source, texture, frame_key = prev.source, prev.texture, prev.frame_key
                    prev.vao.release()
                    prev.vbo.release()
                else:
                    source, texture, frame_key = self._open_spec(surf.id, spec), None, None
                if source is None:
                    continue
                vbo = self.ctx.buffer(_quad_triangles(surf.warp.base).tobytes())
                vao = self.ctx.vertex_array(self.surface_prog, [(vbo, "2f", "in_pos")])
                item = _Item(surf, key, source, vbo, vao, hinv_for(surf.warp.base), texture, frame_key, layer=layer)
                item.uvx = item.fit_uvx()
                items.append(item)
        for stale in old.values():
            self._release_item(stale)
        self._items = items
        self._surfaces = project.surfaces_for(node_id)

    def _open_spec(self, surface_id: str, spec: SourceSpec) -> Optional[FrameSource]:
        try:
            return get_source(spec, self._media_path)
        except Exception as exc:  # noqa: BLE001 — mídia ruim não derruba o show
            log.error("superfície %s: fonte indisponível (%s)", surface_id, exc)
            return StaticSource(solid(2, 2, (255, 0, 255)))  # magenta = "erro de mídia"

    # ----------------------------------------------------------------- render
    def render(self, fbo: moderngl.Framebuffer, t: float) -> None:
        ctx = self.ctx
        fbo.use()
        vw, vh = fbo.viewport[2], fbo.viewport[3]
        ctx.clear(0.0, 0.0, 0.0, 1.0)
        node = self._node
        if node is None or node.output.blackout:
            return
        out = node.output
        size = (float(out.width), float(out.height))
        self.surface_prog["u_out_size"].value = size
        self.surface_prog["u_viewport"].value = (float(vw), float(vh))
        self.line_prog["u_out_size"].value = size
        flip = (-1.0 if out.flip_h else 1.0, -1.0 if out.flip_v else 1.0)
        self.surface_prog["u_flip"].value = flip
        self.line_prog["u_flip"].value = flip
        ctx.enable(moderngl.BLEND)

        if out.pattern != "none":
            # Padrões de alinhamento saem "puros": o ajuste de cor só vale para o conteúdo.
            self._set_adjust("o", NEUTRAL)
            self._draw_pattern(node)
        else:
            self._set_adjust("o", out.color)
            for item in self._items:
                self._draw_item(item, t, out.intensity)

        if out.show_outlines:
            self._draw_outlines()
        ctx.disable(moderngl.BLEND)

    def _draw_item(self, item: _Item, t: float, intensity: float) -> None:
        surf = item.surface
        if item.source is None:
            return
        try:
            key, rgba = item.source.frame_at(t)
        except Exception as exc:  # noqa: BLE001 — falha de decodificação ao vivo não derruba o projetor
            log.error("superfície %s: falha ao ler quadro (%s); usando fallback magenta", surf.id, exc)
            try:
                item.source.close()
            except Exception:  # noqa: BLE001
                pass
            item.source = StaticSource(solid(2, 2, (255, 0, 255)))
            key, rgba = item.source.frame_at(t)
        if item.texture is None or item.frame_key != key or item.texture.size != (rgba.shape[1], rgba.shape[0]):
            item.texture = self._upload(item.texture, rgba)
            item.frame_key = key
            if item.layer is not None or surf.source.fit != "stretch":
                item.uvx = item.fit_uvx()
        prog = self.surface_prog
        prog["u_hinv"].write(item.hinv.astype("f4").T.tobytes())  # GLSL mat3 é column-major
        prog["u_uvx"].value = (*item.uvx.scale, *item.uvx.offset)
        prog["u_opacity"].value = float(item.opacity * intensity)
        prog["u_feather"].value = float(surf.feather)
        prog["u_multiply"].value = 1 if surf.blend_mode == "multiply" else 0
        self._set_adjust("s", surf.color)
        if surf.blend_mode == "add":
            self.ctx.blend_func = moderngl.ONE, moderngl.ONE
        elif surf.blend_mode == "multiply":
            self.ctx.blend_func = moderngl.DST_COLOR, moderngl.ZERO
        else:
            self.ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
        item.texture.use(location=0)
        prog["u_tex"].value = 0
        item.vao.render(moderngl.TRIANGLES)

    def _set_adjust(self, which: str, c: ColorAdjust) -> None:
        self.surface_prog[f"u_adj_{which}"].value = (c.brightness, c.contrast, c.saturation, c.gamma)
        self.surface_prog[f"u_temp_{which}"].value = c.temperature

    def _draw_pattern(self, node: Node) -> None:
        out = node.output
        key = (out.pattern, out.width, out.height, node.photo, tuple(map(tuple, node.photo_boundary)))
        if self._pattern_key != key:
            if self._pattern is not None:
                self._release_item(self._pattern)
            rgba = self._pattern_image(node)
            quad = rect_quad(0, 0, out.width, out.height)
            vbo = self.ctx.buffer(_quad_triangles(quad).tobytes())
            vao = self.ctx.vertex_array(self.surface_prog, [(vbo, "2f", "in_pos")])
            surf = Surface.model_validate({"id": "pattern", "node_id": node.id, "warp": {"base": quad}})
            self._pattern = _Item(surf, "", StaticSource(rgba), vbo, vao, hinv_for(quad))
            self._pattern_key = key
        self._draw_item(self._pattern, 0.0, out.intensity)

    def _pattern_image(self, node: Node) -> np.ndarray:
        out = node.output
        if out.pattern == "white":
            return solid(2, 2)
        if out.pattern == "black":
            return solid(2, 2, (0, 0, 0))
        if out.pattern == "edges":
            photo = self._resolve_path(node.photo)
            if photo and photo.is_file():
                bgr = cv2.imdecode(np.fromfile(str(photo), dtype=np.uint8), cv2.IMREAD_COLOR)
                if bgr is not None:
                    return edges_pattern(bgr, node.photo_boundary, (out.width, out.height))
            log.warning("padrão 'edges' sem foto do nó %s; usando grade", node.id)
        return grid_pattern(out.width, out.height)

    def _draw_outlines(self) -> None:
        """Contorno de cada quad + marcador no canto TL (orientação da textura)."""
        if not self._surfaces:
            return
        prog = self.line_prog
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        out_w = float(self._node.output.width) if self._node else 1920.0
        r = max(4.0, out_w / 160.0)
        for surf in self._surfaces:
            q = np.asarray(surf.warp.base, dtype="f4")
            loop = np.vstack([q, q[:1]])
            self._outline_vbo.orphan(loop.nbytes)
            self._outline_vbo.write(loop.tobytes())
            prog["u_color"].value = (0.2, 1.0, 0.4, 1.0)
            self._outline_vao.render(moderngl.LINE_STRIP, vertices=5)
            x, y = q[0]
            tl = np.array(rect_quad(x - r, y - r, 2 * r, 2 * r), dtype="f4")
            tri = _quad_triangles(tl)
            self._outline_vbo.orphan(tri.nbytes)
            self._outline_vbo.write(tri.tobytes())
            prog["u_color"].value = (1.0, 0.3, 0.3, 1.0)
            self._outline_vao.render(moderngl.TRIANGLES, vertices=6)

    # ---------------------------------------------------------------- texturas
    def _make_texture(self, rgba: np.ndarray) -> moderngl.Texture:
        h, w = rgba.shape[:2]
        tex = self.ctx.texture((w, h), 4, np.ascontiguousarray(rgba).tobytes())
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        tex.repeat_x = tex.repeat_y = False
        return tex

    def _upload(self, tex: Optional[moderngl.Texture], rgba: np.ndarray) -> moderngl.Texture:
        h, w = rgba.shape[:2]
        if tex is None or tex.size != (w, h):
            if tex is not None:
                tex.release()
            return self._make_texture(rgba)
        tex.write(np.ascontiguousarray(rgba).tobytes())
        return tex

    def _release_item(self, item: _Item) -> None:
        item.vao.release()
        item.vbo.release()
        if item.texture is not None:
            item.texture.release()
        if item.source is not None:
            item.source.close()

    def release(self) -> None:
        for item in self._items:
            self._release_item(item)
        self._items = []
        if self._pattern is not None:
            self._release_item(self._pattern)
            self._pattern = None


def render_offscreen(project: Project, node_id: str, media_path: MediaResolver, resolve_path: PathResolver,
                     t: float = 0.0, ctx: Optional[moderngl.Context] = None,
                     size: Optional[tuple[int, int]] = None) -> np.ndarray:
    """Renderiza um frame num FBO e devolve RGB ``uint8 (h, w, 3)`` (linha 0 = topo)."""
    own = ctx is None
    ctx = ctx or moderngl.create_standalone_context()
    node = project.node(node_id)
    w, h = size or (node.output.width, node.output.height)
    fbo = ctx.simple_framebuffer((w, h), components=4)
    renderer = Renderer(ctx, media_path, resolve_path)
    try:
        renderer.sync(project, node_id)
        renderer.render(fbo, t)
        data = np.frombuffer(fbo.read(components=3, alignment=1), dtype=np.uint8).reshape(h, w, 3)
        return np.flipud(data).copy()  # OpenGL lê de baixo para cima
    finally:
        renderer.release()
        fbo.release()
        if own:
            ctx.release()
