"""Bichinho espelho — tradução de ``atualizarBichinho()`` e ``atualizarRig()``
do ``ofApp.cpp`` do visual_frames.

A pessoa vira um personagem chibi (gato, dinossauro ou coelho) desenhado pelo
shader. Da pessoa só vêm **posição, escala e direções** dos membros
(*retargeting*, como no Animated Drawings da Meta), nunca os comprimentos: as
proporções são fixas de desenho (cabeça do tamanho do corpo, membros curtos).

O movimento não é média exponencial: cada parte segue o seu alvo com dinâmica
de segunda ordem (``dynamics.SecondOrder``), então tem massa, passa um
pouquinho do ponto e se acomoda. A cabeça é mais "mole" que o corpo (atrasa e
balança), o corpo inclina para o lado em que anda, as orelhas e o rabo são
molas amortecidas e o rabo também é uma corrente de Verlet (spring bone).
"""

from __future__ import annotations

import math
import random

import numpy as np

from . import config as C
from .dynamics import SecondOrder, aproximar, normalizar, smoothstep
from .tracker import (COTOVELO_D, COTOVELO_E, JOELHO_D, JOELHO_E, NARIZ, OLHO_D, OLHO_E, OMBRO_D,
                      OMBRO_E, ORELHA_D, ORELHA_E, PULSO_D, PULSO_E, QUADRIL_D, QUADRIL_E,
                      TORNOZELO_D, TORNOZELO_E)

NUM_ELOS_RABO = 8  # mesmo ``#define`` do shader
DURACAO_PISCAR = 0.18
GATO, DINOSSAURO, COELHO = 0, 1, 2

L, A = float(C.CAMERA_LARGURA), float(C.CAMERA_ALTURA)


def _v(x: float, y: float) -> np.ndarray:
    return np.array([x, y], np.float32)


