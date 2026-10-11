# ProjMap — Blueprint de engenharia reversa (Fase 0)

> Sistema de **projeção mapeada assistida por IA**, multi-projetor em rede.
> Este documento é o resultado da **Fase 0**: estudo das referências open
> source e de um produto comercial (seed42), destilado num blueprint de
> arquitetura, pipeline, algoritmos e formatos de dados.
> **Nenhuma linha de código foi copiada** — tudo será reimplementado do zero.
> O plano de execução está em [`PLANO.md`](PLANO.md) e **aguarda aprovação**.

---

## 0. Método (como o REA foi aplicado)

O pedido foi usar o **REA — Reverse Engineer Anything** (`morluto/rea`, MIT,
commit `b74d9a1bb2e6`). Li o README e o skill oficial
(`.agents/skills/reverse-engineer-anything/SKILL.md`). Duas conclusões:

1. **As ferramentas do REA não se aplicam a estes alvos.** O REA é um servidor
   MCP para inspecionar binários nativos, APK, .NET, Electron e páginas web
   *sem código-fonte*. O próprio skill diz: *"Skip REA for ordinary
   source-repository architecture analysis"* (SKILL.md, frontmatter e §"Use
   REA when…"). As três referências técnicas são repositórios com código-fonte.
2. **Não executei nada.** Rodar o REA exigiria `npx rea-agents` (pacote de
   terceiros) e, para alvos nativos, Hopper/Ghidra/IDA. Isso conflita com a sua
   regra *"nunca execute binários de repositórios desconhecidos"*. Os repositórios
   foram clonados com `git clone --depth 1` **só como dados** e lidos como texto.
   Nenhum script, build ou binário deles foi executado.

Mesmo assim, segui a **metodologia** do REA, que é o que ele tem de mais útil
aqui (SKILL.md §"Plan broader investigations"):

- transformar o pedido num **checklist de perguntas** e na evidência que cada
  uma exige (§1);
- manter um **ledger de achados** que separa **Observação** (lida no código,
  com `arquivo:linha` no commit fixado), **Inferência** (conclusão minha) e
  **Desconhecido** (o que exige spike/medição);
- no fim, marcar cada pergunta como respondida, parcial ou aberta (§9).

### Alvos e licenças (o que pode e o que não pode ser reaproveitado)

| Alvo | Commit lido | Licença | Consequência |
|---|---|---|---|
| `aiXander/WZRD` | `2abb6961ccb9` | **Sem arquivo de licença** → todos os direitos reservados | Só **ideias e algoritmos** (não são protegidos por copyright). Zero código, zero paráfrase próxima. |
| `ifnull/projection-mapping-workflow` | `f483852d2916` | **Sem arquivo de licença** | Só o **fluxo** (o que fotografar, quando e por quê). Os prompts dele não serão copiados. |
| `YCAMInterlab/mapamok` (Kyle McDonald) | `15f9df6d3af2` | MIT | Poderia ser reaproveitado com atribuição. Mesmo assim vamos reimplementar. |
| `opencv/opencv_contrib` → `modules/structured_light` | `eca97a4adb2f` | Apache-2.0 | Podemos usar o OpenCV como **dependência**. O Gray code será reimplementado em NumPy, e o OpenCV entra como oráculo nos testes. |
| seed42.app | — (produto fechado) | Proprietário | Só **conceitos de produto/UX**, observados de fora. Ver §6. |
| `morluto/rea` | `b74d9a1bb2e6` | MIT | Usado como metodologia, não como ferramenta (ver acima). |

**Atenção a GPL/AGPL nas dependências futuras** (detalhes em `PLANO.md §6`):
evitar `ultralytics` (AGPL) para o SAM, evitar embutir `mpv` (GPL por padrão) e
não redistribuir o NDI SDK (licença proprietária: o usuário instala o *NDI
Runtime*). `python-zeroconf` é LGPL-2.1, o que é OK como biblioteca dinâmica.

---

## 1. Checklist de perguntas (estilo REA)

