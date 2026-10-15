# ProjMap · Camada interativa (IA + sensores + TouchDesigner)

Projeções que **reagem às pessoas**. Você descreve a experiência em texto, o
sistema monta a cena e um sensor (webcam, Kinect ou simulação) diz onde a
pessoa está e para onde ela olha. O visual sai no próprio ProjMap (warp e
máscara do mapeamento) ou no TouchDesigner, via OSC.

```mermaid
flowchart LR
  TXT[Texto: "fantasmas que param quando eu olho…"] --> NLP[NLP: LLM do repo<br/>+ validação + fallback]
  NLP --> SPEC[SceneSpec<br/>sprites + comportamentos]
  CAM[Webcam · MediaPipe] --> SENS
  KIN[Kinect → TouchDesigner] -- OSC :7001 --> SENS
  SIM[Pessoa simulada] --> SENS
  SENS[Sensor: posição + yaw da cabeça] --> SIM2[Simulação 60 Hz<br/>olhar · perseguir · congelar]
  SPEC --> SIM2
  SIM2 --> R[Renderer nativo] --> PM[Superfície ProjMap<br/>fonte 'Cena interativa']
  SIM2 -- OSC :7000 --> TD[TouchDesigner<br/>instancing / partículas / shaders]
```

## A mecânica dos "fantasmas tímidos"

O preset `fantasmas-timidos` faz exatamente o que você descreveu:

- **Você olha** e os fantasmas na região do seu olhar **param e cobrem o rosto**.
- **Você vira de costas** e todos **vêm na sua direção**.
- **Se um te alcança**, a parede pisca e eles recomeçam das bordas.

**Como o "olhar" é calculado.** A pessoa fica diante da parede. Com a posição
dela (`x`, `distance`) e a rotação da cabeça (`yaw`), o raio do olhar cruza a
parede num ponto. O campo de visão (`fov_deg`, padrão 60°) abre um disco em
volta desse ponto, e o que cai dentro está sendo olhado. De costas
(|yaw| ≥ 90°) ou sem rosto visível na webcam, nada é olhado.

> **Direitos autorais.** A *mecânica* (parar quando é olhado) é livre. O
> *personagem* Boo é da Nintendo. Por isso o fantasma aqui é um desenho original.
> Num show público ou comercial, não use sprites nem o nome do personagem.

## Rodar

### Dentro do ProjMap (UI + parede)

```bash
python -m projmap.master --project shows/meu-show.projmap --display 1 --open
```

1. No card **Interativo** da UI, descreva a cena e clique em **Gerar cena**.
   Também pode usar um preset: *Fantasmas tímidos*, *Vaga-lumes do olhar* ou
   *Cardume assustado*.
2. Numa superfície, escolha a fonte **Cena interativa**. Pode ser a parede
   inteira ou só um quad, e passa pelo warp, borda suave e mistura como
   qualquer vídeo.
3. Sem sensor, use **Pessoa simulada**:
   - **Automático** alterna de frente e de costas;
   - **Olhar a parede** e **Virar de costas** mudam na hora;
   - os sliders ajustam a posição e a rotação da cabeça.
   Ligue **Mostrar olhar** para ver a região do olhar na projeção.

Opções do mestre:

| Flag | Para quê |
|---|---|
| `--sensor sim\|osc\|webcam\|phone` | de onde vêm as pessoas (padrão `sim`) |
| `--adb` | celular por USB: `adb reverse` + abre `/sensor/` no celular |
| `--sensor-port 7001` | porta OSC do sensor `osc` (Kinect via TD) |
| `--osc-out 127.0.0.1:7000` | manda o estado da cena para o TouchDesigner |
| `--no-interact` | desliga a camada |

A cena ativa fica salva em `<projeto>/scenes/active.json`.

### Só o motor (TouchDesigner desenha)

```bash
python -m projmap.interact --text "5 fantasmas que param quando eu olho e me perseguem quando viro" \
    --osc-out 127.0.0.1:7000 --preview --windowed --debug
```

`--preview` abre uma janela com o renderer nativo para conferir. Sem ela, o
motor só envia OSC.

## Descrever cenas em texto (NLP)

O texto vira uma `SceneSpec` em JSON, com **peças prontas**:

| Peça | Opções |
|---|---|
| Sprites | `ghost`, `orb`, `firefly`, `fish` |
| Comportamentos | `chase_player`, `flee_player`, `wander`, `seek_gaze`, `freeze_when_watched` |
| Quando alguém é pego | `flash`, `reset` |

A IA nunca escreve código. Tudo é validado antes de rodar, e o resultado diz
de onde veio a cena:

1. **Com LLM.** Usa a mesma factory do Auto Niche Engine
   (`agents.llm.get_text_client`: Ollama local por padrão ou Gemini), configurada
   por `config.json`/`.env`. Se o JSON vier errado, o erro volta ao LLM para ele
   corrigir uma vez.
2. **Sem LLM, ou se ainda falhar.** Um parser por palavras-chave em português e
   inglês monta a cena. A UI avisa "Montado por palavras-chave, sem IA" e mostra
   o motivo.

