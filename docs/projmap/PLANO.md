# ProjMap — Plano de implementação

> Baseado no [`BLUEPRINT.md`](BLUEPRINT.md) (Fase 0).
> **Status:** aprovado como proposto (D1–D8) em 2026-10-11.
> F1 entregue — ver `projmap/README.md` e `docs/entregas/projmap-f1-um-projetor.md`.

---

## 1. Decisões para você aprovar

| # | Decisão | Recomendação | Alternativa | Por quê |
|---|---|---|---|---|
| **D1** | Onde o código mora | Pacote **`projmap/`** neste repo (`neocoisas`), com `requirements-projmap*.txt` próprios e **sem acoplamento** ao runtime do Auto Niche Engine | Repo novo | Você pediu "na aplicação". O mesmo repo deixa reaproveitar os providers de mídia (F7) e o board. O ciclo de vida continua separado. |
| **D2** | Stack da UI do mestre | **Next.js 14 com `output: "export"`** em `projmap/ui/` (mesmo framework e design tokens do `web/`), servido como arquivos estáticos pelo FastAPI do mestre | Vite + React | O mestre roda **nativo no Windows**, sem Docker: o mDNS/multicast não atravessa o Docker Desktop. A UI é só arquivo estático, sem precisar de Node em produção. O mesmo build vira o app Android (D6). |
| **D3** | Renderer do nó | **moderngl** (contexto) + **pyglet 2** (janela/tela cheia/vsync). Shaders em **GLSL ES 3.00** com `#version` injetado por backend | Só pyglet | O moderngl é o pedido e o mais ergonômico. O U1 (GL 3.3 vs GLES 3.1 no Pi 5) é resolvido por spike no início da F2. Se falhar, o mesmo GLSL roda via pyglet/GLES. |
| **D4** | Rede | Descoberta **zeroconf**. Controle por **WebSocket** (o nó é servidor). Mídia por **HTTP endereçado por hash**. Relógio/timecode por **OSC/UDP** | OSC para tudo | O WS dá confirmação e estado. O UDP fica só para o que é sensível a tempo. O hash torna a pré-distribuição idempotente. |
| **D5** | Espaço comum entre projetores | Manual: **foto do projetor *i*** (um espaço por nó). Automático (F4): **imagem da câmera de calibração** (espaço único, onde o edge blend é calculado) | Modelo 3D (mapamok) | Não exige modelo 3D. O modo 3D/pinhole fica como evolução. |
| **D6** | Celular / Android | **Web mobile responsiva** (remote + captura de foto) **+ app Android via Capacitor** empacotando a mesma UI | PWA instalável / TWA | PWA e câmera exigem HTTPS, e a LAN é HTTP. O TWA exige domínio público. O Capacitor resolve as duas coisas e gera APK. |
| **D7** | Segmentação com IA | **SAM 2.1 oficial** (Meta, Apache-2.0) como extra opcional `projmap[ai]`, via factory `get_segmenter: manual \| classic \| sam2` | `ultralytics` | O `ultralytics` é **AGPL**. O fallback `classic` (OpenCV) garante que tudo funciona sem PyTorch. |
| **D8** | Mídia no Pi 5 | Transcodificar no mestre para o **perfil do nó** (H.264 1080p30 decodificado por software, ou HEVC). **Modo baked** (1 vídeo por nó) como opção de robustez | HAP | O Pi 5 não tem decoder H.264 por hardware nem compressão BC (sem HAP). O baked é o "mpv em loop" do ifnull, só que sincronizado. |
| **D9** | ORM/banco pro catálogo (Fase 0 da migração do frontend) | **SQLAlchemy 2.0 async + `aiosqlite`** (migrações com **Alembic**), dentro do FastAPI atual (`master/app.py`) | `prisma-client-py` + SQLite | Revisto em 2026-10-15 a pedido do usuário: trocar por algo mais próximo do "padrão comercial" open source do ecossistema Python. SQLAlchemy é o ORM de fato-padrão (muito mais adotado/mantido que o `prisma-client-py`, que é comunitário), Alembic é a ferramenta de migração companion oficial, e nenhum dos dois depende de um binário Rust baixado por um CLI em Node — é só `pip install`. Spike em 2026-10-15: `create_async_engine("sqlite+aiosqlite:///...")` + modelo declarativo + `create_all` + insert/select assíncronos funcionaram de primeira, nativo no Windows, sem Docker, sem passo de geração. `project.json` continua a fonte de verdade do show; o banco é só para catálogo/biblioteca/presets (ver plano em `docs/planejamento/`). (Histórico: a Fase 0 original validou `prisma-client-py` com sucesso também — ver `docs/entregas/projmap-ui-spike-prisma.md` — a troca foi por preferência de stack, não por um problema técnico encontrado.) |