| # | Pergunta | Evidência necessária | Status |
|---|---|---|---|
| Q1 | Como detectar, na foto, a área que o projetor ilumina? | código do WZRD `detect.py` | ✅ respondida |
| Q2 | Como alinhar uma foto "de dia" com a foto da projeção? | WZRD `align.py` | ✅ respondida |
| Q3 | Como representar regiões/superfícies de forma estável (re-segmentação)? | WZRD `layerpack.py` + docs | ✅ respondida |
| Q4 | Qual modelo de warp manual não "entorta" linhas retas? | WZRD `alignment.rs`, `warp_bake.wgsl`, docs §2.8/§7 | ✅ respondida |
| Q5 | Qual é o pipeline foto → IA → projeção, ponta a ponta? | README do ifnull | ✅ respondida |
| Q6 | Como codificar/decodificar Gray code projetor↔câmera? | OpenCV `graycodepattern.cpp` | ✅ respondida |
| Q7 | Como calibrar a partir de correspondências 2D↔3D (mapamok)? | `Mapamok.h`, `ofApp.cpp` | ✅ respondida |
| Q8 | Como rodar playback estável num Raspberry Pi? | ifnull README | ✅ parcial (sem sync) |
| Q9 | Como sincronizar N nós em rede? | nenhuma referência cobre isso | ⚠️ desenho próprio (§5.4) |
| Q10 | O que o seed42 faz (web/celular/Android)? | página pública; o acesso direto foi bloqueado pelo proxy | ⚠️ parcial (§6) |
| Q11 | O renderer GLSL do nó roda no Pi 5? | só medindo no hardware | ❓ desconhecido → spike na F2 |

---

## 2. WZRD (aiXander) — "additive projection mapping"

### 2.1 Arquitetura observada

- **O:** três partes: toolkit Python offline (`wzrd/`), engine em tempo real em
  Rust + wgpu (`render-core/`) e shell Tauri/React (`wzrd-app/`). Fonte:
  `README.md` (topo) e `docs/reference/render-engine.md` §1.
- **O:** o contrato offline→runtime é um **layer pack**: `pack.json`, `masks/`
  (PNG em tons de cinza com antialiasing, na resolução do projetor),
  `surface.png` e `references/`. Fonte: `wzrd/layerpack.py:1-60`.
- **O:** as máscaras ficam num único `Texture2DArray<R8>`, com limite de 256
  camadas. Fonte: `render-engine.md` §"Load-bearing decisions" D3/D4 e
  `layerpack.py` (`MAX_LAYERS = 256`).
- **O:** o controle é feito por JSON-RPC via WebSocket (`ws://127.0.0.1:9123`).
  O áudio chega por OSC (`:9000`) de outro processo. Fonte: `render-engine.md` §1.
- **O:** a mistura é **aditiva** (`One + One` num composite `Rgba16Float`). O que
  não muda fica preto, e o preto "some" na superfície física. Fonte:
  `render-engine.md` (parágrafo após D-table).
- **O:** decisão D1: *"the browser never renders the projector output"*.
  Fonte: `render-engine.md` §1 e §7.

### 2.2 Detecção da área projetada (Q1)

**O** — `wzrd/detect.py:402-525` (`detect_projection_optimized`):

1. Reduz a imagem para no máximo 512 px (velocidade).
2. Calcula o brilho combinado: `max(luminância, brilho reforçado por saturação)`.
   Assim, projeção colorida saturada também conta como "clara".
3. Aplica um blur gaussiano grande (cerca de 8% da dimensão) para obter um
   gradiente suave.
4. Extrai a **cor dominante da projeção** (média HSV dos pixels acima do
   percentil 50 de brilho, `detect.py:134-195`) e monta um **mapa de proximidade
   de cor** com decaimento suave (`detect.py:196-271`).
5. Aplica **Otsu** (`detect.py:316`), fechamento morfológico com kernel
   elíptico (`:330-332`) e pega o **maior contorno** (`:341-349`). Rejeita
   o contorno se ocupar menos de 15% da imagem.
6. Calcula `convexHull` → `minAreaRect` → 4 cantos ordenados TL, TR, BR, BL
   (`:371-373`, `order_points` em `:38`).
7. Faz `iterative_detection` (`:526-614`): tenta outros fatores de blur
   (0,08 / 0,06 / 0,10 / 0,12) e rejeita detecções "coladas na borda" da foto.
