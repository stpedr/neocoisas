# F9 — Prévia ao vivo no editor + várias mídias por superfície

Pedido: "no MadMapper consigo ver e planejar as mídias em tempo real no
software, vendo a imagem ou a prévia do GIF e do vídeo. Aqui estou mapeando às
cegas. Também tem que dar para pôr mais de um vídeo/foto numa superfície e
ajustar/redimensionar cada um."

## 1. REA — como o MadMapper (e o Resolume) resolvem

Perguntas → ledger. **O** = observação (comportamento documentado e visível no
produto), **I** = inferência, **?** = desconhecido.

| # | Pergunta | Ledger |
|---|---|---|
| Q1 | O que o operador vê ao mapear? | **O** A vista de saída mostra o conteúdo já deformado em cada superfície, ao vivo (vídeo tocando). Os contornos e alças ficam por cima. |
| Q2 | Onde se escolhe *qual parte* da mídia vai numa superfície? | **O** O MadMapper tem a vista **Input** (a mídia inteira, com o retângulo/quad de recorte de cada superfície) e a vista **Output** (a parede). Arrastar na Input muda o recorte; na Output, a forma. |
| Q3 | Várias mídias numa área? | **O** No MadMapper, cada superfície recebe uma mídia; para compor, empilham-se superfícies. No Resolume (Arena), um *slice* recebe uma composição de camadas, cada clipe com transformação própria (posição, escala, rotação). **I** Para o nosso operador, "camadas dentro da superfície" é o modelo mental pedido. |
| Q4 | Como a prévia fica leve? | **I** Prévia de baixa resolução no editor, independente do render final do nó. **O** O MadMapper reduz a qualidade da prévia em máquinas fracas. |
| Q5 | Redimensionar mantém proporção? | **O** Ferramentas de transformação mantêm a proporção por padrão e liberam com um modificador (Shift). |
| Q6 | Como o MadMapper sincroniza a prévia com a saída? | **?** Interno. Para nós a prévia é aproximada (o vídeo no navegador não fica travado ao relógio do nó). Sincronia exata é tema da F2. |

## 2. Decisões

- **D-F9.1 Prévia no próprio canvas 2D do editor.** Cada mídia é desenhada
  dentro da superfície com perspectiva, por **subdivisão em malha 10×10**: cada
  triângulo recebe um mapeamento afim, e o erro de perspectiva fica abaixo de
  1 px numa tela comum. Vídeo via `<video muted loop>` e GIF via `<img>`,
  ambos de `/media/<sha>`. Assim não entra WebGL novo no editor e o mesmo
  código serve às vistas Foto e Projetor.
- **D-F9.2 Camadas por superfície** (`Surface.layers`, campo opcional, sem subir
  a versão do esquema). A `source` atual continua sendo o **fundo**. Cada camada
  tem `source`, `rect = [x, y, w, h]` no espaço uv da superfície (0..1; pode
  passar das bordas, e o que sai é recortado), `fit`, `opacity` e `visible`. A
  ordem na lista define a ordem de desenho.
- **D-F9.3 Matemática única.** O retângulo vira o mesmo `u_uvx` que o shader já
  usa (`tex = uv·s + o`), composto com o `fit` da camada. Nenhum shader novo, e
  o oráculo em CPU (`render_surface_cpu`) testa camadas de graça.
- **D-F9.4 Edição direta no canvas.** Com uma camada selecionada, o editor
  mostra o retângulo dela deformado na superfície, com 4 alças e arraste pelo
  meio. As coordenadas de tela voltam para uv pela homografia inversa. A
  proporção da mídia é mantida por padrão; **Shift** libera.
- **D-F9.5 Looks guardam as camadas** (`SurfaceLook.layers`, opcional: `None` =
  look antigo, não mexe nas camadas).

## 3. Execução

1. Esquema: `Layer`, `Surface.layers`, `SurfaceLook.layers` + testes.
2. `mapping/warp.py`: `layer_uvx(rect, fit, tamanho_fonte, quad)` + testes (CPU).
3. Renderer: desenha fundo + camadas; fontes reaproveitadas por (superfície,
   camada, spec). Teste de GPU com oráculo.
4. Recall de look aplica camadas.
5. UI: prévia de mídia no editor (malha), relógio de animação, cache de
   `<video>`/`<img>`.
6. UI: painel de camadas (adicionar/enviar mídia, ordenar, visível, opacidade,
   ajuste, x/y/w/h, "preencher superfície") e edição da camada no canvas.
7. Build, pytest, verificação ao vivo, MD de entrega e card no board.

## 4. Fora do escopo (próximos)

- Rotação de camada.
- Vista **Input** estilo MadMapper (recortar a mídia em vez de posicionar).
- Prévia sincronizada ao frame do nó (F2).
- Camadas no remote do celular (hoje ele só controla fonte e opacidade).
