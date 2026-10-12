# ProjMap — Efeitos do visual_frames, fase 1 (Luz reativa, LEGO, Ecos em quadrinhos)

## Resumo
Os efeitos visuais do projeto **visual_frames** (Adriel Vasques, usado com
permissão) entram no menu **Interativo** do ProjMap e rodam no Windows com a
C920. O trabalho do autor é **importado**: o shader GLSL roda sem nenhuma
alteração, e os modelos YOLO26 dele vão direto para o ONNX Runtime. A visão e
o áudio, que eram C++ só para Linux, foram traduzidos com fidelidade.

## Motivação
O usuário pediu para usar os efeitos do visual_frames nos visuais interativos
"apenas importando o trabalho que foi feito". O app original é
openFrameworks/C++ só para Linux (V4L2, PulseAudio, CUDA); o ProjMap roda no
Windows.

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/effects/importar.py` | Extrai o `FRAGMENT_SHADER` do `ofApp.cpp` e copia os modelos para `~/.projmap/visual_frames` (fora do git), com `ORIGEM.txt` (commit) |
| `projmap/effects/detector.py` | Tradução de `DetectorPessoas.cpp`: letterbox 640×384, seg + pose, máscara só na caixa (`warpAffine` com meio pixel), casamento por IoU; DirectML/CUDA/CPU |
| `projmap/effects/tracker.py` | `FiltroUmEuro.h` + `RastreadorPessoas.cpp` (ByteTrack em 2 etapas, slots estáveis, velocidade dos pulsos) |
| `projmap/effects/vision.py` | `ProcessadorVisao.cpp`: composição por maior logit, sigmoid, **filtro guiado** (em NumPy; o original usa o `ximgproc`), mistura temporal; estilo HQ (XDoG + bilateral + 3 tons) |
| `projmap/effects/audio.py` | `AnalisadorAudio.cpp`: FFT 2048/1024, bandas com ganho automático, batida de Patin; captura por **loopback WASAPI** (`soundcard`) |
| `projmap/effects/engine.py` | Partes do `ofApp.cpp`: ecos (histórico de máscaras), ganho da câmera (LEGO), matiz e carimbo pela música, fade entre efeitos, centro da cena; contexto GL fora da tela roda o shader e devolve RGBA |
| `projmap/effects/config.py` · `catalog.py` | Parâmetros de `Configuracao.h`; catálogo do menu |
| `projmap/interact/runtime.py` · `api.py` | `set_effect()` (sobe o motor sob demanda, assume a câmera); `GET/POST /api/interact/effects`, `PATCH /effects/params`; superfícies `interactive` mostram o efeito |
| `projmap/master/__main__.py` | Repassa `--camera` ao motor |
| `projmap/ui/app/components/EffectsSection.tsx` (+ `InteractPanel`, `api.ts`, `types.ts`) | Seção "Efeitos visuais" no card Interativo, com os ajustes do painel original |
| `requirements-projmap-master.txt` · `GUIA.md` · `board/seed.py` | Dependências, guia e cards |
| `tests/projmap/test_effects.py` | 12 testes |

## Como funciona
1. **Visão** (thread): câmera → YOLO seg + pose → ByteTrack → máscara
   `(360, 640, 2)` = [alpha, slot+1] → resultado publicado.
2. **Áudio** (thread): o que toca no PC → grave/médio/agudo/batidas.
3. **Motor** (thread com contexto OpenGL próprio): sobe máscara, ecos,
   carimbo, quadrinho e câmera como texturas e passa os mesmos uniforms do
   `desenharEfeitos()` original. O shader importado desenha a 60 fps num FBO,
   que é lido como RGBA. Linha 0 do FBO = topo da câmera, então não é
   preciso virar a imagem.
4. **ProjMap:** `InteractionRuntime.render()` devolve o quadro do efeito; a
   superfície "Cena interativa" aplica o warp/blend como qualquer vídeo.

**Diferenças em relação ao original, por plataforma:**
- O DirectML não aceita as duas redes ao mesmo tempo, então elas rodam em
  sequência (~10 ms numa RTX 4060, contra ~17 ms do original numa GTX 1660 Ti).
- O filtro guiado foi reimplementado (He et al., 2010), porque o
  `opencv-python` não tem o `ximgproc`.
- O centro da cena usa o nariz no lugar da cabeça do bichinho (fase 2).

## Como validar
```bash
python -m projmap.effects.importar ../visual_frames
pytest -q                                   # 435 verdes (12 novos)
python -m projmap.master --project shows/x.projmap --windowed --open
# Interativo → Efeitos visuais → LEGO; superfície com fonte "Cena interativa"
```
Verificado na máquina do usuário (RTX 4060 + câmera do notebook; a C920 não
estava conectada):
- o shader do autor compila sem alterações (34 uniforms);
- YOLO no DirectML: seg 4,6 ms e pose 5,0 ms;
- detecção ao vivo com 94% de confiança;
- os três efeitos foram renderizados com a câmera real, inclusive numa
  superfície em perspectiva pelo renderer do ProjMap;
- o áudio detectou 22 batidas de um bumbo de 120 BPM simulado;
- loopback conectado aos alto-falantes Realtek.

## Critério de aceite
- [x] Trabalho do autor importado (shader + modelos), não reescrito
- [x] Luz reativa, LEGO e Ecos em quadrinhos no menu Interativo, em qualquer superfície
- [x] Música do PC muda as cores (loopback WASAPI)
- [x] Roda no Windows com GPU (DirectML); câmera C920 escolhida sozinha
- [x] `pytest -q` verde e `npm run build` ok
- [ ] Testado com a C920 e o projetor no espaço real
- [ ] Fase 2: Bichinho espelho e Paraquedas

## Pendências / próximos
- **Fase 2:** Bichinho (dinâmica de 2ª ordem, IK de dois ossos, rabo Verlet)
  e Paraquedas (cena + rostos).
- Visão a ~15–25 fps quando o motor desenha ao mesmo tempo (contenção de
  CPU/GIL). Dá para levar a visão para outro processo se for preciso.
- Contexto GL fora da tela usa a GPU integrada (Intel). Num notebook híbrido,
  forçar a NVIDIA no Painel de Controle da NVIDIA para o `python.exe` deixa
  mais folga.