8. Aplica uma margem opcional para dentro (`:615`) e uma correção de proporção
   (`:676`).

**I (melhoria nossa):** `minAreaRect` devolve um **retângulo**, mas um projetor
sem keystone, visto de fora do eixo, ilumina um **quadrilátero qualquer**. No
nosso detector, depois do hull, vamos usar `approxPolyDP` com busca de epsilon
até chegar a 4 vértices. Depois refinamos cada lado com `fitLine` sobre os
pontos do hull e intersectamos as retas. `minAreaRect` fica só como fallback.
O teste usa um quad sintético com perspectiva conhecida e exige erro de canto
abaixo de 1% da diagonal.

### 2.3 Alinhamento de imagens (Q2)

**O** — `wzrd/align.py:371-482` (`align_images`), em três estágios:
(1) features + razão de Lowe 0,75 + homografia (`:205-281`); (2) se falhar,
template matching multiescala sobre bordas/gradiente com CLAHE (`:52-200`);
(3) refino subpixel com **ECC** (`:325-352`). Há validação da homografia
(`:282-312`) que rejeita matrizes degeneradas ou espelhadas.

**I:** isso serve para levar a "foto de dia" (boa para a IA segmentar) até o
enquadramento da "foto com projeção branca" (que define o que o projetor
alcança). Vamos reimplementar com ORB/AKAZE + RANSAC + ECC (todos do OpenCV)
e com a mesma checagem de sanidade da matriz.

### 2.4 Regiões estáveis e máscaras (Q3)

- **O:** cada camada tem um `id` **semântico** estável (`trunk`, `leaf_a`). O
  nome do arquivo da máscara é detalhe de implementação. Também há `tags`,
  `group`, `parent`, `z` e `source_box`. Fonte: `layerpack.py:21-60`,
  `render-engine.md` §2.2.
- **O:** os autores registram como requisito em aberto *"re-importar uma nova
  segmentação SAM2 sobre a tabela de identidade existente — casar por
  sobreposição, expor splits/merges"*. Sem isso, cada nova foto invalida as
  cenas. Fonte: `render-engine.md` §2.2.
- **O:** a segmentação atual deles é por **cor** (k-means em CIELAB →
  "islands"), não por SAM. Fonte: `wzrd/islands.py:142-376`.

**I:** o nosso modelo de dados já nasce com `surface.id` estável e uma etapa de
**reconciliação por IoU** quando o usuário re-segmenta (casar máscaras novas
com as superfícies existentes, com limiar de IoU de 0,5, e mostrar a diferença
para revisão).

### 2.5 Warp manual que mantém retas retas (Q4) — a lição mais importante

**O** — `render-core/src/alignment.rs:1-35` e `render-engine.md` §2.8:

- Modelo `W(x) = H⁻¹(x) + R(x)`: a base é a **homografia exata dos 4 cantos**
  (Heckbert) e `R` é um **resíduo local** (RBF Wendland C², raio por alça,
  resolvido por LU denso com N ≤ 64).
- Abordagem rejeitada explicitamente (§7): ajustar spline, MLS ou malha
  *diretamente* pelos 4 cantos. O resultado é afim + flexão, não perspectiva:
  *"straight edges bow and the image never sits flat on a keystoned wall"*.
- O warp é **"assado" num LUT** de offset (`Rg32Float`, tamanho da saída), e só
  quando muda (`warp_bake.wgsl`). Por frame, o custo é **uma leitura de texel**,
  seja qual for o número de alças. O LUT também é o ponto de extensão para um
  mapa denso vindo de câmera.
- Propriedades de UI: adicionar uma alça em `W_atual(dest)` não altera nada (o
  coeficiente é zero), e arrastar um canto leva junto as alças extras.

**I (adotado no nosso desenho):** todo warp de superfície = **homografia base +
correção local** (grade/Bézier como *offset* sobre a base projetiva, nunca
substituindo a base). No nó, o warp final de cada projetor (calibração densa)
também vira **LUT assado**. As malhas Bézier/grade de cada superfície são
avaliadas na CPU, numa malha fina, e só reenviadas quando editadas.

### 2.6 O que **não** vamos herdar do WZRD

- O engine em Rust/wgpu e o shell Tauri: o requisito pede Python +
  moderngl/pyglet nos nós e Windows/Linux/Pi.