class Critter:
    """Estado do personagem de um slot. Um por pessoa, vive enquanto o id vive."""

    def __init__(self, ident: int = 0, rng: random.Random | None = None):
        self.id = ident
        self._rng = rng or random.Random()

        # Cabeça suavizada e encolhimento ao agachar.
        self.cabeca_iniciada = False
        self.cabeca_centro = _v(0.5, 0.5)  # uv
        self.cabeca_raio = 0.05  # fração da altura da tela
        self.cabeca_dir = _v(1.0, 0.0)  # eixo dos olhos (aponta para a direita da tela)
        self.cabeca_valida = 0.0
        self.altura_ref = 0.0  # maior altura vista (pessoa em pé)
        self.escala = 1.0

        # Física e animação do rosto.
        self.centro_anterior = _v(0.0, 0.0)
        self.tem_centro_anterior = False
        self.orelha_angulo = 0.0
        self.orelha_velocidade = 0.0
        self.pupila = _v(0.0, 0.0)
        self.piscar = 0.0
        self.relogio_piscar = 0.0
        self.proximo_piscar = 0.0
        self.rabo_angulo = 0.0
        self.rabo_velocidade = 0.0
        self.relogio_rabo = 0.0

        # Rig chibi (proporções fixas; só ângulos vêm da pessoa).
        self.rig_iniciado = False
        self.rig_raiz = _v(0.5, 0.5)  # centro do corpo, uv
        self.rig_u = 0.0  # unidade do personagem, fração da altura
        self.rig_valido = 0.0
        self.rig_corpo_angulo = 0.0
        self.rig_esticar = 1.0
        self.alvo_raiz = _v(0.5, 0.5)
        self.alvo_u = 0.0
        self.cabeca_deslocamento = _v(0.0, -0.98)  # em relação à raiz, em U
        self.cabeca_inclinacao = 0.0
        self.ombro_e_a_esquerda = 0.5  # 1 = keypoint OMBRO_E aparece à esquerda da tela
        self.mao = [_v(-0.17, 0.49), _v(0.17, 0.49)]  # em U, a partir do ombro
        self.perna = [_v(-0.15, 0.99), _v(0.15, 0.99)]

        # Dinâmicas de segunda ordem (f Hz, amortecimento, resposta inicial):
        # a "personalidade" de cada parte.
        self.din_u = SecondOrder(1.2, 1.0, 0.0)
        self.din_raiz = SecondOrder(3.2, 0.85, 0.0, _v(0.0, 0.0))
        self.din_cabeca = SecondOrder(2.4, 0.45, 0.0, _v(0.0, 0.0))  # mais mole: atrasa e balança
        self.din_inclinacao = SecondOrder(2.2, 0.5, 0.0)
        self.din_corpo = SecondOrder(1.8, 0.55, 0.0)
        self.din_esticar = SecondOrder(4.0, 0.35, 0.0, 1.0)  # squash que quica
        self.din_mao = [SecondOrder(3.0, 0.6, 1.1, _v(-0.17, 0.49)), SecondOrder(3.0, 0.6, 1.1, _v(0.17, 0.49))]
        self.din_perna = [SecondOrder(3.0, 0.7, 0.0, _v(-0.15, 0.99)), SecondOrder(3.0, 0.7, 0.0, _v(0.15, 0.99))]

        # Rabo (corrente de Verlet), em pixels da câmera.
        self.rabo_iniciado = False
        self.rabo = [_v(0.0, 0.0) for _ in range(NUM_ELOS_RABO)]
        self.rabo_anterior = [_v(0.0, 0.0) for _ in range(NUM_ELOS_RABO)]

    # ------------------------------------------------------------------ cabeça
    def update(self, pontos: np.ndarray, altura_corpo: float, presenca: float,
               dt: float, flash: float, animal: int) -> None:
        """``pontos``: (17, 3) em uv + confiança, como o shader recebe."""
        def ponto(k: int) -> np.ndarray:
            return _v(float(pontos[k, 0]) * L, float(pontos[k, 1]) * A)

        def conf(k: int) -> float:
            return float(pontos[k, 2])

        # Cabeça: média ponderada de nariz, olhos e orelhas.
        soma = _v(0.0, 0.0)
        peso = 0.0
        for k in range(NARIZ, ORELHA_D + 1):
            soma = soma + ponto(k) * conf(k)
            peso += conf(k)
        tem_cabeca = peso > 0.8

        # Eixo dos olhos (ou das orelhas) dá a inclinação; vira sempre para a direita da tela.
        direcao = self.cabeca_dir
        raio_px = self.cabeca_raio * A
        if conf(OLHO_E) > 0.3 and conf(OLHO_D) > 0.3:
            eixo = ponto(OLHO_D) - ponto(OLHO_E)
            comp = float(np.hypot(eixo[0], eixo[1]))
            if comp > 2.0:
                direcao = eixo / comp
            raio_px = 1.3 * comp
        if conf(ORELHA_E) > 0.3 and conf(ORELHA_D) > 0.3:
            d = ponto(ORELHA_D) - ponto(ORELHA_E)
            raio_px = 0.55 * float(np.hypot(d[0], d[1]))
        if direcao[0] < 0:
            direcao = -direcao
        raio_px = max(raio_px, 0.04 * altura_corpo * A)

        if tem_cabeca:
            centro = soma / peso
            # A média fica abaixo do centro do crânio (o nariz puxa para baixo).
            centro = centro - _v(direcao[1], -direcao[0]) * raio_px * 0.10
            centro_uv = _v(centro[0] / L, centro[1] / A)
            if not self.cabeca_iniciada:
                self.cabeca_iniciada = True
                self.cabeca_centro = centro_uv
                self.cabeca_raio = raio_px / A
                self.cabeca_dir = direcao
            else:
                self.cabeca_centro = self.cabeca_centro + (centro_uv - self.cabeca_centro) * (1.0 - math.exp(-dt / 0.04))
                self.cabeca_raio = aproximar(self.cabeca_raio, raio_px / A, dt, 0.15)
                suave = self.cabeca_dir + (direcao - self.cabeca_dir) * (1.0 - math.exp(-dt / 0.08))
                self.cabeca_dir = normalizar(suave, direcao)
        self.cabeca_valida = aproximar(self.cabeca_valida, presenca if tem_cabeca else 0.0, dt, 0.15)

        # Agachar: a altura da caixa cai em relação à maior vista (a pessoa em pé).
        self.altura_ref = max(altura_corpo, self.altura_ref * math.exp(-dt / 30.0))
        razao = altura_corpo / self.altura_ref if self.altura_ref > 0 else 1.0
        self.escala = aproximar(self.escala, 0.25 + 0.75 * smoothstep(0.55, 0.90, razao), dt, 0.15)

        # Velocidade da cabeça (px da câmera/s) move as molas e as pupilas.
        centro_px = _v(self.cabeca_centro[0] * L, self.cabeca_centro[1] * A)
        velocidade = _v(0.0, 0.0)
        if self.tem_centro_anterior and dt > 0:
            velocidade = (centro_px - self.centro_anterior) / dt
        self.centro_anterior = centro_px
        self.tem_centro_anterior = tem_cabeca

        # Orelhas: mola amortecida (oscila um pouco e volta), empurrada pelo
        # movimento lateral da cabeça e por um "pulo" em cada batida da música.
        passo = min(dt, 1.0 / 30.0)

        def mola(angulo: float, vel: float, alvo: float, rigidez: float, amortecimento: float):
            vel += (rigidez * (alvo - angulo) - amortecimento * vel) * passo
            angulo += vel * passo
            return min(0.9, max(-0.9, angulo)), vel

        alvo_orelha = min(0.5, max(-0.5, -float(velocidade[0]) * 0.0012))
        if flash > 0.95:
            self.orelha_velocidade += 2.5
        self.orelha_angulo, self.orelha_velocidade = mola(self.orelha_angulo, self.orelha_velocidade,
                                                          alvo_orelha, 70.0, 6.0)

        # Pupilas "googly": ficam para trás do movimento e voltam devagar.
        alvo_pupila = -velocidade * 0.0015
        comp = float(np.hypot(alvo_pupila[0], alvo_pupila[1]))
        if comp > 0.6:
            alvo_pupila = alvo_pupila / comp * 0.6
        self.pupila = self.pupila + (alvo_pupila - self.pupila) * (1.0 - math.exp(-dt / 0.10))

        # Piscar a cada 2,5–5,5 s, durando 0,18 s.
        self.relogio_piscar += dt
        if self.proximo_piscar <= 0:
            self.proximo_piscar = self._rng.uniform(2.5, 5.5)
        if self.relogio_piscar > self.proximo_piscar:
            t = self.relogio_piscar - self.proximo_piscar
            self.piscar = math.sin(math.pi * t / DURACAO_PISCAR) if t < DURACAO_PISCAR else 0.0
            if t >= DURACAO_PISCAR:
                self.relogio_piscar = 0.0
                self.proximo_piscar = self._rng.uniform(2.5, 5.5)

        # Rabo: balança sozinho e chicoteia com o movimento do quadril.
        self.relogio_rabo += dt
        alvo_rabo = (min(0.6, max(-0.6, -float(velocidade[0]) * 0.0015))
                     + 0.25 * math.sin(self.relogio_rabo * 2.2 + self.id))
        self.rabo_angulo, self.rabo_velocidade = mola(self.rabo_angulo, self.rabo_velocidade, alvo_rabo, 25.0, 4.0)

        self._update_rig(pontos, presenca, dt, animal)

    # --------------------------------------------------------------------- rig
    def _update_rig(self, pontos: np.ndarray, presenca: float, dt: float, animal: int) -> None:
        dt = min(dt, 1.0 / 20.0)  # quadro travado não pode explodir as molas

        def ponto(k: int) -> np.ndarray:
            return _v(float(pontos[k, 0]) * L, float(pontos[k, 1]) * A)

        def visivel(k: int) -> bool:
            return float(pontos[k, 2]) > 0.45

        tem_ombros = visivel(OMBRO_E) and visivel(OMBRO_D)
        tem_quadril = visivel(QUADRIL_E) and visivel(QUADRIL_D)

        # ---- Alvos de posição e escala (só dos ombros; sem ombros, segura) ----
        if tem_ombros:
            d = ponto(OMBRO_E) - ponto(OMBRO_D)
            largura = float(np.hypot(d[0], d[1]))
            # O boneco inteiro tem ~2,6 U de altura; limita para caber na tela.
            self.alvo_u = min(largura * 1.05, 0.30 * A) / A
            raiz_px = 0.5 * (ponto(OMBRO_E) + ponto(OMBRO_D)) + _v(0.0, largura * 0.35)
            # Mantém o boneco inteiro na tela, mesmo com a criança na borda ou sentada.
            u_px = self.alvo_u * A
            raiz_px[0] = min(L - 0.9 * u_px, max(0.9 * u_px, float(raiz_px[0])))
            raiz_px[1] = min(A - 0.95 * u_px, max(1.75 * u_px, float(raiz_px[1])))
            self.alvo_raiz = _v(raiz_px[0] / L, raiz_px[1] / A)
            if not self.rig_iniciado:
                self.rig_iniciado = True
                self.din_u.reset(self.alvo_u)
                self.din_raiz.reset(self.alvo_raiz)
                self.din_cabeca.reset(self.alvo_raiz - _v(0.0, 0.98 * self.alvo_u))
                self.rabo_iniciado = False
        if not self.rig_iniciado:
            self.rig_valido = aproximar(self.rig_valido, 0.0, dt, 0.2)
            return
        valido = tem_ombros or self.cabeca_valida > 0.3
        self.rig_valido = aproximar(self.rig_valido, presenca if valido else 0.0, dt, 0.15 if valido else 0.4)

        # Escala: lenta e sem balanço. Raiz: rápida, quase sem passar do ponto.
        self.rig_u = float(self.din_u.update(dt, self.alvo_u))
        self.rig_raiz = np.array(self.din_raiz.update(dt, self.alvo_raiz), np.float32)
        u_px = max(self.rig_u * A, 1.0)
        velocidade_raiz = self.din_raiz.velocity * _v(L, A) / u_px  # U/s

        # Squash & stretch pela velocidade vertical (y da tela desce).
        alvo_esticar = min(1.16, max(0.86, 1.0 - float(velocidade_raiz[1]) * 0.06))
        self.rig_esticar = float(self.din_esticar.update(dt, alvo_esticar))

        # Corpo: inclinação real (quadril -> ombros) + inclina para o lado em que anda.
        alvo_corpo = 0.0
        if tem_ombros and tem_quadril:
            v = 0.5 * (ponto(OMBRO_E) + ponto(OMBRO_D)) - 0.5 * (ponto(QUADRIL_E) + ponto(QUADRIL_D))
            alvo_corpo = min(0.3, max(-0.3, math.atan2(float(v[0]), -float(v[1]))))
        alvo_corpo += min(0.22, max(-0.22, float(velocidade_raiz[0]) * 0.07))
        self.rig_corpo_angulo = float(self.din_corpo.update(dt, alvo_corpo))
        b = self.rig_corpo_angulo
        direita = _v(math.cos(b), math.sin(b))
        cima = _v(math.sin(b), -math.cos(b))

        # Cabeça: segue o ponto acima do corpo com uma mola mais mole, então
        # atrasa nos movimentos e balança um pouco antes de parar.
        raiz_px = self.rig_raiz * _v(L, A)
        alvo_cabeca = (raiz_px + cima * 0.98 * u_px) / _v(L, A)
        cabeca_px = np.array(self.din_cabeca.update(dt, alvo_cabeca), np.float32) * _v(L, A)
        deslocamento = (cabeca_px - raiz_px) / u_px
        repouso = cima * 0.98
        fora = deslocamento - repouso
        if float(np.hypot(fora[0], fora[1])) > 0.22:
            deslocamento = repouso + normalizar(fora) * 0.22  # não descola do pescoço
        self.cabeca_deslocamento = deslocamento
        alvo_inclinacao = min(0.5, max(-0.5, math.atan2(float(self.cabeca_dir[1]), float(self.cabeca_dir[0]))))
        self.cabeca_inclinacao = float(self.din_inclinacao.update(dt, alvo_inclinacao))

        # ---- Braços e pernas ----
        # Qual ombro está à esquerda da TELA, decidido pela geometria com histerese.
        # (Não dá para supor pelo espelhamento: o modelo vê a imagem já espelhada e
        # rotula esquerda/direita pela aparência, o que inverte os lados.)
        if tem_ombros:
            alvo = 1.0 if float(ponto(OMBRO_E)[0]) < float(ponto(OMBRO_D)[0]) else 0.0
            self.ombro_e_a_esquerda = aproximar(self.ombro_e_a_esquerda, alvo, dt, 0.3)
        e_na_esquerda = self.ombro_e_a_esquerda > 0.5
        for lado in (0, 1):
            usa_e = (lado == 0) == e_na_esquerda
            ombro = OMBRO_E if usa_e else OMBRO_D
            cotovelo = COTOVELO_E if usa_e else COTOVELO_D
            pulso = PULSO_E if usa_e else PULSO_D
            sinal = -1.0 if lado == 0 else 1.0

            # Pata: direção ombro->pulso da pessoa × quanto o braço real está
            # esticado. O cotovelo sai da IK no shader. Sem dados, volta ao descanso.
            alcance = 0.66  # braço do boneco esticado, em U
            alvo_mao = normalizar(_v(0.35 * sinal, 1.0)) * 0.52
            if visivel(ombro) and not visivel(pulso) and visivel(cotovelo):
                # Mão fora do quadro (braço aberto perto da câmera): segue o cotovelo.
                oc = ponto(cotovelo) - ponto(ombro)
                if float(np.hypot(oc[0], oc[1])) > 1.0:
                    alvo_mao = normalizar(oc) * alcance * 0.95
            elif visivel(ombro) and visivel(pulso):
                op = ponto(pulso) - ponto(ombro)
                distancia = float(np.hypot(op[0], op[1]))
                if tem_ombros:
                    d = ponto(OMBRO_E) - ponto(OMBRO_D)
                    comprimento_braco = 1.6 * float(np.hypot(d[0], d[1]))
                else:
                    comprimento_braco = distancia
                if visivel(cotovelo):
                    a1 = ponto(cotovelo) - ponto(ombro)
                    a2 = ponto(pulso) - ponto(cotovelo)
                    comprimento_braco = float(np.hypot(a1[0], a1[1])) + float(np.hypot(a2[0], a2[1]))
                esticado = min(1.0, max(0.35, distancia / max(comprimento_braco, 1.0)))
                if distancia > 1.0:
                    alvo_mao = op / distancia * alcance * esticado
            self.mao[lado] = np.array(self.din_mao[lado].update(dt, alvo_mao), np.float32)

            quadril = QUADRIL_E if usa_e else QUADRIL_D
            joelho = JOELHO_E if usa_e else JOELHO_D
            tornozelo = TORNOZELO_E if usa_e else TORNOZELO_D
            perna = normalizar(_v(0.15 * sinal, 1.0))
            fim = tornozelo if visivel(tornozelo) else (joelho if visivel(joelho) else -1)
            if visivel(quadril) and fim >= 0:
                v = normalizar(ponto(fim) - ponto(quadril) + _v(1e-3, 0.0))
                perna = normalizar(_v(float(v[0]), max(float(v[1]), 0.15)))  # perna de desenho não sobe
            p = np.array(self.din_perna[lado].update(dt, perna), np.float32)
            self.perna[lado] = normalizar(p, perna)

        # ---- Rabo: corrente de Verlet (spring bone) ----
        # Cada elo tem inércia e é puxado para a curva de repouso (rigidez), perde
        # velocidade (arrasto) e mantém o comprimento. Quando o corpo se mexe, o
        # rabo atrasa e chicoteia sozinho.
        gato = animal == GATO
        base = raiz_px + (direita * 0.30 - cima * 0.34) * u_px
        elo = 0.16 * u_px
        balanco = 0.22 * math.sin(self.relogio_rabo * 2.2 + self.id)

        def direcao_repouso(k: int) -> np.ndarray:
            theta = (0.35 + 0.30 * k + balanco) if gato else (-0.10 - 0.05 * k + balanco * 0.4)
            return direita * math.cos(theta) + cima * math.sin(theta)

        if not self.rabo_iniciado:
            self.rabo_iniciado = True
            p = base.copy()
            for k in range(NUM_ELOS_RABO):
                self.rabo[k] = p.copy()
                self.rabo_anterior[k] = p.copy()
                p = p + direcao_repouso(k) * elo
        rigidez = 1.0 - (1.0 - (0.18 if gato else 0.28)) ** (dt * 60.0)
        arrasto = (1.0 - 0.12) ** (dt * 60.0)
        self.rabo[0] = base.copy()
        self.rabo_anterior[0] = base.copy()
        for k in range(1, NUM_ELOS_RABO):
            p = self.rabo[k]
            velocidade = (p - self.rabo_anterior[k]) * arrasto
            self.rabo_anterior[k] = p.copy()
            p = p + velocidade
            p[1] += 0.4 * u_px * dt * dt * 60.0  # um pouco de gravidade
            p = p + (self.rabo[k - 1] + direcao_repouso(k - 1) * elo - p) * rigidez
            d = p - self.rabo[k - 1]
            comprimento = float(np.hypot(d[0], d[1]))
            direcao = d / comprimento if comprimento > 1e-3 else direcao_repouso(k - 1)
            self.rabo[k] = self.rabo[k - 1] + direcao * elo
