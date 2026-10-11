# ProjMap — celular como sensor por USB/ADB (substitui o Kinect)

## Resumo

Um celular Android preso na parede, ligado ao PC por USB com ADB, passa a ser
o sensor da camada interativa. A página `/sensor/` roda a detecção de rosto no
navegador do celular e manda 6 pontos do rosto ao PC. O PC calcula a posição
da pessoa e para onde ela está olhando, e os fantasmas tímidos reagem. Não
precisa de app, Wi-Fi nem internet.

## Motivação

Sem Kinect no momento, o pedido foi usar um celular com ADB ligado para
transmitir os dados ao PC.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `projmap/interact/sensors.py` | Novo sensor `phone` (`PhoneSensor`). `apply_face()` compartilhado com a webcam. Histerese de 0,35 s para "sem rosto". **Correção:** o modelo 3D do rosto tinha esquerda e direita trocadas em relação ao MediaPipe, e uma pessoa de frente virava "de costas". |
| `projmap/interact/api.py` | WebSocket `/api/interact/phone`: conectar já troca o sensor para `phone` e o PC devolve o que está vendo. `GET/HEAD /api/interact/face-model` serve o modelo local. |
| `projmap/tools/adb.py` | `adb reverse tcp:8100 tcp:8100` + abre `/sensor/` no celular, com mensagens claras para "sem adb", "não autorizado" e "mais de um celular". |
| `projmap/tools/fetch_models.py` | Baixa o modelo oficial `face_landmarker.task` (uma vez) para o show funcionar offline. |
| `projmap/master/__main__.py` | `--sensor phone` e `--adb`. |
| `projmap/ui/app/sensor/page.tsx` | Página do celular: câmera (traseira ou frontal), MediaPipe FaceLandmarker (GPU com fallback para CPU), envio a 20 Hz com reconexão, tela sempre ligada e retorno ao vivo. |
| `projmap/ui/scripts/copy-mediapipe.mjs`, `package.json`, `next.config.mjs` | WASM do MediaPipe (`@mediapipe/tasks-vision` 1.0.1, Apache-2.0) copiado no build e servido pelo mestre; `trailingSlash` para `/sensor/`. |
| `projmap/ui/app/components/InteractPanel.tsx` | Mostra "celular conectado (fps)" e as instruções de ADB. |
| `tests/projmap/test_phone_sensor.py` | 14 testes: pontos → pessoa (posição, espelhamento, distância), **landmarks reais de frente** (regressão), lateralidade do modelo, histerese, timeout, WebSocket ponta a ponta, modelo local (GET/HEAD) e ADB com `subprocess` simulado. |
| Docs/board | Passo a passo em `interact/README.md`, quickstart no README, `ARCHITECTURE.md` e card F8. |

## Como funciona

1. `adb reverse` faz o `localhost:8100` do celular apontar para o mestre.
   `localhost` é contexto seguro, então o navegador libera a câmera em `http://`.
2. A página `/sensor/` carrega o MediaPipe (WASM e modelo, ambos do mestre),
   detecta o rosto e manda `{face, pts[6], w, h}` por WebSocket, pelo cabo.
3. O PC faz o `solvePnP` (yaw da cabeça), calcula `x` pela posição do nariz e
   `distance` pela distância entre os olhos (espelhado: câmera na parede
   olhando o público).
4. Sem rosto por mais de 0,35 s, a pessoa conta como "de costas" e os
   fantasmas avançam. Sem mensagens por 2 s, a pessoa conta como "não
   detectada".

## Como validar

```bash
xvfb-run -a pytest -q tests/projmap        # 89 passed

python -m projmap.tools.fetch_models        # uma vez
python -m projmap.master --project shows/meu-show.projmap --display 1 --sensor phone --adb
# no celular: "Iniciar sensor"; olhe para a parede e vire de costas
```

Validação feita nesta entrega: Chromium com câmera falsa, usando uma foto real
de rosto (NASA, domínio público) servida em `localhost` como no `adb reverse`.

- Contexto seguro OK. WASM e modelo vieram do mestre, e o WebSocket conectou.
  O sensor trocou sozinho para `phone`.
- **Bug encontrado e corrigido.** De frente, o PC dava yaw ≈ 179° ("de
  costas"). Depois da correção:

  | Situação | yaw |
  |---|---|
  | Rosto de frente | ≈ −1° |
  | Rosto virado (deformado em perspectiva) | −26°, sinal correto |

  A posição acompanha o rosto (0,55 → 0,77).
- **Offline:** com todo acesso externo bloqueado, foram 0 pedidos externos e o
  rosto continuou detectado.
- Os 6 pontos aparecem corretamente sobre o rosto na tela do celular.

## Critério de aceite

- [x] O celular por USB/ADB alimenta a cena interativa, sem app e sem Wi-Fi.
- [x] De frente = olhando; sem rosto = de costas (com tolerância a piscadas).
- [x] Funciona sem internet.
- [x] Testes automatizados, incluindo landmarks reais, e E2E no navegador.
- [ ] Validar num **celular Android real** preso na parede, com o projetor.

## Pendências / próximos

- Testar no seu celular. O fps de detecção depende do aparelho; em navegador
  headless deu 4–12 fps.
- Calibração de distância por pessoa (hoje é um fator fixo, `distance_scale`).
- Várias pessoas: o MediaPipe aceita `numFaces > 1`.
- Modo "celular na mão": usar o giroscópio como direção do olhar.
- `python -m projmap.interact` (motor sem mestre) ainda não aceita `phone`,
  porque precisa do servidor web do mestre.