- A mistura **aditiva** como regra global. Para nós ela será um *modo de mistura
  por superfície* (`normal | add | multiply`), porque o requisito é mapeamento
  geral (paredes, palco), não só o efeito "criatura viva".
- O HAP (DXT/BC): a GPU do Pi 5 (V3D) **não tem compressão BC**, então não há
  HAP no nó Pi. Ver PLANO §5.

---

## 3. ifnull/projection-mapping-workflow — pipeline foto → IA → projeção (Q5, Q8)

**O** (README, seções "Terms", "Designing the Scene", "Projection Alignment",
"Playback Improvements"):

| Artefato | Quando | Para quê |
|---|---|---|
| *Structure Reference Image* | de dia, **da posição do projetor** | geometria e contexto para a IA |
| *Projection Boundary Image* | à noite, projetando **branco total**, sem keystone | define exatamente a área alcançável |
| *Alignment Image* | gerada (P&B, bordas grossas) | conferir o alinhamento na parede |
| *Scene Base Image* | gerada (estilizada) | o conteúdo final |

- **O:** a geração usa Stability *Control Structure*
  (`v2beta/stable-image/control/structure`, `control_strength` em torno de
  0,8–0,95) com "perfis" YAML (prompt + negative + força).
  Fonte: `sdsc-wrapper.py:43-80`, `profiles/alignment_bw.yml`.
- **O:** as regras práticas são: não usar keystone do projetor (corrigir no
  mapeamento), não mexer no tripé entre as fotos, mascarar cedo e exportar na
  resolução exata do projetor.
- **O:** o playback "à prova de falhas" é um Raspberry Pi tocando **um único
  vídeo já pronto** em loop (`mpv --loop-file`), via systemd. Não há sincronia
  entre projetores.

**I:**
- A *Alignment Image* **não precisa de IA**. Um Canny/realce de bordas local
  sobre a foto produz a mesma referência de alinhamento, sem custo e sem
  internet. Entra como modo "padrão de alinhamento" no editor.
- A geração estilizada por superfície encaixa direto no que este repositório
  já tem: a factory `agents.media.get_image_generator` já tem os providers
  `stability`, `comfyui` (ControlNet local) e `gemini`. Proposta opcional:
  F7 no PLANO.
- O "vídeo único pronto por projetor" do ifnull vira o nosso **modo baked**: o
  mestre pré-renderiza o canvas do projetor (todas as superfícies com warp e
  blend), e o nó só toca um vídeo, sincronizado pelo relógio comum. É o modo
  mais robusto para o Pi 5. O **modo ao vivo** compõe N fontes no nó.

---

## 4. Calibração: Gray code (OpenCV) e mapamok (Q6, Q7)

### 4.1 Gray code — `structured_light/src/graycodepattern.cpp`

**O:**
- **Número de padrões:** `ceil(log2(W))` colunas + `ceil(log2(H))` linhas,
  **cada um com o inverso**, mais uma imagem branca e uma preta.
  Fonte: `:126-210` (`generate`), `getImagesForShadowMasks`.
- **Geração:** o bit `k` da coluna `j` vale `bit_k(j) XOR bit_{k+1}(j)`
  (Gray = `j ^ (j >> 1)`). Os padrões são gravados do MSB para o LSB.
  Fonte: `:138-170`.
- **Máscara de sombra:** um pixel da câmera só é válido se
  `branco − preto > blackThreshold` (padrão 40). Fonte: `:323-357`, `:122`.
- **Decodificação por pixel da câmera:** para cada bit, compara o padrão com o
  inverso (`val1 > val2` → 1). Se `|val1 − val2| < whiteThreshold` (padrão 5),
  o pixel é marcado como **erro**. Depois converte Gray→decimal por XOR
  acumulado e descarta resultados fora da resolução. Fonte: `:370-445`.
- **O:** o `decode()` público do OpenCV é voltado para **estéreo com 2 câmeras**
  (gera um mapa de disparidade). Para projetor↔câmera, o que serve é o
  `getProjPixel` pixel a pixel. Fonte: `:212-260`.

