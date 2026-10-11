# ProjMap — Ajustes de imagem (brilho, gama, cor) + retroprojeção/teto

## Resumo
Ajustes de imagem no projetor inteiro e em cada superfície (brilho,
contraste, saturação, gama, temperatura de cor), com predefinições prontas.
Também espelhar (retroprojeção) e inverter (projetor de teto). Tudo aplicado
na GPU, ao vivo.

## Motivação
Pedido do usuário: "aumentar por trás, aumentar o brilho, configurações que
melhorem a projeção". "Por trás" foi entendido como retroprojeção (projetor
atrás da tela).

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/core/project.py` | `ColorAdjust`; `Output.color`, `Output.flip_h`, `Output.flip_v`; `Surface.color` (opcionais, neutros; projetos antigos continuam válidos) |
| `projmap/mapping/color.py` | Novo: fórmula de referência em CPU (oráculo dos testes) |
| `projmap/node/shaders/surface.frag` · `surface.vert` | `adjust()` por pixel (superfície → projetor) e espelhamento (`u_flip`) |
| `projmap/node/renderer.py` | Envia os ajustes; padrões de alinhamento saem sem ajuste de cor |
| `projmap/ui/app/components/ColorControls.tsx` · `ImageCard.tsx` | Novos: controles, predefinições e orientação |
| `SurfacePanel.tsx` · `Editor.tsx` · `remote/page.tsx` · `page.tsx` | Cor por superfície; prévia aproximada com filtro CSS; card "Imagem" no celular |
| `projmap/GUIA.md` | Seção "Melhorar a imagem projetada" (inclui dicas de hardware) |
| `tests/projmap/test_color.py` | 10 testes |

## Como funciona
- Ordem no shader: contraste → brilho (ganho) → saturação (luma Rec. 709) →
  temperatura (ganho por canal) → corte → gama. Primeiro o ajuste da
  superfície, depois o do projetor. A mesma fórmula está em
  `mapping/color.py`, e o teste compara GPU com CPU (diferença ≤ 2/255).
- **Gama > 1** clareia sombras e médios sem estourar o branco. É o ajuste
  recomendado para ambiente claro. **Brilho > 1** é ganho puro e estoura os
  brancos.
- **Espelhar:** o vértice inverte o NDC e o fragmento converte o pixel da tela
  de volta para o pixel lógico (`out − px`), então homografia, recortes e
  contornos continuam certos.
- A prévia do editor aproxima os ajustes com `ctx.filter` (CSS). A saída real
  usa o shader exato. O editor continua mostrando a vista lógica, sem
  espelhar, para editar sem confusão.

## Como validar
```bash
pytest -q                                     # 397 verdes (10 novos, incl. GPU vs. CPU e espelhamento)
cd projmap/ui && npm run build
```
Ao vivo:
- render do projeto real do usuário com o renderer do nó em 4 configurações
  (original, ambiente claro, parede amarelada, retroprojeção), todas com o
  efeito esperado;
- no Chrome, clicar em "Ambiente claro" e em "Retroprojeção" mudou o
  `output` no mestre, e a prévia refletiu as cores. O projeto foi restaurado
  depois do teste.

## Critério de aceite
- [x] Brilho, contraste, saturação, gama e temperatura no projetor e por superfície
- [x] Predefinições para ambiente e cor de parede
- [x] Retroprojeção (espelhar) e teto (inverter)
- [x] GPU igual à referência CPU; padrões de alinhamento sem ajuste
- [x] Editor, painel e celular; guia atualizado
- [ ] Avaliado num projetor real (percepção de cor varia por modelo)

## Pendências / próximos
- Prévia exata no editor (WebGL com o mesmo shader, em vez do filtro CSS).
- Correção de cor da parede **medida** pela câmera (foto da parede com branco
  projetado → temperatura/ganho automáticos).
- Edge blending e correção de uniformidade (F4).