Exemplos que o parser entende sozinho:

| Texto | Cena |
|---|---|
| "fantasmas do mario que param quando olho e me buscam quando viro" | fantasmas tímidos (perseguem e congelam) |
| "20 peixes azuis que fogem de mim" | cardume com fuga |
| "vaga-lumes que vão para onde eu olho" | vaga-lumes que seguem o olhar |
| "três bolas vermelhas flutuando devagar" | 3 orbes vagando |

## Sensores

### Celular por USB/ADB (`phone`) — recomendado sem Kinect

Um celular Android **preso na parede projetada, com a câmera virada para o
público**, faz o papel do Kinect. Não é preciso instalar app nem ter Wi-Fi:

```
celular (navegador: câmera + MediaPipe) ──USB / adb reverse──► PC (mestre :8100)
   detecta o rosto e manda 6 pontos (~20×/s)          calcula posição + rotação da cabeça
```

- **Por que ADB.** Com `adb reverse tcp:8100 tcp:8100`, o `localhost:8100` do
  celular aponta para o PC. Para o navegador, `localhost` é contexto seguro,
  então ele libera a câmera **sem HTTPS**. Pelo Wi-Fi, com IP, o navegador
  bloquearia a câmera. Os dados vão pelo cabo, e o mestre continua fechado em
  `127.0.0.1`.
- **Divisão de trabalho.** A rede neural do rosto roda **no celular**. O PC só
  recebe 6 pontos e faz o `solvePnP`, a mesma conta da webcam, coberta por
  testes com pontos reais.
- **Funciona offline.** O WASM do MediaPipe vai junto no build da UI, e o
  modelo do rosto é servido pelo mestre (`python -m projmap.tools.fetch_models`,
  uma vez).

Passo a passo:

1. **No celular:** Configurações → Sobre o telefone → toque 7× em "Número da
   versão". Depois, em Opções do desenvolvedor, ligue **Depuração USB**.
2. **No PC:**
   - instale o **Android Platform Tools** (`adb`) e deixe-o no PATH;
   - rode uma vez `python -m projmap.tools.fetch_models` (modelo do rosto,
     para funcionar sem internet);
   - conecte o cabo e aceite o aviso "Permitir depuração USB" no celular.
3. **Rode o mestre:**
   ```bash
   python -m projmap.master --project shows/meu-show.projmap --display 1 --sensor phone --adb
   ```
   O `--adb` faz o `adb reverse` e abre `http://localhost:8100/sensor/` no
   celular. Para fazer à mão: `python -m projmap.tools.adb`.
4. **Na página do celular**, toque em **Iniciar sensor**:
   - use a câmera traseira (melhor) e deixe marcado "Celular na parede olhando
     o público";
   - a tela mostra "Rosto detectado" e o que o PC está vendo (olhando ou de
     costas, rotação da cabeça, quantos fantasmas andam ou estão parados);
   - a tela fica ligada sozinha.
5. **Posicionamento:** na altura dos olhos, centralizado na área projetada,
   carregando pelo USB. A posição da pessoa na parede vem de onde o rosto
   aparece na imagem; a distância vem do tamanho do rosto.

**Rosto ausente conta como "de costas"**, que é o que a mecânica dos fantasmas
precisa. Há uma tolerância de ~0,35 s: uma piscada da detecção não faz os
fantasmas avançarem. Se o celular parar de mandar dados por 2 s, a pessoa vira
"não detectada".

### Simulado (`sim`)
Pessoa virtual controlada pela UI ou pela API (`POST /api/interact/player`) ou
por roteiro automático. Serve para criar e testar sem hardware.

### Webcam (`webcam`)
- **Montagem.** Uma câmera comum **na parede, centralizada, olhando para o
  público**. O MediaPipe FaceLandmarker acha o rosto e o `solvePnP` estima a
  rotação da cabeça.
- **Leitura.** A posição do nariz dá o `x` na parede. A distância entre os
  olhos estima o `distance`.
- **Rosto não detectado** é tratado como "de costas", que é o que importa
  para a mecânica.

```bash
pip install mediapipe
# baixe o modelo oficial "face_landmarker.task" (MediaPipe Face Landmarker)
export PROJMAP_FACE_MODEL=models/face_landmarker.task
python -m projmap.master --project ... --sensor webcam
```

> A matemática da pose está testada com rostos sintéticos. A captura da câmera
> real **não foi testada** nesta entrega (o ambiente não tem webcam).

### Kinect (via TouchDesigner, sensor `osc`)
O TouchDesigner já lê Kinect v2, Azure e Orbbec nativamente (Kinect CHOP).
Sem driver no nosso processo:

1. Na rede do TD:
   - um **Kinect CHOP**;
   - um **OSC Out DAT** chamado `oscout_projmap`, apontando para
     `127.0.0.1:7001`;
   - um **Execute DAT** (com *Frame End* ligado) com o conteúdo de
     [`touchdesigner/td_kinect_to_osc.py`](touchdesigner/td_kinect_to_osc.py).