**I (o nosso decodificador):**
- Vetorizado em NumPy: todos os bits de uma vez, Gray→binário por XOR
  cumulativo e **confiança** por pixel = `min_k |p_k − inv_k|`.
- **Bits finos não resolvidos:** quando a câmera tem menos resolução que o
  projetor, as listras de 1–2 px viram ruído. Vamos medir o contraste por
  nível de bit e **descartar os LSBs** sem contraste (decodificando blocos de
  2ᵏ px), em vez de aceitar lixo.
- **Inverter o mapa:** o resultado é câmera→projetor (esparso). Para cada
  superfície (máscara na imagem da câmera) ajustamos uma **homografia RANSAC**
  (superfície plana) ou amostramos uma **grade** (superfície não plana) →
  projetor. Os buracos são preenchidos por interpolação.
- **Oráculo de teste:** se o `opencv-contrib-python` estiver instalado,
  comparamos o nosso decode com `cv2.structured_light` nas mesmas imagens
  sintéticas.

### 4.2 mapamok — calibração por correspondência 2D↔3D

**O** — `SharedCode/Mapamok.h:13-48`, `mapamok-original/src/ofApp.cpp:381-450`:
- O usuário clica em pelo menos **6** pares (vértice do modelo 3D ↔ pixel do
  projetor).
- `calibrateCamera` com chute de intrínsecos (`f ≈ largura·aov`, centro óptico
  no meio), `USE_INTRINSIC_GUESS | FIX_ASPECT_RATIO | FIX_K1..K3`, ou seja,
  sem distorção de lente. O resultado é `rvec`/`tvec` → matriz de modelo, e os
  intrínsecos → matriz de projeção do OpenGL.
- O projetor é tratado como uma **câmera invertida** (modelo pinhole).

**I:** isso pede um **modelo 3D** da cena, que o requisito não exige. Vamos
guardar a ideia para um modo futuro "mapeamento 3D" (pós-F5). O conceito
reaproveitado já agora é: *projetor = câmera pinhole*. Com Gray code + câmera
calibrada, dá para estimar a pose do projetor em superfícies não planas. Na
F4 fica como opção "avançado".

---

## 5. Blueprint do sistema (síntese)

### 5.1 Componentes

```mermaid
flowchart LR
  subgraph MESTRE["MESTRE (PC Windows) — FastAPI"]
    UI[UI web: editor de malha sobre a foto]
    PRJ[(Projeto: project.json + media/)]
    DET[detect/: SAM 2 | OpenCV]
    CAL[calibrate/: Gray code + homografia/grade]
    MAP[mapping/: quads, grade, Bézier, máscaras, blend]
    CLK[net/clock: servidor de tempo OSC/UDP]
    DISC[net/discovery: zeroconf browse]
    PJ[net/pjlink: TCP 4352]
    MED[HTTP /media/sha256]
  end
  subgraph NO1["NÓ 1 (Pi 5 / mini PC)"]
    R1[node/: janela GLSL tela cheia]
    S1[fontes: vídeo, GIF, imagem, NDI]
  end
  CEL[Celular / app Android: controle remoto + câmera]
  TD[TouchDesigner] -- NDI --> S1
  UI --- PRJ
  DISC -. mDNS _projmap._tcp .- NO1
  MESTRE == WS: config/comandos ==> NO1
  MED == HTTP pull + hash ==> NO1
  CLK == OSC/UDP: sync de relógio + timecode ==> NO1
  PJ == PJLink ==> PROJ1[(Projetor 1)]
  NO1 -- HDMI --> PROJ1
  CEL == HTTPS/WS LAN ==> UI
```

### 5.2 Espaços de coordenadas (base de toda a matemática)

| Espaço | Origem | Uso |
|---|---|---|
| **foto_i** | foto tirada da posição do projetor *i* | modo manual: o usuário desenha as superfícies aqui |
| **câmera** | webcam fixa da calibração | modo automático: espaço comum a todos os projetores (é nele que o blend é calculado) |
| **projetor_i** | pixels de saída do nó *i* (ex.: 1920×1080) | onde o warp final acontece |
| **conteúdo** | uv `[0,1]²` de cada fonte | recorte/ajuste da mídia por superfície |

