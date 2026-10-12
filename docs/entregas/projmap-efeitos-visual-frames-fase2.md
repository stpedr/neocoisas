# ProjMap — Efeitos do visual_frames, fase 2 (Bichinho espelho, Salto de paraquedas)

## Resumo
Os dois efeitos que faltavam do **visual_frames** (Adriel Vasques, usado com
permissão) entram no menu *Interativo*: **Bichinho espelho** (a pessoa vira um
gato, dinossauro ou coelho) e **Salto de paraquedas** (paraquedistas com o rosto
de quem está na câmera). Com isso os **5 efeitos do autor** estão no ProjMap.
Junto vão três otimizações **medidas**, que tiram ~11 ms do quadro da visão.

## Motivação
"Era pegar todos os efeitos do Adriel que não tinha, faltou o do paraquedas e
outros." A fase 1 trouxe Luz reativa, LEGO e Ecos; o `EstadoPainel.h` original
lista cinco (`Luz, Bichinho, Ecos, Paraquedas, Lego`).

E: "não dá pra rodar no CUDA? fica mais fluido, atualmente está mt travado."
Medi antes de mexer — **não era o CUDA** (ver *Performance* abaixo).

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/effects/dynamics.py` | **Novo**: `DinamicaSegundaOrdem.h` (massa-mola-amortecedor do t3ssel8r) + `aproximar`, `smoothstep`, `normalizar` |
| `projmap/effects/critter.py` | **Novo**: `atualizarBichinho()` + `atualizarRig()` — cabeça suavizada, molas das orelhas, pupilas *googly*, piscar, rig chibi por *retargeting*, squash & stretch, rabo em corrente de Verlet |
| `projmap/effects/faces.py` | **Novo**: `recortarRostos()` — recorte 256×256 endireitado, CLAHE no canal L do Lab e leve nitidez; só atualiza com o rosto de frente |
| `projmap/effects/parachutes.py` | **Novo**: `Paraquedistas.cpp` — avião, nuvens em paralaxe, morro, velame com gomos e cordas, fases queda livre → paraquedas → pouso; desenhado com OpenCV |
| `projmap/effects/engine.py` | `NUM_ELOS_RABO` **6 → 8** (o shader usa 8); personagem por slot; uniforms `cabeca/corpo/extra/rig1/rig2/rig3/bracos/raboPontos`; `efeitoBichinho`, `efeitoFundo`, `animal`; cena dos paraquedistas por cima do shader |
| `projmap/effects/tracker.py` | Índices dos 17 keypoints (antes só os pulsos) |
| `projmap/effects/catalog.py` | `vf-bichinho` e `vf-paraquedas` |
| `projmap/effects/vision.py` | `_flatten_colors()`: bilateral em meia resolução (**10,2 → 0,9 ms**) |
| `projmap/effects/detector.py` | `preprocess` com buffer fixo + `blobFromImage` (**2,9 → 1,4 ms**, bit a bit igual); `PROJMAP_EFFECTS_PROVIDER` para forçar `cuda`/`cpu` |
| `projmap/ui/.../EffectsSection.tsx`, `types.ts` | Escolha do animal, fundo colorido e intervalo do avião |
| `tests/projmap/test_effects.py` | 6 testes novos (18 no arquivo) |
| `board/seed.py` | Card da fase 2 em `done` |

## Como funciona
**Bichinho.** Da pessoa só vêm *posição, escala e direções* dos membros
(*retargeting*, como no Animated Drawings da Meta); as proporções são fixas de
desenho. Cada parte segue o alvo com dinâmica de segunda ordem — tem massa,
passa um pouco do ponto e se acomoda —, a cabeça mais mole que o corpo, e o
rabo é uma corrente de Verlet com rigidez, arrasto e comprimento preservado. O
shader do autor desenha o personagem a partir desses uniforms, sem alteração.

**Paraquedas.** O rosto é recortado do quadro da câmera (256×256, endireitado
pelo eixo dos olhos, CLAHE para contraluz) e vai no capacete. O avião aparece
quando alguém olha para a câmera e larga um paraquedista por pessoa.

**Diferença consciente:** o original desenha a cena com o openFrameworks por
cima do shader; aqui ela é desenhada com o OpenCV no quadro RGBA que sai do
FBO — mesmas formas e coordenadas, com antisserrilhado e 1/8 de pixel de
precisão. No fade, o original multiplica a cor de cada primitiva pela
opacidade (o céu escurece junto com o fundo); aqui a cena é montada opaca e
entra por *crossfade* limpo. Ao fim da transição as duas são idênticas.

## Performance — o que estava travando
Medido na máquina do usuário (RTX 4060, DirectML), orçamento de 33 ms/quadro:

| Etapa | Antes | Depois |
|---|---|---|
| YOLO seg+pose (DirectML) | 10,8 ms | 10,8 ms |
| `stylize_comic` (Ecos) | **17,7 ms** | **8,0 ms** |
| `preprocess` | 2,9 ms | 1,4 ms |
| `fbo.read` | 0,9 ms | 0,9 ms |
| Visão com Ecos ligado | **~34,5 ms** (estoura) | **~24 ms** |

**O CUDA não era o gargalo.** O DirectML já roda na RTX 4060 (seg 4,1 ms, pose
4,7 ms); o CUDA só permitiria as duas redes em paralelo, economizando ~4 ms —
contra os ~11 ms que saíram do lado da CPU. Quem quiser comparar:
`PROJMAP_EFFECTS_PROVIDER=cuda` (exige trocar `onnxruntime-directml` por
`onnxruntime-gpu` com CUDA 12 + cuDNN 9).

O `ximgproc.guidedFilter` nativo foi testado (o `opencv-contrib` está
instalado) e é **mais lento** que a versão em NumPy: 4,6 ms contra 4,3 ms. Ficou
como estava.

Custo de cada efeito por quadro no motor (shader + desenho), 1280×720:

| Efeito | ms |
|---|---|
| Bichinho | 5,0 |
| Luz reativa | 8,1 |
| Paraquedas | 8,5 (era 18,8 antes do céu em cache e da cena em RGBA) |
| Ecos | 10,7 |
| LEGO | 13,0 |

## Como validar
```bash
pytest -q                      # 445 verdes (6 novos)
cd projmap/ui && npm run build
python -m projmap.master --project shows/x.projmap --windowed --open
# Interativo → Efeitos visuais → Bichinho espelho / Salto de paraquedas
```
Verificado nesta máquina com o shader real do autor (34 uniforms) e uma pose
sintética: o rig monta (`rig_valido=1,00`), os elos do rabo mantêm o
comprimento, o recorte de rosto fica pronto, o avião passa e solta um
paraquedista, e os três animais (gato, dinossauro, coelho) desenham com o fundo
colorido de cada um.

## Critério de aceite
- [x] Bichinho espelho no menu, com gato, dinossauro e coelho
- [x] Salto de paraquedas no menu, com o rosto real no capacete
- [x] Os 5 efeitos do autor disponíveis
- [x] `NUM_ELOS_RABO` igual ao do shader (8)
- [x] `pytest -q` verde e `npm run build` ok
- [ ] Testado com a C920 e o projetor no espaço real

## Pendências / próximos
- **Visão e motor ainda dividem o GIL** no mesmo processo. Com os ~11 ms que
  saíram a visão cabe nos 33 ms, mas levar a visão para outro processo
  (`multiprocessing`) é o próximo passo se ainda faltar folga com várias
  pessoas em cena.
- O fundo colorido do Bichinho é um ajuste global (`fundo_colorido`), como no
  original — vale expor no remote do celular.
