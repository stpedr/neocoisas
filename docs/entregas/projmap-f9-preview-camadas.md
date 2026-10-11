# ProjMap F9 — Prévia ao vivo no editor + camadas por superfície

## Resumo
O editor passa a mostrar a mídia **dentro** das superfícies, em perspectiva e
animada (vídeo, GIF, imagem, cor e cartela), como no MadMapper. Cada superfície
aceita **várias mídias (camadas)**, que podem ser movidas e redimensionadas
direto no canvas.

## Motivação
O operador mapeava só por contornos coloridos, "às cegas", e cada superfície
aceitava uma única mídia. O plano e o REA estão em
[`docs/projmap/PLANO-F9-preview-camadas.md`](../projmap/PLANO-F9-preview-camadas.md).

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/core/project.py` | `Layer` (fonte, `rect` em uv, opacidade, visível); `Surface.layers`; `SurfaceLook.layers`; validação de mídia e ids das camadas |
| `projmap/mapping/warp.py` | `compose()` e `layer_uvx()`: o retângulo vira o mesmo `u_uvx` do shader, composto com o `fit` |
| `projmap/node/renderer.py` | Desenha o fundo e as camadas visíveis; fontes reaproveitadas por (superfície, camada, spec); contornos por superfície |
| `projmap/master/remote.py` | Looks salvam/restauram camadas (ignorando mídias apagadas) |
| `projmap/ui/app/lib/preview.ts` | Novo: região da textura no uv (espelho de `fit`/`layer_uvx`), cache de `<video>`/`<img>`, desenho em perspectiva por malha 10×10 |
| `projmap/ui/app/components/Editor.tsx` | Prévia dentro das superfícies, laço de animação só com vídeo/GIF, alças e arraste da camada selecionada |
| `projmap/ui/app/components/LayersPanel.tsx` | Novo: painel de camadas |
| `projmap/ui/app/page.tsx` | Liga camada selecionada e "Prévia da mídia"; edição parte sempre do projeto mais recente; upload junta a mídia nova ao estado |
| `projmap/ui/app/lib/types.ts` · `globals.css` | Tipo `Layer` e estilos |
| `tests/projmap/test_layers.py` · `test_remote.py` | 13 testes novos |
| `docs/projmap/PLANO-F9-preview-camadas.md` · `projmap/README.md` · `board/seed.py` | Plano com REA, guia de uso e card |

## Como funciona
- **Modelo.** `rect = [x, y, w, h]` no uv da superfície. O shader já faz
  `tex = uv·s + o`; a camada só define `s`/`o` (`(uv − xy)/wh`, composto com o
  `fit`). Fora do retângulo, `tex` sai de [0,1] e o fragmento é descartado.
  Nenhum shader novo, e o oráculo em CPU cobre camadas.
- **Prévia.** Para cada superfície: `uv → projetor` (homografia do quadrado
  unitário para o quad) `→ vista` (foto ou projetor) `→ tela`. A região da
  textura é dividida em 10×10 células, e cada triângulo recebe um afim e copia
  só a sua célula, para um vídeo 1080p continuar fluido. Recorte pela
  superfície e pelo retângulo da camada. O canvas só redesenha por frame quando
  há vídeo/GIF à vista.
- **Edição.** Com uma camada selecionada, as alças dela têm prioridade.
  Tela → uv pela homografia inversa. Canto: o oposto fica fixo e a proporção é
  mantida (Shift libera). Por dentro: translada.
- **Bug corrigido no caminho.** Depois de um upload, a edição seguinte partia
  de um estado antigo, sem a mídia nova, e o PUT seria recusado. Agora a edição
  usa sempre o projeto mais recente, e o upload junta só a mídia nova.

## Como validar
```bash
pytest -q                                    # 276 passam (13 novos, incl. GPU vs. CPU com camadas)
cd projmap/ui && npm run build
python -m projmap.tools.demo --project shows/demo.projmap
python -m projmap.master --project shows/demo.projmap --windowed --open
# Caixa grande → card Camadas → "+ Do projeto…" → arraste os quadrados brancos
```
Verificado ao vivo no Chrome (automação com cliques reais):
- o vídeo toca na superfície e as 2 camadas aparecem em perspectiva;
- arrastar o canto redimensionou a camada e manteve a proporção
  (1,000 → 1,000);
- arrastar por dentro moveu a camada sem mudar o tamanho;
- o painel lista, ordena e edita as camadas.

## Critério de aceite
- [x] Mídia visível e animada dentro das superfícies no editor (vistas Foto e Projetor)
- [x] Várias mídias por superfície, cada uma movível e redimensionável
- [x] A saída do projetor renderiza as camadas igual ao editor (teste GPU vs. CPU)
- [x] Looks guardam as camadas; projetos antigos continuam válidos
- [x] `pytest -q` verde e `npm run build` ok
- [ ] Validado num projetor real com vídeo pesado

## Pendências / próximos
- Rotação de camada.
- Vista **Input** estilo MadMapper (recortar a mídia em vez de posicioná-la).
- Prévia sincronizada ao frame do nó (F2).
- Camadas no remote do celular.
- Setas do teclado ainda movem os cantos da superfície, não a camada selecionada.