As relações são `H_foto→proj` (manual: 4 cantos ajustados na UI) ou
`M_cam→proj` (automático: Gray code). Cada superfície guarda o polígono no
espaço de origem e o warp resolvido no espaço do projetor.

### 5.3 Pipeline do nó (por frame)

```
fontes (vídeo/GIF/imagem/NDI) ──► textura por superfície
  ► malha da superfície (homografia base + offset grade/Bézier, uv projetivo)
  ► máscara da superfície (polígonos rasterizados + feather)
  ► composite do projetor (normal/add/multiply)
  ► passe final: LUT de calibração densa (opcional) × máscara de edge blend (gama)
  ► swapchain (vsync)
```

Para a homografia ficar correta numa malha de 2 triângulos, as coordenadas de
textura usam **uv projetivo** (coordenada `q`, `textureProj`). Sem isso aparece
a "dobra" diagonal da interpolação afim.

### 5.4 Sincronia (Q9 — desenho próprio, nenhuma referência cobre)

1. **Relógio comum:** cada nó faz trocas estilo NTP com o mestre por OSC/UDP
   (`/clock/ping t0` → `/clock/pong t0 t1 t2`, 2 Hz). O offset é estimado pela
   **mediana das 8 amostras de menor RTT** numa janela, o que filtra o jitter
   do Wi-Fi.
2. **Timecode:** o mestre não manda "frame atual". Manda o **contrato de
   playback**: `{cue_id, t0_master, rate, loop, duration}`. Cada nó calcula
   localmente `pos = (agora_master − t0_master)·rate mod duração`, a cada
   vsync. O mestre reenvia esse contrato via OSC a 5 Hz (redundância/
   late-join) e via WS (confirmação).
3. **Compensação de latência:** `agora_master = relógio_local + offset +
   latência_saída_nó`. O último termo é o **input lag do projetor/TV**, que
   varia de 16 a 100 ms entre modelos. Ele é medido na calibração (flash +
   câmera) ou ajustado à mão.
4. **Correção de deriva do vídeo:** o decoder corre à frente num buffer. Se o
   frame decodificado se afastar de `pos` por mais de ½ frame, o nó repete ou
   pula um frame. Acima de 0,5 s, faz seek.
5. **Medição (meta: < 1 frame a 30 fps = 33,3 ms):** cada nó registra
   `(t_master no vsync, índice do frame exibido)`. Um script compara os nós e
   reporta p50/p95/máximo do desvio em frames. Na F2 (3 janelas no mesmo PC)
   injetamos **offset artificial de relógio e jitter de rede** por nó. Sem isso
   o teste seria trivial, porque as janelas compartilham o mesmo relógio.

### 5.5 Formatos de dados

**Projeto em disco** (`<nome>.projmap/`, exportável como `.pmz` = zip):

```
meu-show.projmap/
  project.json          # esquema versionado (pydantic), migrável
  media/<sha256>.<ext>  # mídia endereçada por conteúdo (sem duplicatas)
  captures/<node>/      # fotos por projetor, capturas de Gray code
  calibration/<node>.npz  # mapas densos cam↔proj, LUTs
  masks/<surface>.png   # máscaras raster opcionais (as da IA)
```

**`project.json` (v1, resumido):**

```json
{
  "version": 1,
  "name": "Fachada Halloween",
  "fps": 30,
  "nodes": [{
    "id": "proj-esq", "name": "Projetor esquerdo",
    "output": {"width": 1920, "height": 1080, "latency_ms": 45},
    "photo": "captures/proj-esq/ref.jpg",
    "pjlink": {"host": "192.168.0.50", "port": 4352, "password_env": "PJLINK_PROJ_ESQ"},
    "calibration": {"mode": "manual|graycode", "file": "calibration/proj-esq.npz"},
    "blend": {"gamma": 2.2, "edges": {"right": {"width_px": 240, "curve": 0.5}}}
  }],
  "surfaces": [{
    "id": "coluna-1", "label": "Coluna 1", "node_id": "proj-esq", "z": 0,
    "polygon_src": [[0.41,0.22],[0.47,0.22],[0.47,0.88],[0.41,0.88]],
    "warp": {
      "base": [[812,140],[905,138],[910,990],[808,995]],
      "type": "homography|grid|bezier",
      "grid": {"cols": 4, "rows": 8, "offsets": [[0,0]]}
    },
    "masks": [{"polygon": [[0.1,0.1],[0.2,0.1],[0.2,0.3]], "invert": false, "feather_px": 6}],
    "source": {"kind": "video|image|gif|ndi|color|test", "media": "sha256:…", "ndi_name": "TD (out1)",
               "fit": "cover|contain|stretch", "crop": [0,0,1,1], "loop": true},
    "opacity": 1.0, "blend_mode": "normal"
  }],
  "cues": [{"id": "abertura", "surfaces": {"coluna-1": {"media": "sha256:…"}}}]
}
```

