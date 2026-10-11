# Controlador Raspberry Pi (botões/LEDs GPIO)

## Resumo
Novo serviço opt-in `raspberry_pi.py` que permite operar o Auto Niche Engine por
botões físicos e LEDs de status ligados ao GPIO de um Raspberry Pi.

## Motivação
Ter um "painel físico" para revisar e disparar a esteira sem abrir a web ou o
Telegram — útil em estúdio/bancada ou com o Pi como controle remoto da stack.

## O que mudou
| Arquivo | Mudança |
|---|---|
| `raspberry_pi.py` | Controlador: contrato `Board` + factory `get_board` (`gpiozero` \| `mock`), cliente HTTP da API, lógica de botões/LEDs |
| `tests/test_raspberry_pi.py` | 9 testes offline (pinos, seleção de ideia, LEDs, controlador com API mockada) |
| `requirements-rpi.txt` · `Dockerfile.rpi` | Imagem enxuta do controlador |
| `docker-compose.yml` | Serviço `rpi` (profile `rpi`, acesso a `/dev/gpiochip0`) |
| `.env.example` | `RPI_BACKEND`, `RPI_POLL_INTERVAL`, `RPI_PIN_*` |
| `board/seed.py` | Card "Controlador Raspberry Pi" (Sprint 12 · Hardware) |

## Como funciona
Igual ao bot do Telegram: processo separado que só fala com a API por HTTP.

| Botão (BCM) | Ação | Endpoint |
|---|---|---|
| APPROVE (17) | aprova a pendente mais antiga | `POST /api/ideas/{id}/approve` |
| REJECT (27) | rejeita a pendente mais antiga | `POST /api/ideas/{id}/reject` |
| RENDER (22) | renderiza a aprovada mais antiga sem vídeo | `POST /api/ideas/{id}/render` |
| PUBLISH (23) | roda o agendador agora | `POST /api/schedule/run-now` |
| GENERATE (24) | autogera ideias (prompt do agendamento) | `POST /api/schedule/autogen-now` |

| LED (BCM) | Significado |
|---|---|
| PENDING (5) | há ideias aguardando revisão (consulta `/api/counts` a cada `RPI_POLL_INTERVAL` s) |
| BUSY (6) | ação em andamento (uma por vez; cliques extras são ignorados) |
| ERROR (13) | última ação/consulta falhou |

Ligação: botões entre o pino e GND (pull-up interno); LEDs pino → resistor 330 Ω → LED → GND.

## Como validar
```bash
pytest -q tests/test_raspberry_pi.py
# Simulação no PC (sem Pi), com a API rodando:
RPI_BACKEND=mock python raspberry_pi.py      # teclas a/r/d/p/g + Enter
# No Pi:
pip install -r requirements-rpi.txt && python raspberry_pi.py
# ou: docker compose --profile rpi up -d rpi
```

## Critério de aceite
- [x] Botões disparam aprovar/rejeitar/renderizar/publicar/gerar via API
- [x] LEDs refletem pendências, ocupado e erro
- [x] Backend `mock` para testar sem hardware
- [x] Pinos configuráveis por env, com validação de repetidos
- [x] `pytest -q` verde
- [ ] Validado em hardware real

## Pendências / próximos
- Display (OLED I2C/LCD) mostrando o título da ideia atual.
- Buzzer/feedback ao concluir render.
- Validar em Pi 4 e Pi 5 (device do gpiochip pode variar por kernel).
