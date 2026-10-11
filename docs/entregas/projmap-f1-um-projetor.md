# ProjMap F1 — um projetor, local: quads manuais + vídeo/GIF

## Resumo

Primeira versão funcional do ProjMap. Você carrega a foto tirada da posição do
projetor, marca onde a luz cai, desenha as superfícies como quads (mouse ou
toque, com lupa) e escolhe vídeo, GIF, imagem, cor ou cartela para cada uma.
Uma janela em tela cheia no projetor mostra o resultado **ao vivo** enquanto
você arrasta. O projeto salva sozinho e exporta/importa como `.pmz`.

## Motivação

É a fase F1 do plano aprovado ("aprovado como está", D1–D8). Ela estabelece o
núcleo que todas as fases seguintes reutilizam: modelo de dados, homografia,
renderer GLSL, fontes guiadas por tempo e API do mestre.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `projmap/core/geometry.py` | Homografia por DLT normalizada (Hartley), validação de quad (convexo/não cruzado), `order_quad`. |
| `projmap/core/project.py` | Esquema `project.json` v1 (pydantic): nós, saída, superfícies, fontes, mídia. Validação de referências e `migrate()`. |
| `projmap/core/store.py` | Diretório `.projmap`, escrita atômica, mídia por sha256, fotos por nó, exportar/importar `.pmz` (anti zip slip, confere hash). |
| `projmap/core/state.py` | Estado vivo com **revisão**: a API publica, o renderer compara um inteiro por frame. |
| `projmap/content/*` | Fontes por factory (`get_source`): imagem, GIF (atraso real por frame), vídeo (PyAV numa thread, seek/loop), cor, cartela. Padrões grade/branco/preto/**bordas da foto**. |
| `projmap/mapping/warp.py` | Uniforms do shader, ajuste cover/contain/stretch, renderer de referência em CPU (bilinear). |
| `projmap/node/renderer.py` + `shaders/` | Renderer moderngl. `uv = H⁻¹·(x,y,1)` por pixel (sem "dobra"), feather, opacidade, misturas normal/add/multiply, dimmer master, blackout, contornos. GLSL ES 3.00 com `#version` injetado. |
| `projmap/node/window.py`, `node/__main__.py` | Janela pyglet em tela cheia no monitor escolhido, log de fps. Nó standalone que recarrega o `project.json`. |
| `projmap/master/app.py`, `master/__main__.py` | API FastAPI (projeto, uploads, toggles de saída, export) + CLI do mestre: UI + saída no mesmo processo. |
| `projmap/ui/` | Editor Next.js com export estático: vistas Foto/Projetor, arraste de cantos e da superfície, lupa, marcação da área projetada, setas/Tab para ajuste fino, painel da superfície, barra de saída. Layout responsivo para celular. |
| `projmap/tools/demo.py`, `tools/bench.py` | Projeto de exemplo para testar sem projetor; benchmark do aceite 1080p30. |
| `projmap/README.md`, `projmap/ARCHITECTURE.md` | Setup do mestre e do nó (com systemd), fluxo na parede real, decisões de engenharia, desempenho medido. |
| `tests/projmap/*` (48 testes) | Geometria, GPU vs CPU, projeto/store/.pmz, fontes (GIF/vídeo/loop), API. |
| `requirements-projmap-{master,node}.txt` | Dependências do mestre e do nó (nó sem torch). |
| `.github/workflows/ci.yml` | Backend instala as deps do ProjMap e roda sob `xvfb-run` (testes de GPU reais com llvmpipe). Novo job de build da UI. |
| `board/seed.py`, `docs/projmap/PLANO.md`, `.gitignore` | F0 → Concluído, F1 → Revisão; status do plano; `shows/` e `*.pmz` fora do git. |

## Como funciona

1. **Foto e área projetada.** A foto vem da posição do projetor. O usuário
   marca os 4 cantos de onde o quadro branco cai na foto. Isso define a
   homografia foto→projetor.
2. **Superfícies.** Um quad desenhado na foto é convertido para pixels do
   projetor, que são a fonte de verdade.
3. **Ida à parede.** A UI manda o projeto inteiro (`PUT /api/project`, ~20/s
   durante o arraste). O servidor valida e grava, e a revisão sobe.
4. **Renderer.** A cada frame, o renderer vê a revisão nova e refaz só os
   buffers da superfície. O vídeo não reinicia, porque a fonte é reaproveitada
   pela chave da especificação.
5. **Shader.** Para cada pixel, calcula `uv = H⁻¹·(x, y, 1)`, aplica
   fit/feather/opacidade e mistura.
6. **Tempo.** Todas as fontes respondem a `frame_at(t)`. É isso que, na F2, vai
   sincronizar vários nós com um relógio comum.

Detalhes e justificativas: `projmap/ARCHITECTURE.md`.

## Como validar

```bash
# Testes (GPU real via Xvfb; sem display os testes de GPU são pulados)
pip install -r requirements-dev.txt -r requirements-projmap-master.txt
xvfb-run -a pytest -q            # 199 passed (Python 3.11 e 3.13)

# UI
cd projmap/ui && npm ci && npm run build && cd ../..

# Ao vivo, sem projetor (janela de preview)
python -m projmap.tools.demo --project shows/demo.projmap
python -m projmap.master --project shows/demo.projmap --windowed --open

# Com projetor (2º monitor)
python -m projmap.master --project shows/meu-show.projmap --display 1 --open

# Desempenho
python -m projmap.tools.bench --surfaces 4 --seconds 10
```

Validação feita nesta entrega, num ambiente com Xvfb e GL por software:
- Mestre em tela cheia com o projeto de exemplo: saída 1080p a 60–120 fps.
- UI dirigida por Chromium (Playwright):
  - arrastar um canto gerou PUTs ao vivo, e a revisão subiu de 23 para 33;
  - padrão, contornos e dimmer mudaram a saída;
  - a lupa amplia a foto;
  - o layout de celular (390 px) cabe na tela;
  - zero erros de JS.
- O padrão "Bordas da foto" na saída caiu exatamente sobre a superfície da
  coluna. Isso confirma que a homografia do TypeScript (UI) e a do Python
  (renderer) concordam.

## Critério de aceite

- [x] Testes de homografia: round-trip < 1e-6 px, igual ao OpenCV
      (`getPerspectiveTransform` e `findHomography`), recusa colineares,
      cruzados e côncavos, e há um teste de uv projetivo sem a "dobra".
- [x] GPU = referência CPU em mais de 99% dos pixels (perspectiva, cover,
      contain, feather) e orientação dos cantos correta.
- [x] Projeto salvo → recarregado → idêntico. `.pmz` exporta e importa com
      conferência de hash.
- [x] GIF respeita o atraso por frame. Vídeo segue o relógio e faz loop.
- [~] 1080p30 com 4 superfícies:
  - ✅ 4×720p (p95 28,9 ms) e 2×1080p, medidos **com GL por software** num
    container de 4 vCPUs;
  - ❌ 4×1080p nesse mesmo ambiente (p95 51,7 ms);
  - **falta medir numa GPU real**: rode o `bench` no seu PC.
- [ ] Validação na parede real com o seu projetor. É o que mantém o card em
      **Revisão**.

## Pendências / próximos

- **Você:** rodar no seu PC com o projetor e o `bench`, e contar o resultado.
- **F2:**
  - nó como processo próprio, com descoberta mDNS;
  - distribuição de mídia por hash;
  - relógio comum por OSC;
  - 3 nós simulados com medição de sincronia;
  - spikes U1/U2 no Pi 5.
- **Otimização, se a GPU real não sobrar:** upload de YUV e conversão no shader.
- **Ainda não feito (vem nas próximas fases):**
  - grade/Bézier por superfície e máscaras por polígono, previstas no PLANO
    como correção sobre a homografia;
  - integração com o app `web/` do Auto Niche Engine, prevista para a F6
    junto com o remote mobile.