**Nota sobre D6 (revisão parcial, 2026-10-15):** a limitação de D6 (PWA +
câmera exige HTTPS) só se aplica à tela do **sensor** (`sensor/page.tsx`,
que usa `getUserMedia` para vídeo em tempo real). O editor e o remote usam
`<input type="file" capture="environment">` para a foto da posição do
projetor — um seletor nativo do sistema, sem exigência de secure context —
então **podem** virar PWA instalável normalmente. D6 continua valendo para
o sensor (Capacitor/app Android).

---

## 2. Estrutura do código (alvo)

Os módulos pedidos (`capture/ detect/ calibrate/ mapping/ net/ node/ ui/`)
mais dois de suporte: `core/` (modelo do projeto e geometria, usado por todos)
e `content/` (fontes de mídia, compartilhadas entre preview e nó). Cada
capacidade externa segue o padrão **contrato + factory** do repo (CLAUDE.md).

```
projmap/
  ARCHITECTURE.md            # decisões de engenharia (criado na F1, cresce a cada fase)
  README.md                  # setup do mestre (Windows) e dos nós (Pi OS / Linux)
  core/
    project.py               # modelos pydantic do project.json v1 + migrações
    geometry.py              # homografia (DLT normalizada), uv projetivo, polígonos, IoU
    store.py                 # salvar/carregar .projmap/ e exportar/importar .pmz
  capture/
    photos.py                # upload/registro de fotos por projetor (web e celular)
    camera.py                # webcam (OpenCV) para a calibração
  detect/
    factory.py               # get_segmenter(config): manual | classic | sam2
    projection_area.py       # detecção do quad projetado (E5)
    classic.py               # segmentação OpenCV (bordas/cores) sem IA
    sam2_segmenter.py        # SAM 2.1 (import tardio; extra opcional)
    polygons.py              # máscara → polígono editável (approxPolyDP, quad-fit)
    reconcile.py             # re-segmentação → ids estáveis por IoU (E4)
  calibrate/
    graycode.py              # gerar/decodificar (NumPy), confiança, LSB adaptativo
    procam.py                # mapa câmera↔projetor, homografia/grade por superfície
    latency.py               # medição de input lag (flash + câmera)
  mapping/
    warp.py                  # homografia base + offsets de grade/Bézier → malha fina
    bezier.py                # patches bicúbicos
    masks.py                 # rasterização de polígonos + feather
    blend.py                 # pesos de edge blend (soma linear = 1) + gama
    bake.py                  # modo baked: render offline do canvas do projetor
  content/
    factory.py               # get_source(kind): video | image | gif | ndi | color | test
    video.py  gif.py  image.py  ndi.py  test_patterns.py
  net/
    discovery.py             # zeroconf: anunciar (nó) / descobrir (mestre)
    clock.py                 # servidor/cliente de relógio (NTP-like), estimador de offset
    timecode.py              # contrato de playback → posição local
    protocol.py              # mensagens WS tipadas (pydantic)
    pjlink.py                # cliente PJLink classe 1 (auth MD5), sem dependências
  master/
    app.py                   # FastAPI: REST do projeto, WS da UI, /media, servidor de relógio
    nodes.py                 # gerência dos nós conectados (config, mídia, status)
  node/
    __main__.py              # python -m projmap.node --name proj-esq [--windowed]
    renderer.py              # moderngl: surfaces, máscaras, composite, passe final
    shaders/                 # *.glsl (GLSL ES 3.00 compartilhado com o preview WebGL2)
    player.py                # agenda frames por relógio comum, correção de deriva
  ui/                        # Next.js (export estático): editor, remote mobile
  android/                   # projeto Capacitor (F6)
  tools/
    simulate_nodes.py        # F2: N nós locais com offset/jitter injetados
    measure_sync.py          # relatório p50/p95/máx de desvio em frames
tests/projmap/               # pytest (roda junto com o `pytest -q` da raiz)
```