2. Ajuste `WALL_WIDTH_M`, `WALL_HEIGHT_M` e os nomes de canal do seu Kinect.
3. Rode o mestre com `--sensor osc`.

Formato aceito (qualquer fonte serve):

```
/player  id  x[0..1]  distance  yaw_deg  tracked  [face]
/player/<id>/x | /distance | /yaw | /tracked | /face
```

> **Limitação conhecida.** O esqueleto do Kinect assume a pessoa de frente;
> de costas ele tende a espelhar o corpo. Para a mecânica dos fantasmas, junte
> um detector de rosto (ex.: plugin MediaPipe para TouchDesigner) e mande
> `face = 0/1`. O ProjMap trata `face = 0` como "de costas".

## TouchDesigner desenhando o visual

O motor calcula o estado (posições e quem está tímido ou andando) e o
TouchDesigner faz o visual: instancing, partículas, GLSL, áudio. Para receber:

1. **OSC In DAT** na porta `7000`, com *Callbacks DAT* apontando para um Text DAT
   com [`touchdesigner/td_oscin_callbacks.py`](touchdesigner/td_oscin_callbacks.py).
2. Dois **Table DAT** vazios: `entities` e `players`.
3. **Geometry COMP** com *Instancing* a partir de `entities`:
   `tx`, `ty`, `scale`. A coluna `shy`/`state` troca a textura ou a cor.
4. (Opcional) um **Constant CHOP** `flash`, que recebe o flash do "pegou".
5. Rode o mestre (ou o motor) com `--osc-out 127.0.0.1:7000`.

Mensagens enviadas (coordenadas 0..1, y para baixo):

```
/projmap/frame   tick t count flash
/projmap/entity  id group x y state heading size        state: move|frozen|shy|idle
/projmap/player  id x y yaw_deg watching gaze_x gaze_y gaze_r
/projmap/event   name entity_id                           ex.: caught
/projmap/scene   json                                     quando a cena muda
```

Para levar a saída do TD de volta ao mapeamento do ProjMap, o caminho é
**NDI**, que entra na F5 como fonte de superfície. Até lá, o TD pode fazer o
próprio mapeamento.

> **Licença do TouchDesigner.** A edição Non-Commercial limita a saída a
> 1280×1280. Para projetar em 1080p ou mais, é preciso licença Commercial/Pro.
>
> Os scripts do TD **não foram executados dentro do TouchDesigner** nesta
> entrega. O protocolo OSC foi testado de ponta a ponta em Python.

## Assistir de outra máquina (RTSP)

Com `PROJMAP_RTSP_URL` definida no `.env`, o mestre publica o que a camada
interativa está mostrando (a cena ou o efeito do visual_frames) num servidor
RTSP (MediaMTX e afins):

```ini
PROJMAP_RTSP_URL=rtsp://usuario:senha@servidor:8554/cam
PROJMAP_RTSP_SIZE=1280x720   # opcional
PROJMAP_RTSP_FPS=30          # opcional
PROJMAP_RTSP_BITRATE=4M      # opcional
PROJMAP_RTSP_TRANSPORT=tcp   # opcional
```

De outra máquina na mesma rede do servidor:

```bash
ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay "rtsp://.../cam"
```

- Roda numa thread própria (`interact/stream.py::RtspPublisher`, ffmpeg via
  `stdin` → H.264 `zerolatency`): servidor lento ou fora do ar **não trava a
  projeção**, e a transmissão reconecta sozinha com recuo progressivo (1 s →
  15 s).
- A URL tem senha — por isso só vem do `.env` (nunca de `--flag`, onde
  apareceria na lista de processos), e é mascarada em todo log/status/erro.
- Sem `PROJMAP_RTSP_URL`, nada sobe e o ProjMap funciona como antes.
- A credencial precisa de permissão de **publicação** (`ANNOUNCE`) no
  servidor — uma credencial só de leitura recebe `401`. Detalhes em
  [`docs/entregas/projmap-transmissao-rtsp.md`](../../docs/entregas/projmap-transmissao-rtsp.md).

## API (`/api/interact/...`)

| Método | Rota | Para quê |
|---|---|---|
| GET | `/state` | cena, entidades, pessoas, olhar, eventos |
| POST | `/generate` `{text, use_llm}` | texto → cena (aplica na hora) |
| PUT | `/spec` | aplica uma `SceneSpec` editada à mão |
| GET/POST | `/presets`, `/presets/{nome}` | presets |
| POST | `/player` `{x, distance, yaw_deg, tracked}` | pessoa simulada |
| POST | `/player/auto` · `/reset` · `/pause?paused=` · `/debug?on=` | controles |
| POST | `/sensor` `{kind, options}` | troca o sensor em execução |
| WS | `/phone` | celular-sensor: `{face, pts[6], w, h, mirror, fps}`; responde com o que o PC vê |
| GET/HEAD | `/face-model` | modelo do rosto local para o celular (offline) |
