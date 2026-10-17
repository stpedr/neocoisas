"""Salto de paraquedas — tradução de ``Paraquedistas.cpp`` do visual_frames.

Um avião de desenho cruza o céu e solta paraquedistas que têm o **rosto** das
pessoas na frente da câmera (recortado ao vivo pelo ``faces.py``). Queda livre,
o paraquedas abre com um tranco, descem balançando, pousam no morro, acenam e
somem.

O original desenha com as primitivas imediatas do openFrameworks sobre o
resultado do shader. Aqui a cena é desenhada com o OpenCV no quadro RGBA que
sai do FBO: as mesmas formas, nas mesmas coordenadas (``uv`` da tela × tamanho
relativo a 720p), com antisserrilhado e um oitavo de pixel de precisão.

Diferença consciente: no original a opacidade do fade multiplica a cor de cada
primitiva, então durante os 0,25 s de transição o céu escurece junto com o que
está atrás. Aqui a cena é montada opaca e entra por um *crossfade* limpo — ao
fim da transição as duas são idênticas.
"""

from __future__ import annotations

import math
import random
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

import cv2
import numpy as np

from .faces import LADO as LADO_ROSTO
from .dynamics import aproximar

ALTURA_AVIAO = 0.14  # uv da tela
CHAO = 0.90  # onde os pés tocam o morro
PES = 0.105  # dos pés ao centro do corpo, uv (a 720p)
TEMPO_QUEDA_LIVRE = 1.1  # s até abrir o paraquedas
DESCIDA = 0.075  # uv/s com o paraquedas aberto
TEMPO_NO_CHAO = 0.35  # s no chão antes de começar a sumir
MAX_SALTADORES = 14
CONTORNO = (28, 24, 44)
RAIO_TEXTURA = 0.43  # raio normalizado do rosto dentro do recorte 256x256

CORES = ((255, 92, 92), (255, 168, 40), (255, 214, 50), (70, 200, 120),
         (60, 160, 255), (160, 100, 255), (255, 110, 190))

_SH = 3  # bits de subpixel do OpenCV (1/8 de pixel)
_S = 1 << _SH


def _i(v: float) -> int:
    return int(round(v * _S))


def _pt(p: Iterable[float]) -> tuple[int, int]:
    x, y = p
    return _i(x), _i(y)


def _girar(p: np.ndarray, angulo: float) -> np.ndarray:
    c, s = math.cos(angulo), math.sin(angulo)
    return np.array([c * p[0] - s * p[1], s * p[0] + c * p[1]], np.float32)


class Fase(Enum):
    QUEDA_LIVRE = 0
    PARAQUEDAS = 1
    NO_CHAO = 2


@dataclass
class Saltador:
    fase: Fase = Fase.QUEDA_LIVRE
    posicao: np.ndarray = field(default_factory=lambda: np.zeros(2, np.float32))  # centro do corpo, uv
    velocidade: np.ndarray = field(default_factory=lambda: np.zeros(2, np.float32))  # uv/s
    tempo_na_fase: float = 0.0
    abertura: float = 0.0  # velame: 0 fechado .. 1 aberto (com "tranco")
    velocidade_abertura: float = 0.0
    semente: float = 0.0
    rosto: int = -1  # slot da pessoa cujo rosto ele usa
    macacao: tuple = CORES[0]
    velame1: tuple = CORES[1]
    velame2: tuple = (255, 250, 240)
    sumir: float = 0.0


@dataclass
class _Aviao:
    ativo: bool = False
    x: float = 0.0
    direcao: float = 1.0
    helice: float = 0.0
    fila: list = field(default_factory=list)
    pontos_de_salto: list = field(default_factory=list)


@dataclass
class _Nuvem:
    posicao: np.ndarray
    escala: float
    velocidade: float
    camada: float  # 0 = longe, 1 = perto