**Requisitos separados:**
- `requirements-projmap-master.txt`: fastapi, uvicorn, numpy, opencv-python,
  pillow, av, zeroconf, python-osc, websockets, pydantic.
- `requirements-projmap-node.txt`: numpy, moderngl, pyglet, av, pillow,
  zeroconf, python-osc, websockets. **Sem torch**, porque precisa ser leve no Pi.
- `requirements-projmap-ai.txt`: torch, sam2 (opcional, pesado).
- NDI: `cyndilib` (opcional) + **NDI Runtime instalado pelo usuário** (não
  redistribuível).

---

## 3. Fases

Em cada fase: testes `pytest -q` verdes, `npm run build` da UI,
`docs/entregas/<slug>.md` no formato do CLAUDE.md, card movido no board e
`ARCHITECTURE.md` atualizado.

### F1 — Um projetor, local, quads manuais + vídeo/GIF (MVP)

**Entrega:** mestre e nó no **mesmo processo/PC**. A UI carrega a foto, você
desenha as superfícies como quads sobre ela, arrasta os cantos e escolhe vídeo
ou GIF por superfície. Uma janela (2º monitor/projetor) mostra o resultado em
tempo real. Salvar/carregar o projeto.

Tarefas:
1. `core/geometry.py`: homografia por DLT **normalizada** (Hartley) e
   `perspective_transform`; uv projetivo para a malha.
2. `core/project.py` + `core/store.py`: esquema v1, salvar/carregar, mídia
   por sha256, `.pmz`.
3. `content/`: vídeo (PyAV em thread com fila), imagem e GIF (frames +
   durações por frame, loop por tempo).
4. `node/renderer.py`: N superfícies × textura, uv projetivo, máscara simples,
   tela cheia por monitor (`--display 1`).
5. `master/app.py` + `ui/`: editor em canvas 2D com pointer events (funciona
   com mouse e toque). Cantos com zoom/lupa, snap e nudge pelo teclado. Modo
   "padrão de alinhamento" (bordas Canny da foto + grade) projetado para
   conferir na parede (E7).
6. `projmap/README.md` (setup F1) + `ARCHITECTURE.md` (seções de
   coordenadas e warp).

**Aceite:**
- [ ] Testes de homografia: round-trip de pontos < 1e-6 px; igual ao
      `cv2.findHomography` (método 0) em 4 pontos; rejeita cantos colineares
      ou fora de ordem; uv projetivo sem a "dobra" diagonal (teste de pixel
      no centro de um quad em perspectiva).
- [ ] Projeto salvo → recarregado → idêntico (round-trip de JSON + hashes de
      mídia).
- [ ] GIF respeita as durações por frame; vídeo em loop sem salto visível.
- [ ] 1080p30 com 4 superfícies estáveis no PC (fps logado).

### F2 — Mestre/nós em rede, 3 nós simulados, sincronia medida

**Entrega:** o nó vira processo próprio (`python -m projmap.node`). O mestre
descobre os nós por mDNS, distribui config e mídia, e manda o contrato de
playback. `tools/simulate_nodes.py` sobe 3 janelas no mesmo PC, cada uma com
**offset de relógio (±200 ms) e jitter de rede (0–30 ms) injetados**.

Tarefas: `net/discovery.py`, `net/clock.py` (estimador de mínimo RTT +
mediana), `net/timecode.py`, `net/protocol.py`, `master/nodes.py`,
`node/player.py` (deriva: repetir/pular frame se > ½ frame, seek se > 0,5 s),
pré-distribuição de mídia com verificação de hash e "pronto para tocar" só com
tudo em cache. **Spikes U1 e U2 no Pi 5**, se você tiver um em mãos.

**Aceite:**
- [ ] Teste do estimador de relógio: com jitter simulado de 0–30 ms, o erro de
      offset é < 2 ms (p95).
- [ ] Teste do timecode: posição local correta sob offset, pause/seek/loop.
- [ ] `measure_sync.py` com 3 nós simulados, 10 min: **desvio máximo entre nós
      < 1 frame a 30 fps** (meta do requisito), p95 reportado.
- [ ] Um nó que entra atrasado (late-join) sincroniza em < 2 s.
- [ ] Um nó desconectado e reconectado volta sozinho, sem ação na UI.

### F3 — Detecção de superfícies com IA a partir da foto

**Entrega:** botão "Detectar superfícies" na foto. O SAM 2 (automático ou por
cliques/caixa na UI) gera máscaras → polígonos editáveis → superfícies.
A área projetada (foto com branco) é detectada e vira o limite do projetor.

