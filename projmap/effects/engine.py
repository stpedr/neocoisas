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
from .critter import NUM_ELOS_RABO, Critter
from .dynamics import aproximar, smoothstep
from .faces import FaceCropper
from .importar import DEST, is_imported
from .parachutes import Parachutists
from .tracker import NUM_KEYPOINTS
from .vision import VisionProcessor, VisionResult

log = logging.getLogger(__name__)

VERTEX = """#version 150
in vec2 in_pos;
out vec2 uv;
void main() { uv = in_pos * 0.5 + 0.5; gl_Position = vec4(in_pos, 0.0, 1.0); }
"""


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
    animal: float = 0.0  # 0 gato, 1 dinossauro, 2 coelho
    fundo_colorido: bool = True
    intervalo_aviao: float = 10.0
    brilho: float = 1.0


@dataclass
class _Slot:
    id: int = -1
    presenca: float = 0.0
    energia_e: float = 0.0
    energia_d: float = 0.0
    altura: float = 0.0
    pontos: np.ndarray = field(default_factory=lambda: np.zeros((NUM_KEYPOINTS, 3), np.float32))
    critter: Critter = field(default_factory=Critter)


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
        self._fade = {"luz": 0.0, "ecos": 0.0, "lego": 0.0, "maos": 0.0,
                      "bichinho": 0.0, "paraquedas": 0.0, "fundo": 1.0}
        self._faces = FaceCropper()
        self._parachutes = Parachutists()
        self._rostos: list = []
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
        """``key``: uma chave de ``catalog.EFFECTS`` (ou o id interno) | None."""
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
        visivel = lambda name: eff == name or self._fade[name] > 0.01  # noqa: E731
        precisa_rostos = visivel("paraquedas")
        if self._vision is not None:
            self._vision.want_comic = visivel("ecos")
            # O quadro da câmera serve às cores das peças (LEGO) e aos rostos
            # dos paraquedistas.
            self._vision.want_frame = visivel("lego") or precisa_rostos
        new = vision if vision is not None else (self._vision.latest(self._vres.seq) if self._vision else None)
        if new is not None:
            self._on_vision(new)
        self._update_slots(dt)
        self._update_music(dt, audio if audio is not None else (self._audio.get() if self._audio else AudioLevels()))
        for name in ("luz", "ecos", "lego", "bichinho", "paraquedas"):
            self._fade[name] = aproximar(self._fade[name], 1.0 if eff == name else 0.0, dt, 0.25)
        self._fade["maos"] = aproximar(self._fade["maos"], 1.0 if (eff == "luz" and p.orbes_maos) else 0.0, dt, 0.25)
        self._fade["fundo"] = aproximar(self._fade["fundo"], 1.0 if p.fundo_colorido else 0.0, dt, 0.25)
        if new is not None and precisa_rostos and new.frame is not None:
            self._crop_faces(new.frame)
        self._update_parachutes(dt)
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
        animal = int(round(self.params.animal))
        for s, slot in enumerate(self._slots):
            pp = by_slot.get(s)
            alvo = alvo_e = alvo_d = 0.0
            if pp is not None:
                if slot.id != pp.id:  # pessoa nova neste slot: personagem recomeça
                    self._slots[s] = slot = _Slot(id=pp.id, critter=Critter(pp.id))
                    self._faces.forget(s)
                alvo = 1.0 if pp.active else 0.0
                alvo_e, alvo_d = pp.wrist_speed_l, pp.wrist_speed_r
                slot.altura = float((pp.box[3] - pp.box[1]) / C.CAMERA_ALTURA)
                slot.pontos = np.column_stack([pp.points[:, 0] / C.CAMERA_LARGURA, pp.points[:, 1] / C.CAMERA_ALTURA,
                                               pp.points[:, 2]]).astype(np.float32)
            slot.presenca = aproximar(slot.presenca, alvo, dt, 0.12 if alvo > slot.presenca else 0.45)
            slot.energia_e = aproximar(slot.energia_e, alvo_e, dt, 0.06 if alvo_e > slot.energia_e else 0.5)
            slot.energia_d = aproximar(slot.energia_d, alvo_d, dt, 0.06 if alvo_d > slot.energia_d else 0.5)
            # O ``flash`` é o da batida anterior, como no original (que atualiza
            # os slots antes da música).
            slot.critter.update(slot.pontos, slot.altura, slot.presenca, dt, self._flash, animal)

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

    def _crop_faces(self, frame: np.ndarray) -> None:
        for s, slot in enumerate(self._slots):
            cr = slot.critter
            if slot.presenca < 0.05 or cr.cabeca_valida < 0.05:
                self._faces.forget(s)
                continue
            self._faces.crop(frame, s, slot.pontos, cr.cabeca_centro, cr.cabeca_raio, cr.cabeca_dir)

    def _update_parachutes(self, dt: float) -> None:
        if self.effect != "paraquedas" and self._fade["paraquedas"] < 0.01:
            self._rostos = []
            self._parachutes.clear()
            return
        rostos = []
        for s, slot in enumerate(self._slots):
            cr = slot.critter
            if slot.presenca < 0.05 or cr.cabeca_valida < 0.05 or not self._faces.ready(s):
                continue
            rosto = self._faces.face(s, slot.presenca * cr.cabeca_valida)
            if rosto is not None:
                rostos.append(rosto)
        self._rostos = rostos
        self._parachutes.update(dt, rostos, self.params.intervalo_aviao)

    def _update_center(self, dt: float) -> None:
        """Centro da pessoa principal (raios do fundo dos Ecos)."""
        best = 0.0
        for slot in self._slots:
            cr = slot.critter
            if slot.presenca > best and cr.cabeca_valida > 0.3:
                best = slot.presenca
                self._centro += (cr.cabeca_centro - self._centro) * (1.0 - math.exp(-dt / 0.3))

    def _draw(self) -> np.ndarray:
        w, h = self.size
        pr = self.prog
        p = self.params
        pontos = np.zeros((C.MAX_PESSOAS * NUM_KEYPOINTS, 3), np.float32)
        pessoas = np.zeros((C.MAX_PESSOAS, 4), np.float32)
        cabecas = np.zeros((C.MAX_PESSOAS, 4), np.float32)
        corpos = np.zeros((C.MAX_PESSOAS, 4), np.float32)
        extras = np.zeros((C.MAX_PESSOAS, 4), np.float32)
        rig1 = np.zeros((C.MAX_PESSOAS, 4), np.float32)
        rig2 = np.zeros((C.MAX_PESSOAS, 4), np.float32)
        rig3 = np.zeros((C.MAX_PESSOAS, 4), np.float32)
        bracos = np.zeros((C.MAX_PESSOAS, 4), np.float32)
        rabo_pontos = np.zeros((C.MAX_PESSOAS * NUM_ELOS_RABO, 2), np.float32)
        # Personagens bem menores que o maior em cena são detecções falsas
        # (pôster, reflexo): somem.
        maior_u = max((sl.critter.rig_u for sl in self._slots if sl.critter.rig_valido > 0.5), default=0.0)
        for s, slot in enumerate(self._slots):
            cr = slot.critter
            pessoas[s] = (slot.presenca, slot.energia_e, slot.energia_d, slot.altura)
            pontos[s * NUM_KEYPOINTS:(s + 1) * NUM_KEYPOINTS] = slot.pontos
            cabecas[s] = (cr.cabeca_centro[0], cr.cabeca_centro[1], cr.cabeca_raio, cr.cabeca_valida)
            corpos[s] = (cr.cabeca_dir[0], cr.cabeca_dir[1], cr.escala, cr.orelha_angulo)
            extras[s] = (cr.pupila[0], cr.pupila[1], cr.piscar, cr.rabo_angulo)
            relativo = smoothstep(0.45, 0.60, cr.rig_u / maior_u) if maior_u > 0 else 1.0
            rig1[s] = (cr.rig_raiz[0], cr.rig_raiz[1], cr.rig_u, cr.rig_valido * relativo)
            rig2[s] = (cr.rig_corpo_angulo, cr.cabeca_inclinacao,
                       math.atan2(cr.perna[0][1], cr.perna[0][0]), math.atan2(cr.perna[1][1], cr.perna[1][0]))
            bracos[s] = (cr.mao[0][0], cr.mao[0][1], cr.mao[1][0], cr.mao[1][1])
            rig3[s] = (cr.rig_esticar, cr.cabeca_deslocamento[0], cr.cabeca_deslocamento[1], 0.0)
            for k in range(NUM_ELOS_RABO):
                rabo_pontos[s * NUM_ELOS_RABO + k] = cr.rabo[k] / (C.CAMERA_LARGURA, C.CAMERA_ALTURA)
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
        put("efeitoBichinho", self._fade["bichinho"])
        put("efeitoFundo", self._fade["fundo"])
        put("animal", float(round(p.animal)))
        put("cabeca", cabecas)
        put("corpo", corpos)
        put("extra", extras)
        put("rig1", rig1)
        put("rig2", rig2)
        put("rig3", rig3)
        put("bracos", bracos)
        put("raboPontos", rabo_pontos)
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
        img = np.frombuffer(data, np.uint8).reshape(h, w, 4).copy()
        # Os paraquedistas são desenhados com o OpenCV por cima do shader, como
        # no original (lá o OF desenha depois do quadTela).
        if self._fade["paraquedas"] > 0.01:
            self._parachutes.draw(img, self._rostos, self._fade["paraquedas"])
        return img
