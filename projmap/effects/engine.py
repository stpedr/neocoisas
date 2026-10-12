"""Motor dos efeitos: roda o shader importado do visual_frames num contexto
OpenGL fora da tela e entrega quadros RGBA para as superfícies do ProjMap.

Tradução das partes de ``ofApp.cpp`` que alimentam o shader: ``update()``
(fade entre efeitos, ganho da câmera), ``atualizarEcos()``,
``atualizarSlots()``, ``atualizarMusica()``, ``atualizarCentroCena()`` e
``desenharEfeitos()``. O shader é o original, sem alterações.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from . import config as C
from .audio import AudioAnalyzer, AudioLevels
from .catalog import EFFECTS
from .importar import DEST, is_imported
from .tracker import NUM_KEYPOINTS
from .vision import VisionProcessor, VisionResult

log = logging.getLogger(__name__)

VERTEX = """#version 150
in vec2 in_pos;
out vec2 uv;
void main() { uv = in_pos * 0.5 + 0.5; gl_Position = vec4(in_pos, 0.0, 1.0); }
"""
NUM_ELOS_RABO = 6  # tamanho de raboPontos por pessoa no shader original (fase 2)


def aproximar(atual: float, alvo: float, dt: float, tau: float) -> float:
    return atual + (alvo - atual) * (1.0 - math.exp(-dt / tau)) if dt > 0 else atual


@dataclass
class EffectParams:
    """Os ajustes do ``EstadoPainel`` original (mesmos padrões)."""

    orbes_maos: bool = False
    cor_segue_musica: bool = True
    matiz_fixo: float = 0.75
    sensibilidade_som: float = 1.0
    quantidade_ecos: float = 6.0
    distancia_ecos: float = 4.0
    tamanho_peca: float = 16.0
    lego_cair: bool = True
    brilho: float = 1.0


@dataclass
class _Slot:
    id: int = -1
    presenca: float = 0.0
    energia_e: float = 0.0
    energia_d: float = 0.0
    altura: float = 0.0
    pontos: np.ndarray = field(default_factory=lambda: np.zeros((NUM_KEYPOINTS, 3), np.float32))


class EffectsEngine:
    def __init__(self, size: tuple[int, int] = (1280, 720), base: Path = DEST, camera: "int | str" = "auto",
                 vision: Optional[VisionProcessor] = None, audio: Optional[AudioAnalyzer] = None,
                 threaded: bool = True):
        self.size = size
        self.base = Path(base)
        self.camera = camera
        self.params = EffectParams()
        self.effect: Optional[str] = None  # "luz" | "lego" | "ecos"
        self._vision = vision
        self._audio = audio
        self._threaded = threaded
        self._lock = threading.Lock()
        self._frame: tuple[int, np.ndarray] = (0, np.zeros((size[1], size[0], 4), np.uint8))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self.error = ""
        # estado do ofApp
        self._vres = VisionResult()
        self._slots = [_Slot() for _ in range(C.MAX_PESSOAS)]
        self._fade = {"luz": 0.0, "ecos": 0.0, "lego": 0.0, "maos": 0.0}
        self._hist: deque[np.ndarray] = deque(maxlen=8 * 8 + 1)
        self._ganho_camera = 1.0
        self._matiz = 0.0
        self._flash = 0.0
        self._carimbo_forca = 0.0
        self._ultima_batida = 0
        self._centro = np.array([0.5, 0.5], np.float32)
        self._t0 = time.perf_counter()
        self._seq = 0

    # ------------------------------------------------------------------- vida
    def start(self) -> "EffectsEngine":
        if not is_imported(self.base):
            raise RuntimeError("efeitos não importados: rode  python -m projmap.effects.importar")
        if self._vision is None:
            self._vision = VisionProcessor(self.base / "modelos", self.camera).start()
        if self._audio is None:
            self._audio = AudioAnalyzer().start()
        if self._threaded:
            self._thread = threading.Thread(target=self._run, name="vf-motor", daemon=True)
            self._thread.start()
            self._ready.wait(10)
        else:
            self._init_gl()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        for comp in (self._vision, self._audio):
            if comp is not None:
                comp.stop()

    def set_effect(self, key: Optional[str]) -> None:
        """``key``: "vf-luz" | "vf-lego" | "vf-ecos" (ou o id interno) | None."""
        if key is not None:
            key = EFFECTS[key].shader_id if key in EFFECTS else key
        self.effect = key

    def frame(self) -> tuple[int, np.ndarray]:
        with self._lock:
            return self._frame

    @property
    def status(self) -> str:
        if self.error:
            return self.error
        return self._vision.status if self._vision else "parado"

    # --------------------------------------------------------------------- GL
    def _init_gl(self) -> None:
        import moderngl

        w, h = self.size
        self.ctx = moderngl.create_standalone_context()
        frag = (self.base / "efeitos.frag").read_text(encoding="utf-8")
        self.prog = self.ctx.program(vertex_shader=VERTEX, fragment_shader=frag)
        quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32)
        self.vao = self.ctx.vertex_array(self.prog, [(self.ctx.buffer(quad.tobytes()), "2f", "in_pos")])
        self.fbo = self.ctx.simple_framebuffer((w, h), components=4)
        mw, mh = C.MASCARA_LARGURA, C.MASCARA_ALTURA

        def tex(size, comps):
            t = self.ctx.texture(size, comps)
            t.repeat_x = t.repeat_y = False
            return t

        self.tex = {
            "mascara": tex((mw, mh), 2), "ecosA": tex((mw, mh), 4), "ecosB": tex((mw, mh), 4),
            "carimbo": tex((mw, mh), 1), "quadrinho": tex((mw, mh), 4),
            "camera": tex((C.CAMERA_LARGURA, C.CAMERA_ALTURA), 3),
        }
        for unit, name in enumerate(("mascara", "ecosA", "ecosB", "carimbo", "quadrinho", "camera")):
            self.tex[name].use(location=unit)
            if name in self.prog:
                self.prog[name].value = unit
        self._ready.set()

    def _run(self) -> None:
        try:
            self._init_gl()
        except Exception as exc:  # noqa: BLE001
            self.error = f"OpenGL: {exc}"
            log.error(self.error)
            self._ready.set()
            return
        last = time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            dt, last = now - last, now
            try:
                self.step(dt)
            except Exception as exc:  # noqa: BLE001 — um quadro ruim não derruba o show
                log.exception("efeitos: %s", exc)
            time.sleep(max(0.0, 1 / 60 - (time.perf_counter() - now)))

    # ------------------------------------------------------------------ passo
    def step(self, dt: float, vision: Optional[VisionResult] = None, audio: Optional[AudioLevels] = None) -> np.ndarray:
        """Um quadro (público para testes: dá para injetar visão e áudio)."""
        p = self.params
        eff = self.effect
        if self._vision is not None:
            self._vision.want_comic = eff == "ecos" or self._fade["ecos"] > 0.01
            self._vision.want_frame = eff == "lego" or self._fade["lego"] > 0.01
        new = vision if vision is not None else (self._vision.latest(self._vres.seq) if self._vision else None)
        if new is not None:
            self._on_vision(new)
        self._update_slots(dt)
        self._update_music(dt, audio if audio is not None else (self._audio.get() if self._audio else AudioLevels()))
        for name in ("luz", "ecos", "lego"):
            self._fade[name] = aproximar(self._fade[name], 1.0 if eff == name else 0.0, dt, 0.25)
        self._fade["maos"] = aproximar(self._fade["maos"], 1.0 if (eff == "luz" and p.orbes_maos) else 0.0, dt, 0.25)
        self._update_center(dt)
        img = self._draw()
        self._seq += 1
        with self._lock:
            self._frame = (self._seq, img)
        return img

    def _on_vision(self, r: VisionResult) -> None:
        self._vres = r
        if r.mask is None:
            return
        self.tex["mascara"].write(np.ascontiguousarray(r.mask).tobytes())
        alpha = np.ascontiguousarray(r.mask[..., 0])
        self._hist.appendleft(alpha)
        lego = self.effect == "lego" or self._fade["lego"] > 0.01
        if self.effect == "ecos" or self._fade["ecos"] > 0.01 or lego:
            passo = 2 if lego else max(1, round(self.params.distancia_ecos))
            empty = np.zeros_like(alpha)

            def eco(j: int) -> np.ndarray:
                i = (j + 1) * passo
                return self._hist[i] if i < len(self._hist) else empty

            self.tex["ecosA"].write(np.dstack([eco(0), eco(1), eco(2), eco(3)]).tobytes())
            self.tex["ecosB"].write(np.dstack([eco(4), eco(5), eco(6), eco(7)]).tobytes())
        if r.comic is not None:
            self.tex["quadrinho"].write(np.ascontiguousarray(r.comic).tobytes())
        if lego and r.frame is not None:
            self.tex["camera"].write(np.ascontiguousarray(r.frame[..., ::-1]).tobytes())  # BGR -> RGB
            small = cv2.resize(r.frame, (C.MASCARA_LARGURA, C.MASCARA_ALTURA), interpolation=cv2.INTER_AREA)
            sel = alpha > 128
            if sel.any():
                b, g, rr = small[sel].mean(axis=0)
                lum = (0.114 * b + 0.587 * g + 0.299 * rr) / 255.0
                alvo = float(np.clip(0.5 / lum, 1.0, 4.0)) if lum > 0.01 else 1.0
                self._ganho_camera += (alvo - self._ganho_camera) * 0.2

    def _update_slots(self, dt: float) -> None:
        by_slot = {pp.slot: pp for pp in self._vres.people}
        for s, slot in enumerate(self._slots):
            pp = by_slot.get(s)
            alvo = alvo_e = alvo_d = 0.0
            if pp is not None:
                if slot.id != pp.id:
                    self._slots[s] = slot = _Slot(id=pp.id)
                alvo = 1.0 if pp.active else 0.0
                alvo_e, alvo_d = pp.wrist_speed_l, pp.wrist_speed_r
                slot.altura = float((pp.box[3] - pp.box[1]) / C.CAMERA_ALTURA)
                slot.pontos = np.column_stack([pp.points[:, 0] / C.CAMERA_LARGURA, pp.points[:, 1] / C.CAMERA_ALTURA,
                                               pp.points[:, 2]]).astype(np.float32)
            slot.presenca = aproximar(slot.presenca, alvo, dt, 0.12 if alvo > slot.presenca else 0.45)
            slot.energia_e = aproximar(slot.energia_e, alvo_e, dt, 0.06 if alvo_e > slot.energia_e else 0.5)
            slot.energia_d = aproximar(slot.energia_d, alvo_d, dt, 0.06 if alvo_d > slot.energia_d else 0.5)

    def _update_music(self, dt: float, lv: AudioLevels) -> None:
        p = self.params
        k = p.sensibilidade_som
        self._lv = AudioLevels(min(1, lv.grave * k), min(1, lv.medio * k), min(1, lv.agudo * k),
                               min(1, lv.geral * k), lv.batidas, lv.ativo)
        beat = lv.batidas != self._ultima_batida
        self._ultima_batida = lv.batidas
        if beat:
            self._flash = 1.0
            if self.effect == "ecos" and self._hist:
                self.tex["carimbo"].write(self._hist[0].tobytes())  # carimba a silhueta atual
                self._carimbo_forca = 1.0
        self._carimbo_forca = aproximar(self._carimbo_forca, 0.0, dt, 0.7)
        if p.cor_segue_musica:
            vel = 0.015 + (0.12 * self._lv.geral if self._lv.ativo else 0.0)
            if beat:
                self._matiz += 0.06 + 0.08 * self._lv.grave
            self._matiz = (self._matiz + vel * dt) % 1.0
        else:
            self._matiz = p.matiz_fixo
        self._flash = aproximar(self._flash, 0.0, dt, 0.15)

    def _update_center(self, dt: float) -> None:
        """Centro da pessoa principal (raios do fundo dos Ecos). O original usa
        a cabeça do bichinho; aqui o nariz, que é o mesmo ponto na prática."""
        best = 0.0
        for slot in self._slots:
            nose = slot.pontos[0]
            if slot.presenca > best and nose[2] > 0.3:
                best = slot.presenca
                self._centro += (nose[:2] - self._centro) * (1.0 - math.exp(-dt / 0.3))

    def _draw(self) -> np.ndarray:
        w, h = self.size
        pr = self.prog
        p = self.params
        pontos = np.zeros((C.MAX_PESSOAS * NUM_KEYPOINTS, 3), np.float32)
        pessoas = np.zeros((C.MAX_PESSOAS, 4), np.float32)
        for s, slot in enumerate(self._slots):
            pessoas[s] = (slot.presenca, slot.energia_e, slot.energia_d, slot.altura)
            pontos[s * NUM_KEYPOINTS:(s + 1) * NUM_KEYPOINTS] = slot.pontos
        lv = self._lv

        def put(name: str, value) -> None:
            if name not in pr:
                return
            if isinstance(value, np.ndarray):
                pr[name].write(value.astype(np.float32).tobytes())
            else:
                pr[name].value = value

        put("resolucao", (float(w), float(h)))
        put("tempo", time.perf_counter() - self._t0)
        put("pontos", pontos)
        put("pessoas", pessoas)
        put("efeitoMaos", self._fade["maos"])
        put("efeitoNuvem", self._fade["luz"])
        put("efeitoEcos", self._fade["ecos"])
        put("numEcos", float(round(p.quantidade_ecos)))
        put("carimboForca", self._carimbo_forca)
        put("centroCena", (float(self._centro[0]), float(self._centro[1])))
        put("efeitoBichinho", 0.0)  # fase 2
        put("efeitoFundo", 0.0)
        put("animal", 0.0)
        put("efeitoLego", self._fade["lego"])
        put("tamanhoPeca", float(p.tamanho_peca))
        put("legoCair", 1.0 if p.lego_cair else 0.0)
        put("ganhoCamera", float(self._ganho_camera))
        put("brilhoGeral", float(p.brilho))
        put("musica", (lv.grave, lv.medio, lv.agudo, self._flash))
        put("matiz", float(self._matiz))
        for i, name in enumerate(("mascara", "ecosA", "ecosB", "carimbo", "quadrinho", "camera")):
            self.tex[name].use(location=i)
        self.fbo.use()
        self.fbo.clear(0.0, 0.0, 0.0, 1.0)
        self.vao.render(mode=5)  # TRIANGLE_STRIP
        data = self.fbo.read(components=4, alignment=1)
        # Linha 0 do FBO = uv.y 0 = linha 0 da máscara (topo da câmera): já está na orientação da imagem.
        return np.frombuffer(data, np.uint8).reshape(h, w, 4).copy()