**Protocolo mestre↔nó:**

| Canal | Transporte | Mensagens |
|---|---|---|
| Descoberta | mDNS `_projmap-node._tcp.local.` | TXT: `id`, `ver`, `res`, `caps=video,gif,ndi`, `gl` |
| Controle | WebSocket (nó é servidor, `:8765`), JSON | `hello{token}`, `apply_config{rev,hash,node_cfg}`, `media_sync{[sha256,url,size]}`, `cue{…contrato…}`, `pause`, `blackout`, `test_pattern{kind,idx}`, `identify`; nó → `status{fps,temp,drift_ms,missing_media}` |
| Mídia | HTTP GET `master:/media/{sha256}` | o nó baixa, confere o hash e mantém em cache. Nada toca até a mídia estar completa. |
| Relógio/TC | OSC sobre UDP | `/clock/ping`, `/clock/pong`, `/tc/contract` |
| Projetores | PJLink classe 1, TCP 4352 | `%1POWR 1/0/?`, `%1INPT 31/?`, `%1AVMT`, `%1ERST ?` + autenticação MD5 |

**Segurança na LAN:** o nó só aceita comandos com o **token de pareamento** do
projeto (gerado no mestre e mostrado como QR). As senhas de PJLink ficam só no
`.env`. O `project.json` guarda apenas o *nome* da variável (regra do CLAUDE.md).

---

## 6. seed42.app — "turn the whole room into the show" (Q10)