Tarefas: `detect/factory.py`, `classic.py`, `sam2_segmenter.py`,
`polygons.py` (simplificação com tolerância ajustável na UI; ajuste para quad
quando a superfície "parece" retangular), `projection_area.py` (E5),
`reconcile.py` (E4), alinhamento foto-dia → foto-branco (ORB/AKAZE + RANSAC +
ECC).

**Aceite:**
- [ ] `classic` funciona sem torch (CI roda sem GPU).
- [ ] Teste do quad projetado: imagem sintética em perspectiva, erro de canto
      < 1% da diagonal.
- [ ] Teste máscara → polígono: IoU(polígono rasterizado, máscara) > 0,95 com
      ≤ N vértices.
- [ ] Re-segmentação mantém os ids das superfícies existentes (teste de IoU).
- [ ] SAM 2 roda no seu Windows (U4) ou há fallback documentado.

### F4 — Calibração automática por luz estruturada + edge blending

**Entrega:** "Calibrar" na UI. Cada nó projeta, em sequência, preto, branco e
os padrões Gray code (+ inversos). A webcam do mestre captura (sincronizada
por confirmação WS: projetou → esperou a estabilização → capturou). O mestre
decodifica, gera o mapa câmera↔projetor e resolve a homografia ou grade por
superfície. Com 2+ projetores, calcula as sobreposições e as máscaras de blend.

Tarefas: `calibrate/graycode.py` (E6), `procam.py`, `latency.py` (U5),
`mapping/blend.py` (pesos por distância à borda de cada footprint no espaço
da câmera, normalizados para soma 1, depois `w^(1/γ)` por projetor), passe
final do nó com LUT (E2) e máscara de blend. Edge blend **manual** (largura e
curva por borda) para quem não tem câmera.

**Aceite:**
- [ ] Teste Gray code: gerar → "fotografar" sinteticamente (homografia
      conhecida + blur + ruído + gama) → decodificar → homografia recuperada
      com erro de reprojeção < 0,5 px.
- [ ] Teste comparando com `cv2.structured_light` (quando o contrib estiver
      instalado).
- [ ] Teste de blend: soma dos pesos lineares = 1 ± 1e-3 na sobreposição;
      bordas contínuas.
- [ ] Calibração real de 1 projetor com webcam: erro médio < 2 px.

### F5 — Entrada NDI + controle PJLink

**Entrega:** fonte `ndi` por superfície (lista de fontes NDI na rede; cada nó
recebe direto do TouchDesigner, sem passar pelo mestre). Painel de projetores
com ligar/desligar, entrada, mute de AV, erros e status de lâmpada.

Tarefas: `content/ndi.py` (cyndilib, import tardio), modo "ao vivo" (NDI não
segue o timecode; latência mínima), `net/pjlink.py` (classe 1: `POWR`,
`INPT`, `AVMT`, `ERST`, `LAMP`, `NAME`; autenticação MD5) e spike U3 no Pi 5.

**Aceite:**
- [ ] Teste do PJLink contra um **servidor PJLink falso** (com e sem senha,
      `ERRA`, `ERR3`, timeout).
- [ ] NDI do TouchDesigner aparece numa superfície com latência medida e
      registrada.
- [ ] Senhas PJLink só no `.env`, nunca no `project.json` nem no log.

### F6 — Remote mobile + app Android (pedido extra, inspirado no seed42)

**Entrega:**
- **Rota `/remote`** responsiva: QR no mestre (URL + token). Cues/"looks",
  master dimmer por nó/superfície, blackout, play/pause, troca de fonte por
  superfície, energia via PJLink e status dos nós (fps, deriva, temperatura).
- **Rota `/capture`**: tirar a foto da posição do projetor pelo celular e
  enviá-la ao projeto (funciona via HTTP com `capture="environment"`).
- **App Android (Capacitor)**: mesma UI. Descoberta do mestre na LAN (mDNS
  via plugin ou digitando/escaneando o QR), câmera nativa e cleartext
  liberado só para IPs privados.
- Depois (opcional): celular no tripé como **câmera de calibração** (frames
  por WS), substituindo a webcam.

**Aceite:**
- [ ] Remote funciona em celular Android/iOS pelo navegador na mesma rede.
- [ ] APK de debug instala e controla o mestre; o build é documentado no README.
- [ ] Sem token → nenhum comando aceito (teste).