class _Tela:
    """Alvo de desenho com as primitivas que o openFrameworks oferecia.

    Aceita buffer RGB ou RGBA: as cores são dadas em RGB e completadas com
    alfa opaco quando o buffer tem 4 canais (senão o OpenCV zeraria o alfa).
    """

    def __init__(self, img: np.ndarray):
        self.img = img
        self.h, self.w = img.shape[:2]
        self._rgba = img.ndim == 3 and img.shape[2] == 4

    def _cor(self, cor) -> tuple:
        return (*cor, 255) if self._rgba and len(cor) == 3 else tuple(cor)

    @contextmanager
    def alpha(self, a: float, bbox: tuple[int, int, int, int]):
        """Tudo desenhado dentro do bloco entra com opacidade ``a``.

        ``bbox`` em pixels (x0, y0, x1, y1) limita a cópia ao que o bloco pode
        pintar — o bloco pode desenhar fora, mas só o recorte recebe o fade.
        """
        x0, y0 = max(0, bbox[0]), max(0, bbox[1])
        x1, y1 = min(self.w, bbox[2]), min(self.h, bbox[3])
        if a >= 0.999 or x1 <= x0 or y1 <= y0:
            yield
            return
        base = self.img[y0:y1, x0:x1].copy()
        yield
        roi = self.img[y0:y1, x0:x1]
        cv2.addWeighted(roi, a, base, 1.0 - a, 0.0, dst=roi)

    def circulo(self, c, r: float, cor) -> None:
        cv2.circle(self.img, _pt(c), max(_i(r), 1), self._cor(cor), -1, cv2.LINE_AA, _SH)

    def elipse_d(self, c, largura: float, altura: float, cor, angulo: float = 0.0) -> None:
        """Elipse por **diâmetros**, como ``ofDrawEllipse``."""
        cv2.ellipse(self.img, _pt(c), (max(_i(largura / 2), 1), max(_i(altura / 2), 1)),
                    angulo, 0, 360, self._cor(cor), -1, cv2.LINE_AA, _SH)

    def elipse_contornada(self, c, rx: float, ry: float, cor, contorno: float) -> None:
        """O helper ``elipse()`` do original: contorno escuro + preenchimento."""
        self.elipse_d(c, 2 * (rx + contorno), 2 * (ry + contorno), CONTORNO)
        self.elipse_d(c, 2 * rx, 2 * ry, cor)

    def retangulo(self, x: float, y: float, w: float, h: float, cor) -> None:
        x0, x1 = (x, x + w) if w >= 0 else (x + w, x)
        y0, y1 = (y, y + h) if h >= 0 else (y + h, y)
        cv2.rectangle(self.img, (_i(x0), _i(y0)), (_i(x1), _i(y1)), self._cor(cor), -1, cv2.LINE_AA, _SH)

    def retangulo_redondo(self, x: float, y: float, w: float, h: float, r: float, cor) -> None:
        r = min(r, abs(w) / 2, abs(h) / 2)
        self.retangulo(x + r, y, w - 2 * r, h, cor)
        self.retangulo(x, y + r, w, h - 2 * r, cor)
        for cx in (x + r, x + w - r):
            for cy in (y + r, y + h - r):
                self.circulo((cx, cy), r, cor)

    def poligono(self, pontos, cor) -> None:
        pts = np.array([[_pt(p) for p in pontos]], np.int32)
        cv2.fillPoly(self.img, pts, self._cor(cor), cv2.LINE_AA, _SH)

    def capsula(self, a, b, raio: float, cor, contorno: float) -> None:
        """Peça de desenho animado: contorno escuro + preenchimento. Retângulo +
        círculos porque o perfil core do OpenGL não tinha linha grossa."""
        a = np.asarray(a, np.float32)
        b = np.asarray(b, np.float32)
        d = b - a
        comprimento = float(np.hypot(d[0], d[1]))
        angulo = math.atan2(float(d[1]), float(d[0]))
        for camada in (0, 1):
            r = raio + contorno if camada == 0 else raio
            c = CONTORNO if camada == 0 else cor
            self.circulo(a, r, c)
            self.circulo(b, r, c)
            if comprimento > 0.5:
                co, si = math.cos(angulo), math.sin(angulo)
                # retângulo local (0,-r)..(comprimento,+r), girado e transladado
                cantos = [(0.0, -r), (comprimento, -r), (comprimento, r), (0.0, r)]
                self.poligono([(a[0] + x * co - y * si, a[1] + x * si + y * co) for x, y in cantos], c)

    def disco_com_rosto(self, centro, raio: float, rosto: np.ndarray) -> None:
        """Rosto recortado desenhado num disco (o centro da textura é o centro
        do rosto; a borda do disco amostra o raio normalizado 0,43)."""
        r = int(round(raio))
        if r < 2:
            return
        meio = LADO_ROSTO / 2.0
        janela = RAIO_TEXTURA * LADO_ROSTO
        a, b = int(round(meio - janela)), int(round(meio + janela))
        recorte = rosto[max(0, a):min(LADO_ROSTO, b), max(0, a):min(LADO_ROSTO, b)]
        if recorte.size == 0:
            return
        disco = cv2.resize(recorte, (2 * r, 2 * r), interpolation=cv2.INTER_LINEAR)
        mascara = np.zeros((2 * r, 2 * r), np.uint8)
        cv2.circle(mascara, (r, r), r, 255, -1, cv2.LINE_AA)
        cx, cy = int(round(centro[0])), int(round(centro[1]))
        x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r
        sx0, sy0 = max(0, -x0), max(0, -y0)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.w, x1), min(self.h, y1)
        if x1 <= x0 or y1 <= y0:
            return
        src = disco[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
        m = mascara[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
        roi = self.img[y0:y1, x0:x1]
        np.copyto(roi[..., :3] if self._rgba else roi, src, where=m[..., None] > 127)


class Parachutists:
    def __init__(self, rng: Optional[random.Random] = None):
        self._rng = rng or random.Random()
        self.saltadores: list[Saltador] = []
        self.nuvens: list[_Nuvem] = []
        self.aviao = _Aviao()
        self._ultimo_salto: dict[int, float] = {}
        self._ultima_passagem = -100.0
        self.relogio = 0.0
        self._cena: Optional[np.ndarray] = None
        self._ceu_cache: Optional[np.ndarray] = None

    def clear(self) -> None:
        self.saltadores.clear()
        self.aviao = _Aviao()
        self._ultimo_salto.clear()
        self._ultima_passagem = -100.0

    def _cor(self) -> tuple:
        return CORES[int(self._rng.uniform(0.0, 7.0)) % 7]

    # ------------------------------------------------------------------ passo
    def update(self, dt: float, rostos: list, intervalo_aviao: float) -> None:
        # (o original também recebe o nível da música aqui, mas não usa)
        dt = min(dt, 1.0 / 20.0)
        self.relogio += dt

        # Nuvens em duas camadas (paralaxe), criadas uma vez.
        if not self.nuvens:
            for i in range(9):
                camada = 0.0 if i < 5 else 1.0
                y = self._rng.uniform(0.05, 0.45) if camada == 0 else self._rng.uniform(0.25, 0.7)
                self.nuvens.append(_Nuvem(
                    posicao=np.array([self._rng.uniform(-0.1, 1.1), y], np.float32),
                    escala=self._rng.uniform(0.6, 0.9) if camada == 0 else self._rng.uniform(1.0, 1.4),
                    velocidade=self._rng.uniform(0.006, 0.012) if camada == 0 else self._rng.uniform(0.015, 0.025),
                    camada=camada))
        for n in self.nuvens:
            n.posicao[0] -= n.velocidade * dt
            if n.posicao[0] < -0.25:
                n.posicao[0] = 1.25
                n.posicao[1] = self._rng.uniform(0.05, 0.45) if n.camada == 0 else self._rng.uniform(0.25, 0.7)

        # Avião: vem na hora em que aparece alguém com o rosto visível; depois,
        # a mesma pessoa só salta de novo após o intervalo. Sem ninguém, de vez
        # em quando saltam dois "convidados".
        if not self.aviao.ativo:
            prontos = []
            for r in rostos:
                # Só salta quem está olhando para a câmera (rosto bom no recorte).
                if r.presenca < 0.6 or r.imagem is None or not r.de_frente:
                    continue
                ultimo = self._ultimo_salto.get(r.slot)
                if ultimo is None or self.relogio - ultimo > intervalo_aviao:
                    prontos.append(r.slot)
            convidados = not rostos and self.relogio - self._ultima_passagem > intervalo_aviao * 1.5
            if prontos or convidados:
                av = self.aviao
                av.ativo = True
                av.direcao = 1.0 if self._rng.uniform(0.0, 1.0) < 0.5 else -1.0
                av.x = -0.2 if av.direcao > 0 else 1.2
                av.fila = list(prontos) if prontos else [-1, -1]
                for ident in prontos:
                    self._ultimo_salto[ident] = self.relogio
                self._ultima_passagem = self.relogio
                # Pontos de salto espalhados ao longo da passagem (o primeiro logo
                # depois que o avião entra na tela).
                av.pontos_de_salto = []
                n = len(av.fila)
                for i in range(n):
                    t = (i + 0.5) / n
                    x = 0.12 + 0.7 * t + self._rng.uniform(-0.03, 0.03)
                    av.pontos_de_salto.append(x if av.direcao > 0 else 1.0 - x)
        else:
            av = self.aviao
            av.x += av.direcao * 0.22 * dt
            av.helice += dt * 40.0
            while av.fila:
                alvo = av.pontos_de_salto[0]
                passou = av.x >= alvo if av.direcao > 0 else av.x <= alvo
                if not passou or len(self.saltadores) >= MAX_SALTADORES:
                    break
                self.saltadores.append(Saltador(
                    posicao=np.array([av.x - av.direcao * 0.03, ALTURA_AVIAO + 0.03], np.float32),
                    velocidade=np.array([av.direcao * 0.12, 0.05], np.float32),
                    semente=self._rng.uniform(0.0, 2 * math.pi),
                    rosto=av.fila[0], macacao=self._cor(), velame1=self._cor(), velame2=(255, 250, 240)))
                av.fila.pop(0)
                av.pontos_de_salto.pop(0)
            if av.x < -0.3 or av.x > 1.3:
                av.ativo = False

        for s in self.saltadores:
            s.tempo_na_fase += dt
            if s.fase is Fase.QUEDA_LIVRE:
                s.velocidade[1] = min(float(s.velocidade[1]) + 1.5 * dt, 0.45)
                s.velocidade[0] = aproximar(float(s.velocidade[0]), 0.0, dt, 0.6)
                if s.tempo_na_fase > TEMPO_QUEDA_LIVRE:
                    s.fase = Fase.PARAQUEDAS
                    s.tempo_na_fase = 0.0
                    s.velocidade[1] = 0.02  # tranco da abertura
            elif s.fase is Fase.PARAQUEDAS:
                # Velame abre com mola (passa um pouco e volta: "pop").
                s.velocidade_abertura += (90.0 * (1.0 - s.abertura) - 9.0 * s.velocidade_abertura) * dt
                s.abertura += s.velocidade_abertura * dt
                s.velocidade[1] = aproximar(float(s.velocidade[1]), DESCIDA, dt, 0.5)
                s.velocidade[0] = 0.03 * math.sin(self.relogio * 1.1 + s.semente)
                if float(s.posicao[1]) + PES >= CHAO:
                    s.fase = Fase.NO_CHAO
                    s.tempo_na_fase = 0.0
                    s.posicao[1] = CHAO - PES
                    s.velocidade[:] = 0.0
            else:
                s.abertura = aproximar(s.abertura, 0.0, dt, 0.35)
                # Ao pousar, um aceno rápido e já vai sumindo.
                if s.tempo_na_fase > TEMPO_NO_CHAO:
                    s.sumir = min(1.0, s.sumir + dt / 0.5)
            s.posicao += s.velocidade * dt
            s.posicao[0] = min(0.96, max(0.04, float(s.posicao[0])))
        self.saltadores = [s for s in self.saltadores if s.sumir < 1.0]

    # ---------------------------------------------------------------- desenho
    def draw(self, img: np.ndarray, rostos: list, opacidade: float) -> None:
        """Desenha a cena sobre ``img`` (RGB ou RGBA; o alfa não é tocado)."""
        if opacidade < 0.01:
            return
        h, w = img.shape[:2]
        # A cena é montada num buffer próprio, com os mesmos canais de ``img``:
        # assim a composição final é uma operação contígua só (em RGBA, mexer em
        # ``img[..., :3]`` seria uma view com passo 4, três vezes mais cara).
        if self._cena is None or self._cena.shape != img.shape:
            self._cena = np.empty_like(img)
        cena = self._cena
        # Não precisa semear com o que está atrás: o céu é opaco e cobre tudo.
        self._draw_scene(_Tela(cena), w, h, rostos)
        if opacidade >= 0.999:
            np.copyto(img, cena)
        else:
            cv2.addWeighted(cena, opacidade, img, 1.0 - opacidade, 0.0, dst=img)

    def _draw_scene(self, tela: _Tela, w: int, h: int, rostos: list) -> None:
        self._ceu(tela, w, h)
        # Todas as nuvens ficam atrás: nada pode cobrir os rostos.
        self._nuvens(tela, w, h, frente=False)
        self._nuvens(tela, w, h, frente=True)
        if self.aviao.ativo:
            self._aviao_(tela, w, h)
        self._chao(tela, w, h)
        # Quem está no chão por trás, quem está no ar na frente.
        for no_chao in (True, False):
            for s in self.saltadores:
                if (s.fase is Fase.NO_CHAO) == no_chao:
                    self._saltador(tela, s, w, h, rostos)

    def _ceu(self, tela: _Tela, w: int, h: int) -> None:
        """Degradê do céu e o sol. Não muda nunca, então vale um cache: era o
        item mais caro do desenho (3,4 ms de 11,9 ms)."""
        if self._ceu_cache is None or self._ceu_cache.shape != tela.img.shape:
            ceu = np.empty_like(tela.img)
            canais = ceu.shape[2]
            topo = np.array([0.27, 0.56, 0.93], np.float32) * 255.0
            baixo = np.array([0.70, 0.88, 1.00], np.float32) * 255.0
            t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
            degrade = (topo * (1.0 - t) + baixo * t).astype(np.uint8)
            ceu[..., :3] = degrade[:, None, :]
            if canais == 4:
                ceu[..., 3] = 255
            fundo = _Tela(ceu)
            # Sol com brilho.
            sol = (w * 0.86, h * 0.16)
            for i in (4, 3, 2, 1):
                r = h * (0.06 + 0.025 * i)
                bbox = (int(sol[0] - r) - 2, int(sol[1] - r) - 2, int(sol[0] + r) + 2, int(sol[1] + r) + 2)
                with fundo.alpha(30 / 255.0, bbox):
                    fundo.circulo(sol, r, (255, 240, 150))
            fundo.circulo(sol, h * 0.06, (255, 228, 90))
            self._ceu_cache = ceu
        np.copyto(tela.img, self._ceu_cache)

    def _nuvens(self, tela: _Tela, w: int, h: int, frente: bool) -> None:
        for n in self.nuvens:
            if (n.camada > 0.5) != frente:
                continue
            cx, cy = float(n.posicao[0]) * w, float(n.posicao[1]) * h
            r = h * 0.045 * n.escala
            a = (210.0 if frente else 235.0) / 255.0
            bbox = (int(cx - 4 * r), int(cy - 3 * r), int(cx + 4 * r), int(cy + 3 * r))
            with tela.alpha(a, bbox):
                branco = (255, 255, 255)
                tela.circulo((cx - 1.6 * r, cy + 0.3 * r), r * 0.9, branco)
                tela.circulo((cx - 0.5 * r, cy - 0.3 * r), r * 1.25, branco)
                tela.circulo((cx + 0.8 * r, cy - 0.1 * r), r * 1.1, branco)
                tela.circulo((cx + 1.8 * r, cy + 0.35 * r), r * 0.8, branco)
                tela.retangulo_redondo(cx - 2.4 * r, cy, 4.9 * r, 1.1 * r, r * 0.55, branco)

    def _chao(self, tela: _Tela, w: int, h: int) -> None:
        # Morro verde ondulado com uma faixa mais escura.
        for camada in (0, 1):
            base = h * (0.885 if camada == 0 else 0.93)
            cor = (110, 200, 90) if camada == 0 else (80, 165, 70)
            pontos = [(0.0, float(h))]
            for i in range(49):
                x = w * i / 48.0
                onda = math.sin(i * 0.35 + camada * 1.7) * h * 0.012
                pontos.append((x, base + onda))
            pontos.append((float(w), float(h)))
            tela.poligono(pontos, cor)

    def _aviao_(self, tela: _Tela, w: int, h: int) -> None:
        av = self.aviao
        s = h / 720.0
        tx = av.x * w
        ty = ALTURA_AVIAO * h + math.sin(self.relogio * 2.0) * 4 * s
        d = av.direcao

        def p(lx: float, ly: float) -> tuple[float, float]:
            return tx + d * lx, ty + ly

        def rect(lx: float, ly: float, lw: float, lh: float, cor) -> None:
            x0, x1 = tx + d * lx, tx + d * (lx + lw)
            tela.retangulo(min(x0, x1), ty + ly, abs(x1 - x0), lh, cor)

        # Asa de trás, fuselagem, janelas, cauda, asa da frente e hélice.
        tela.elipse_d(p(-10 * s, 8 * s), 128 * s, 34 * s, CONTORNO)
        tela.elipse_d(p(-10 * s, 8 * s), 120 * s, 26 * s, (200, 60, 60))
        tela.capsula(p(-110 * s, 0), p(95 * s, 0), 30 * s, (250, 250, 255), 3.5 * s)
        tela.poligono([p(-140 * s, -62 * s), p(-95 * s, -10 * s), p(-130 * s, 0)], CONTORNO)
        tela.poligono([p(-134 * s, -54 * s), p(-100 * s, -12 * s), p(-126 * s, -4 * s)], (220, 70, 70))
        rect(-110 * s, 6 * s, 205 * s, 8 * s, (220, 70, 70))
        for i in range(6):
            c = p((-60 + i * 26) * s, -8 * s)
            tela.circulo(c, 8 * s, CONTORNO)
            tela.circulo(c, 6 * s, (140, 210, 255))
        tela.elipse_d(p(5 * s, 22 * s), 120 * s, 22 * s, CONTORNO)
        tela.elipse_d(p(5 * s, 22 * s), 112 * s, 15 * s, (230, 80, 80))
        tela.circulo(p(126 * s, 0), 9 * s, CONTORNO)
        altura_helice = 70 * s * abs(math.sin(av.helice)) + 8 * s
        cx, cy = p(130 * s, 0)
        bbox = (int(cx - 8 * s), int(cy - altura_helice), int(cx + 8 * s), int(cy + altura_helice))
        with tela.alpha(180 / 255.0, bbox):
            tela.elipse_d((cx, cy), 8 * s, altura_helice, (80, 80, 90))

    def _saltador(self, tela: _Tela, sal: Saltador, w: int, h: int, rostos: list) -> None:
        s = h / 720.0
        corpo = np.array([float(sal.posicao[0]) * w, float(sal.posicao[1]) * h], np.float32)
        contorno = 3.0 * s
        pele = (255, 214, 180)

        # Pose e inclinação conforme a fase (em coordenadas locais, y para baixo).
        tempo = self.relogio + sal.semente
        if sal.fase is Fase.QUEDA_LIVRE:
            giro = 0.25 * math.sin(tempo * 5.0)
            bate = 6 * math.sin(tempo * 14.0)
            mao_e, mao_d = np.array([-58, -30 + bate]), np.array([58, -30 - bate])
            pe_e, pe_d = np.array([-34, 62 - bate]), np.array([34, 62 + bate])
        elif sal.fase is Fase.PARAQUEDAS:
            giro = 0.12 * math.sin(self.relogio * 1.1 + sal.semente)
            mao_e, mao_d = np.array([-34, -66]), np.array([34, -66])
            balanca = 8 * math.sin(tempo * 2.5)
            pe_e, pe_d = np.array([-14 + balanca, 66]), np.array([14 + balanca, 64])
        else:
            giro = 0.0
            aceno = math.sin(tempo * 9.0)
            mao_e, mao_d = np.array([-34, 22]), np.array([48 + 6 * aceno, -48 + 8 * aceno])
            pe_e, pe_d = np.array([-16, 70]), np.array([16, 70])

        def ponto(local) -> np.ndarray:
            return corpo + _girar(np.asarray(local, np.float32) * s, giro)

        alpha = 1.0 - sal.sumir
        raio_cabeca = 54 * s
        # Caixa generosa: velame (até -195-70) e pés (+70), mais o contorno.
        bbox = (int(corpo[0] - 160 * s), int(corpo[1] - 290 * s),
                int(corpo[0] + 170 * s), int(corpo[1] + 100 * s))
        with tela.alpha(alpha, bbox):
            # Velame com gomos listrados, borda recortada e cordas até os ombros.
            if sal.abertura > 0.03:
                ab = sal.abertura
                centro = ponto((0, -195))
                rx = 135 * s * ab
                ry = 70 * s * min(ab, 1.2)
                if sal.fase is Fase.NO_CHAO:
                    # Desinflando ao lado, no chão.
                    tela.elipse_d(corpo + np.array([70 * s, 60 * s]), rx * 1.6, ry * 0.5, sal.velame1)
                else:
                    GOMOS, PASSOS = 7, 6
                    # Contorno só da cúpula (meia-elipse um pouco maior por trás).
                    borda = [centro + _girar(np.array([math.cos(a) * (rx + contorno),
                                                       math.sin(a) * (ry + contorno)], np.float32), giro)
                             for a in (math.pi + math.pi * p / 32.0 for p in range(33))]
                    borda.append(centro + _girar(np.array([rx + contorno, contorno], np.float32), giro))
                    borda.append(centro + _girar(np.array([-rx - contorno, contorno], np.float32), giro))
                    tela.poligono(borda, CONTORNO)
                    for g in range(GOMOS):
                        gomo = [centro]
                        for pp in range(PASSOS + 1):
                            a = math.pi + math.pi * (g + pp / PASSOS) / GOMOS
                            gomo.append(centro + _girar(np.array([math.cos(a) * rx, math.sin(a) * ry], np.float32), giro))
                        tela.poligono(gomo, sal.velame1 if g % 2 == 0 else sal.velame2)
                    for lado in (-1.0, -0.4, 0.4, 1.0):
                        de = centro + _girar(np.array([lado * rx * 0.97, 2 * s], np.float32), giro)
                        ate = ponto((-26.0 if lado < 0 else 26.0, -36))
                        tela.capsula(de, ate, 1.0 * s, CONTORNO, 0.0)

            # Corpo: pernas, macacão, braços, luvas e botas.
            bota = (60, 52, 70)
            tela.capsula(ponto((-12, 20)), ponto(pe_e), 12 * s, sal.macacao, contorno)
            tela.capsula(ponto((12, 20)), ponto(pe_d), 12 * s, sal.macacao, contorno)
            tela.elipse_contornada(ponto(pe_e + np.array([-4, 4])), 15 * s, 9 * s, bota, contorno)
            tela.elipse_contornada(ponto(pe_d + np.array([4, 4])), 15 * s, 9 * s, bota, contorno)
            tela.capsula(ponto((0, -22)), ponto((0, 22)), 25 * s, sal.macacao, contorno)
            tela.capsula(ponto((-18, -28)), ponto(mao_e), 11 * s, sal.macacao, contorno)
            tela.capsula(ponto((18, -28)), ponto(mao_d), 11 * s, sal.macacao, contorno)
            tela.elipse_contornada(ponto(mao_e), 11 * s, 11 * s, (250, 250, 250), contorno)
            tela.elipse_contornada(ponto(mao_d), 11 * s, 11 * s, (250, 250, 250), contorno)
            # Faixa do equipamento no peito.
            faixa = ponto((-22, -6))
            with tela.alpha(0.85, (int(faixa[0]) - 1, int(faixa[1]) - 1,
                                   int(faixa[0] + 44 * s) + 2, int(faixa[1] + 7 * s) + 2)):
                tela.retangulo(float(faixa[0]), float(faixa[1]), 44 * s, 7 * s, CONTORNO)

            # Cabeça: o rosto real da pessoa, recortado em círculo do quadro da câmera.
            cabeca = ponto((0, -72))
            tela.circulo(cabeca, raio_cabeca + 5 * s, CONTORNO)
            tela.circulo(cabeca, raio_cabeca + 2.5 * s, (255, 255, 255))

            rosto = None
            for r in rostos:
                if r.imagem is not None and r.presenca > 0.3 and (r.slot == sal.rosto or rosto is None):
                    rosto = r
                    if r.slot == sal.rosto:
                        break
            if rosto is not None:
                tela.disco_com_rosto(cabeca, raio_cabeca, rosto.imagem)
            else:
                # Ninguém na câmera: carinha de desenho.
                tela.circulo(cabeca, raio_cabeca, pele)
                tela.circulo(cabeca + np.array([-13, -6]) * s, 5 * s, CONTORNO)
                tela.circulo(cabeca + np.array([13, -6]) * s, 5 * s, CONTORNO)
                tela.retangulo_redondo(float(cabeca[0]) - 12 * s, float(cabeca[1]) + 12 * s,
                                       24 * s, 5 * s, 2.5 * s, CONTORNO)
            # Capacete: aro colorido em volta do rosto.
            for i in range(28):
                a0 = math.pi * 1.05 + math.pi * 0.9 * i / 28.0
                p = cabeca + np.array([math.cos(a0), math.sin(a0)], np.float32) * (raio_cabeca + 1.5 * s)
                tela.circulo(p, 5.5 * s, sal.macacao)