**Limite da investigação:** o acesso direto a `www.seed42.app` foi **bloqueado
pelo proxy de rede deste ambiente** (DNS/CONNECT 403). As observações vêm do
texto público indexado pela busca (página inicial e `/login.html`, "Early
Access"). É o equivalente REA a "observação de marketing, não verificada em
runtime".

**O (página pública):**
- Ferramenta de **visuais generativos com IA em tempo real**, reativos a áudio,
  para música e eventos. Está em beta fechado.
- Roda **no navegador**, sem instalação. O laptop ligado ao projetor/TV
  mostra a saída, e **o celular abre um link de "remote"**.
- Entrada de câmera: **celular, webcam ou qualquer feed**. Também aceita
  vídeo, imagens, formas e ruído.
- Pelo celular: **trocar "looks" salvos** e **ajustar intensidade**.
- Grava o set. Precisa de internet estável (processamento em nuvem).
- Um app nativo dedicado é prometido "para depois".

**I — o que trazer para o ProjMap (pedido: "web no celular ou app Android"):**

| Conceito seed42 | Tradução no ProjMap |
|---|---|
| Link de remote no celular | **Controle remoto mobile**: o mestre mostra um **QR** (URL + token). O celular controla cues/"looks", intensidade (master dimmer por nó/superfície), blackout, play/pause, fonte por superfície e liga/desliga via PJLink. |
| Celular como câmera | **Captura pelo celular**: foto da posição de cada projetor direto para `captures/` (requisito 1). Depois (F6+), o celular no tripé como câmera de calibração Gray code, enviando frames por WebSocket. |
| Looks salvos | **Cues** no `project.json` (snapshot de fonte/opacidade por superfície). |
| Sem instalação | A UI do mestre é web e responsiva. O nó continua nativo, porque precisa de GLSL em tela cheia e de sincronia. |
| Visual por prompt | Opcional (F7): gerar conteúdo por superfície com os providers de imagem/vídeo **já existentes** neste repo. Diferença deliberada: **local-first**, sem exigir nuvem. |

**I — restrição técnica importante para o celular:** navegadores só liberam
**câmera (`getUserMedia`), service worker e instalação de PWA em contexto
seguro (HTTPS)**. Numa LAN servida por `http://192.168.x.x`, isso não funciona.
Por isso a proposta (PLANO, decisão D6) é:
1. **Web mobile** responsiva, sem depender de contexto seguro: o
   `<input type="file" accept="image/*" capture="environment">` funciona via
   HTTP e já resolve a foto do projetor;
2. **App Android com Capacitor** empacotando a mesma UI. O app tem câmera
   nativa e fala com o mestre na LAN (cleartext liberado só para faixas
   privadas no `network_security_config`). Um TWA foi descartado, porque exige
   domínio HTTPS público.

---

## 7. Decisões de engenharia derivadas (resumo)

| # | Decisão | Origem |
|---|---|---|
| E1 | Warp = **homografia base + correção local**; nunca spline direto nos 4 cantos | WZRD §2.8/§7 |
| E2 | Warp de calibração densa **assado em LUT** e reassado só quando muda | WZRD `warp_bake.wgsl` |
| E3 | O navegador **não** renderiza a saída do projetor; ele só faz preview (WebGL2 com o mesmo GLSL ES 3.00 do nó) | WZRD D1 |
| E4 | IDs de superfície semânticos e estáveis + reconciliação por IoU ao re-segmentar | WZRD §2.2 |
| E5 | Detecção da área projetada: brilho+saturação → proximidade de cor → Otsu → maior contorno → **quad por approxPolyDP/fitLine** (melhoria sobre `minAreaRect`) | WZRD `detect.py` + inferência |
| E6 | Gray code com inversos + máscara de sombra + confiança por pixel + descarte de LSBs sem contraste | OpenCV `graycodepattern.cpp` + inferência |
| E7 | Duas fotos por projetor (dia = estrutura, noite/branco = limite) + padrão de bordas local para conferir o alinhamento | ifnull |
| E8 | Modo **baked** (1 vídeo por nó) além do modo ao vivo, pela robustez no Pi | ifnull (playback no Pi) |
| E9 | Relógio comum estilo NTP + contrato de playback + latência por nó | desenho próprio |
| E10 | Remote mobile por QR + captura pelo celular + Capacitor no Android | seed42 + restrição de contexto seguro |
| E11 | Projetor = câmera pinhole (mapamok), para o modo 3D futuro | mapamok |

## 8. Desconhecidos (exigem spike ou medição)

| # | Desconhecido | Como resolver | Fase |
|---|---|---|---|
| U1 | O moderngl roda no **Pi 5** (V3D: GLES 3.1 / GL 3.1, e o moderngl pede GL 3.3 core)? | Spike: `moderngl` via EGL/GLES no Pi 5. Fallback: pyglet 2 com GLES. Shaders escritos em GLSL ES 3.00 para servirem às duas opções. | F2 (antes de fechar o nó) |
| U2 | O Pi 5 **não tem decoder H.264 por hardware** (só HEVC). Quantos vídeos 1080p30 cabem na CPU? | Medir PyAV com 1, 2 e 4 vídeos. Se não couber: modo baked ou mini PC. | F2 |
| U3 | NDI no Pi 5 (aarch64): desempenho de receber 1080p "full NDI" | Spike com NDI\|HX vs full. Recomendar mini PC para nós NDI se necessário. | F5 |
| U4 | SAM 2 no Windows (PyTorch/CUDA; o repo oficial recomenda Linux/WSL) | Testar `SAM2_BUILD_CUDA=0` no Windows. Alternativa: export ONNX/CPU. | F3 |
| U5 | Input lag real dos projetores do usuário | Medição por flash + câmera na calibração | F4 |
| U6 | Funcionalidades reais do seed42 além da página pública | Acesso ao beta (pelo usuário) | — |

## 9. Fechamento do checklist

Q1–Q7 **respondidas** com evidência em código. Q8 **parcial**: o ifnull cobre
playback estável, não sincronia. Q9 é **desenho próprio** e será validada por
medição na F2. Q10 **parcial**: página pública apenas. Q11 **aberta**: spike
U1 no hardware. Nenhuma pergunta obrigatória para *iniciar* a F1 está em
aberto. U1/U2 bloqueiam apenas o fechamento da F2 no hardware real, não o
início.
