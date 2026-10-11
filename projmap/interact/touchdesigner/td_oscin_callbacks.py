# ProjMap → TouchDesigner: callbacks do OSC In DAT.
#
# Como usar (ver projmap/interact/README.md, seção TouchDesigner):
#   1. OSC In DAT  (Network Port = 7000)  → aba "Callbacks DAT" aponta para este Text DAT.
#   2. Table DAT chamado "entities" (vazio) e Table DAT "players" (vazio) na mesma rede.
#   3. Geometry COMP com Instancing ligado, "Instance OP" = entities,
#      Translate X = tx, Translate Y = ty, Uniform Scale = scale; (opcional) cor por "shy".
#
# O motor (python -m projmap.interact --osc-out 127.0.0.1:7000) manda, a cada tick:
#   /projmap/frame [tick, t, count, flash]
#   /projmap/entity [id, group, x, y, state, heading, size]   (x, y em 0..1, y para baixo)
#   /projmap/player [id, x, y, yaw_deg, watching, gaze_x, gaze_y, gaze_r]
#   /projmap/event  [name, entity_id]
#   /projmap/scene  [json]
#
# NÃO TESTADO DENTRO DO TOUCHDESIGNER nesta entrega (só o protocolo foi testado em
# Python). Ajuste nomes de operadores se a sua rede for diferente.

import json

ASPECT = 16 / 9  # atualizado por /projmap/scene
STATES = {'idle': 0, 'move': 1, 'frozen': 2, 'shy': 3}
HEADER = ['id', 'group', 'tx', 'ty', 'scale', 'heading', 'state', 'shy']


def _table(name, header):
    t = op(name)
    if t.numRows == 0 or t[0, 0].val != header[0]:
        t.clear()
        t.appendRow(header)
    return t


def onReceiveOSC(dat, rowIndex, message, byteData, timeStamp, address, args, peer):
    global ASPECT
    if address == '/projmap/entity' and len(args) >= 7:
        eid, group, x, y, state, heading, size = args[:7]
        t = _table('entities', HEADER)
        row = int(eid) + 1
        while t.numRows <= row:
            t.appendRow([''] * len(HEADER))
        # Espaço do TD: origem no centro, y para cima; largura = ASPECT, altura = 1.
        values = [int(eid), group, (x - 0.5) * ASPECT, 0.5 - y, size, heading,
                  STATES.get(state, 0), 1 if state == 'shy' else 0]
        for c, v in enumerate(values):
            t[row, c] = v
    elif address == '/projmap/frame' and len(args) >= 3:
        count = int(args[2])
        t = _table('entities', HEADER)
        while t.numRows > count + 1:  # cena encolheu: remove linhas sobrando
            t.deleteRow(t.numRows - 1)
        if op('flash') is not None and len(args) >= 4:  # opcional: Constant CHOP "flash"
            op('flash').par.value0 = float(args[3])
    elif address == '/projmap/player' and len(args) >= 8:
        t = _table('players', ['id', 'tx', 'ty', 'yaw', 'watching', 'gx', 'gy', 'gr'])
        pid, x, y, yaw, watching, gx, gy, gr = args[:8]
        row = int(pid) + 1
        while t.numRows <= row:
            t.appendRow([''] * 8)
        for c, v in enumerate([int(pid), (x - 0.5) * ASPECT, 0.5 - y, yaw, int(watching),
                               (gx - 0.5) * ASPECT, 0.5 - gy, gr]):
            t[row, c] = v
    elif address == '/projmap/scene' and args:
        try:
            ASPECT = float(json.loads(args[0]).get('aspect', ASPECT))
        except Exception:
            pass
    elif address == '/projmap/event' and args:
        # Gancho para sons/efeitos: ex. op('audiofilein_scare').par.cuepulse.pulse()
        debug('evento', args)
    return
