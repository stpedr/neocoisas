# TouchDesigner (Kinect CHOP) → ProjMap: Execute DAT que envia a pessoa por OSC.
#
# Rede sugerida:
#   Kinect CHOP (ou Kinect Azure CHOP) → este Execute DAT (onFrameEnd ligado)
#   OSC Out DAT chamado "oscout_projmap" → Network Address 127.0.0.1, Port 7001
#   Rode o motor com:  python -m projmap.interact --sensor osc --sensor-port 7001 ...
#
# Premissas de montagem: o Kinect fica NA PAREDE projetada, centralizado, olhando
# para o público. Eixos do Kinect: x para a direita do sensor, z = distância.
#
# Limitação conhecida: o esqueleto do Kinect assume a pessoa de frente; de costas
# ele costuma "espelhar" em vez de dizer que está de costas. Para a mecânica dos
# fantasmas, mande também "face" (0/1) de um detector de rosto (ex.: plugin
# MediaPipe para TouchDesigner) — o ProjMap trata face=0 como "de costas".
#
# NÃO TESTADO DENTRO DO TOUCHDESIGNER nesta entrega. Confira os nomes dos canais
# no seu Kinect CHOP (variam entre Kinect v2 e Azure) e ajuste abaixo.

import math

KINECT = 'kinect1'
WALL_WIDTH_M = 4.0    # largura da área projetada na parede (metros)
WALL_HEIGHT_M = 2.25  # altura da área projetada (1 unidade no ProjMap)
FACE_CHOP = None      # ex.: 'face_present' — CHOP com 1 canal 0/1 vindo do detector de rosto
CH = {
    'tracked': 'p1/tracked',
    'head_x': 'p1/head:tx', 'head_z': 'p1/head:tz',
    'sl_x': 'p1/shoulder_l:tx', 'sl_z': 'p1/shoulder_l:tz',
    'sr_x': 'p1/shoulder_r:tx', 'sr_z': 'p1/shoulder_r:tz',
}


def _ch(chop, name, default=0.0):
    c = chop[name]
    return float(c.eval()) if c is not None else default


def onFrameEnd(frame):
    k = op(KINECT)
    out = op('oscout_projmap')
    if k is None or out is None:
        return
    tracked = _ch(k, CH['tracked'], 1.0) >= 0.5
    hx, hz = _ch(k, CH['head_x']), _ch(k, CH['head_z'])
    # posição ao longo da parede, 0..1 (sensor no centro; espelhado: x do sensor
    # cresce para a esquerda de quem olha a parede)
    x = 0.5 - hx / WALL_WIDTH_M
    distance = max(0.05, hz / WALL_HEIGHT_M)
    # yaw pela linha dos ombros: de frente para a parede, os ombros ficam paralelos a ela
    dx = _ch(k, CH['sr_x']) - _ch(k, CH['sl_x'])
    dz = _ch(k, CH['sr_z']) - _ch(k, CH['sl_z'])
    yaw = math.degrees(math.atan2(dz, dx)) if (dx or dz) else 0.0
    args = [0, x, distance, yaw, 1 if tracked else 0]
    if FACE_CHOP and op(FACE_CHOP) is not None:
        args.append(1 if op(FACE_CHOP)[0].eval() >= 0.5 else 0)
    out.sendOSC('/player', args)
    return