### F7 — (Opcional) Conteúdo gerado por IA por superfície

Conecta o ProjMap às factories que **já existem** neste repo
(`get_image_generator`: stability *control structure*, comfyui com ControlNet,
gemini; `get_video_generator`: Veo). Fluxo do ifnull: foto da posição →
geração estilizada que respeita a estrutura → recorte por superfície → mídia
no projeto. Também um "prompt → look" no remote, no espírito do seed42, mas
local-first.

---

### F8 — Camada interativa: IA + sensores + TouchDesigner (pedido extra)

**Entrega (MVP feito):**
- motor de interação com sensores `sim | osc (Kinect via TD) | webcam`;
- comportamentos perseguir, fugir, vagar, seguir o olhar e congelar quando
  olhado;
- texto → cena por LLM, com validação e fallback;
- render nativo como fonte de superfície;
- OSC para o TouchDesigner;
- card na UI.

O guia está em `projmap/interact/README.md`.

**Próximos:**
- validar com webcam e Kinect reais e nos scripts do TD;
- várias pessoas e várias paredes (modelo da sala em 3D);
- sons nos eventos;
- sprites gerados por IA (factories de imagem do repo);
- NDI do TD de volta para o ProjMap (F5).

## 4. Estratégia de testes (resumo)

| Área | Tipo | Exemplo |
|---|---|---|
| Homografia/geometria | unitário, propriedades | round-trip, casos degenerados, vs. OpenCV |
| Gray code | sintético ponta a ponta | gerar → câmera simulada → decodificar → H |
| Sincronia | simulação determinística | relógio falso + jitter com seed fixa → desvio em frames |
| Rede | integração local | mestre + 3 nós em processos, loopback |
| PJLink | servidor falso | auth, erros, timeout |
| Projeto | round-trip | salvar → carregar → igual |
| UI | `npm run build` | — |

Os testes de GPU (moderngl) rodam com contexto **standalone/EGL** quando houver
GPU e são *skip* sem ela. A lógica de agendamento e geometria é testada sem GPU.

## 5. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| U1: moderngl no Pi 5 | Nó Pi inviável com moderngl | Spike primeiro. Shaders GLSL ES 3.00. Fallback pyglet/GLES. Mini PC x86 como nó alternativo. |
| U2: CPU do Pi 5 para N vídeos | Frames perdidos | Perfil de transcodificação, modo baked e limite de fontes simultâneas por nó, avisado na UI. |
| Input lag diferente entre projetores | Dessincronia visível mesmo com relógio perfeito | `latency_ms` por nó, medido na F4 e ajustável à mão. |
| Wi-Fi com jitter alto | Offset ruidoso | Filtro por mínimo RTT. Recomendação de cabo para os nós. |
| SAM 2 pesado no Windows | F3 lenta ou quebrada | Fallback `classic` + checkpoints tiny/small + export ONNX. |
| Licenças | Contaminação GPL/AGPL | Lista de dependências aprovada (§6) e checada a cada fase. |

## 6. Dependências e licenças previstas

| Pacote | Licença | Onde |
|---|---|---|
| numpy, opencv-python(-contrib) | BSD / Apache-2.0 | mestre, testes |
| fastapi, uvicorn, pydantic, websockets | MIT/BSD | mestre, nó |
| python-zeroconf | **LGPL-2.1** (OK como biblioteca) | mestre, nó |
| python-osc | Unlicense | mestre, nó |
| moderngl / pyglet | MIT / BSD | nó |
| PyAV (FFmpeg LGPL nos wheels) | BSD-3 + LGPL | mestre, nó |
| Pillow | HPND | todos |
| torch, sam2 | BSD / Apache-2.0 | extra `ai` |
| cyndilib + NDI Runtime | MIT + **proprietária (não redistribuir)** | extra `ndi` |
| Capacitor | MIT | Android |
| **Evitar:** ultralytics (AGPL), mpv embutido (GPL), qualquer código do WZRD/ifnull (sem licença) | — | — |

## 7. Ordem sugerida e tamanho

F1 → F2 → F3 → F4 → F5 → F6 (F7 opcional, a qualquer momento depois da F3).
F6 pode subir para logo depois da F2, se o remote no celular for mais urgente
que a IA. Cada fase é entregue como um PR (ou um commit grande) com seu MD em
`docs/entregas/`.
