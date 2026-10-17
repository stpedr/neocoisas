# ProjMap — Camera Grain Crimson

## Entrega

Motion Module v1 autocontido em
`projmap/motion/examples/camera-grain-crimson.html`. Ele recebe a câmera pelo
canal `motion:video` e os envelopes/eventos do show por `motion:audio`, sem
acessar diretamente a API do mestre.

Desde a versão 1.1.0 do motion, posterização, contraste, recorte, cor, grão e
scanlines são executados em um fragment shader WebGL. O vídeo é enviado direto
para uma textura, sem `getImageData` nem laços JavaScript por pixel. O navegador
dedicado solicita a GPU de alto desempenho e usa D3D11 no Windows.
O parâmetro **Resolução interna** controla o custo de captura; o padrão de 35%
preserva o aspecto do grão enquanto reduz cerca de 88% dos pixels processados
em cada quadro. A saída RGBA é lida diretamente da GPU, sem codificar e
decodificar JPEG.

## Visual

- vídeo convertido em preto, branco e níveis de cinza;
- granulação vermelha determinística e linhas de varredura;
- modos `crimson`, `monochrome` e `negative`;
- fallback procedural quando ainda não existe quadro da câmera;
- teste independente com câmera e microfone pelo botão do próprio HTML.

## Reação ao áudio

| Alvo | Fonte sugerida | Resultado |
|---|---|---|
| Grão | agudos | aumenta a textura e a instabilidade do quadro |
| Vermelho | graves | reforça a camada carmesim |
| Contraste | energia | fecha pretos e abre brancos durante trechos fortes |
| Impacto | kick | cria um flash curto e emite `motion:event beat` |

Todos os alvos respeitam `reactTo`, intensidade global, sensibilidade,
roteamento personalizado e suavização/caimento definidos pelo Motion Module
v1.

## Uso

1. Na superfície, clique em **+ Motion** e escolha o HTML.
2. Em **Entrada de vídeo do motion**, selecione `auto` ou parte do nome da
   câmera/placa de captura.
3. Mantenha o áudio do show ativo e ajuste os parâmetros no Motion Studio.

## Validação

- manifesto validado no backend e pelo validador estrito da UI;
- fluxo real Chromium isolado → `motion:video`/`motion:audio` → JPEG → renderer;
- câmera sintética e mudança visual por áudio verificadas em 1280×720;
- testes automatizados garantem que o exemplo continue importável e declare
  entrada de vídeo e os três modos.
