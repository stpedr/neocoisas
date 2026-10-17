# ProjMap — Entrada de vídeo/áudio ao vivo, efeitos reativos e servidor MCP

## 1. Resumo
O ProjMap agora aceita **entrada de vídeo ao vivo** (webcam ou placa de captura
HDMI) como fonte de superfície e uma **entrada de áudio** (o que toca no PC,
microfone ou um dispositivo pelo nome). Sobre qualquer fonte dá para aplicar
**efeitos reativos ao áudio** (pulsar, flash na batida, girar cores, zoom,
separar RGB, tremer, inverter), calculados na GPU. Um **servidor MCP**
(`python -m projmap.mcp_server`) expõe tudo isso a agentes (Claude Code etc.),
inclusive um snapshot do que está na parede.

## 2. Motivação
"Atualmente o sistema não aceita entrada de vídeo, correto? Planeje para aceitar
entrada de áudio e de vídeo e aplicar efeito em cima desses dois. De validação,
faça um e2e aplicando um efeito no vídeo usando a entrada de áudio e mapeie em
tela cheia no projeto já conectado neste PC." + "crie um MCP para permitir isso".

Antes: só arquivos (vídeo/GIF/imagem) viravam fonte; câmera e música existiam
apenas dentro dos efeitos do visual_frames (fonte "Cena interativa").

## 3. O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/core/project.py` | `SourceKind` ganha `capture` + `SourceSpec.device`; novos `AudioFx` e `AudioInput`; `Surface.fx` (≤ 8) e `Project.audio`. Campos opcionais — projetos antigos continuam válidos (sem subir a versão do esquema) |
| `projmap/inputs/video.py` | **Novo**: `Capture`/`CaptureSource` — thread por dispositivo, captura compartilhada com contagem de referências, reconexão com recuo, status (fps, erro) |
| `projmap/inputs/audio.py` | **Novo**: `AudioBus` — escolhe o dispositivo, aplica ganho, bandas `bass/mid/high/level` e envelope `beat` (meia-vida 0,12 s); só liga se alguma superfície tiver efeito |
| `projmap/effects/audio.py` | `AudioAnalyzer(device=…)`: `loopback` (padrão, igual a antes), `mic` ou parte do nome |
| `projmap/mapping/fx.py` | **Novo**: níveis + lista de efeitos → uniforms (`compute_fx`) e o espelho em CPU das fórmulas |
| `projmap/mapping/warp.py` | `render_surface_cpu(fx=…)` — oráculo GPU × CPU cobre os efeitos |
| `projmap/node/shaders/surface.frag` | Uniforms `u_fx_*`: zoom/tremor/separação RGB na amostragem; ganho/matiz/inversão/flash na cor |
| `projmap/node/renderer.py` | Lê os níveis uma vez por frame, liga o áudio no `sync` quando há efeito; stop de captura/áudio fora da thread do GL |
| `projmap/node/tap.py` + `window.py` | **Novo**: `OutputTap` — snapshot PNG do framebuffer real da janela do projetor, sob demanda |
| `projmap/master/inputs_api.py` | **Novo**: `GET /api/inputs`, `GET /api/inputs/audio`, `PATCH /api/audio`, `POST /api/surfaces`, `POST /api/surfaces/{id}/fullscreen`, `GET /api/nodes/{id}/snapshot` |
| `projmap/master/remote.py` | `PATCH /api/surfaces/{id}` aceita `fx` |
| `projmap/mcp_server/` | **Novo**: cliente HTTP da API + servidor MCP (SDK `mcp` 2.x, stdio) |
| `.mcp.json` | Registra o servidor `projmap` para o Claude Code neste repositório |
| `projmap/ui/…` | Fonte "Entrada de vídeo (câmera/captura)" com campo Dispositivo, seção "Efeitos de áudio" (`AudioFxSection`), botão "Tela cheia" em Cantos, rótulos na prévia/remote |
| `tests/projmap/test_av_inputs.py` | 30 testes: esquema, fórmulas, GPU × CPU com efeitos, barramento de áudio, captura, tap e rotas |
| `tests/projmap/test_mcp_server.py` | 5 testes: ferramentas MCP em memória contra a API real |
| `tests/projmap/test_e2e_live_av.py` | E2E ao vivo (projetor + webcam + som), só com `PROJMAP_LIVE=1` |
| `AudioFxSection.test.tsx`, `SurfacePanel.test.tsx` | 10 testes novos (TDD) |
| `projmap/ui/e2e/av-inputs.spec.ts` | Playwright: Entrada de vídeo → efeito de áudio (flash na batida) → Tela cheia, conferindo o PUT enviado ao mestre |

## 4. Como funciona
**Vídeo.** `{"kind": "capture", "device": "auto"}` abre a câmera (DirectShow no
Windows, V4L2 no Linux) escolhida como no sensor de webcam (`auto` = primeira
física, ignora OBS/DroidCam). Uma thread guarda só o quadro mais novo; o render
nunca espera e só reenvia a textura quando chega quadro novo. Duas superfícies
com a mesma entrada dividem a captura.

**Áudio.** `project.audio = {"device": "loopback", "gain": 1.0}`. O
barramento usa o mesmo analisador do visual_frames (FFT 2048, ganho automático,
batida de Patin) e entrega níveis 0..1. Nesta máquina o loopback capta a saída
padrão (o áudio HDMI do projetor EPSON).

**Efeitos.** Cada item de `surface.fx` é `{type, band, amount, enabled}`. A
cada frame `compute_fx` converte os níveis em uniforms e o shader aplica:
zoom → tremor → separação RGB na amostragem; ganho → matiz → inversão → flash
na cor; depois os ajustes de cor da superfície e do projetor. Vale para
qualquer fonte (vídeo ao vivo, arquivo, GIF, imagem).

**MCP.** O servidor só fala HTTP com o mestre já rodando (`PROJMAP_URL`,
`PROJMAP_TOKEN` se exposto na LAN — nunca por linha de comando). Ferramentas:
`status`, `list_inputs`, `audio_levels`, `set_audio_input`, `create_surface`,
`map_fullscreen`, `set_surface_source`, `set_surface_fx`, `set_output`,
`snapshot_output` (devolve a imagem).

## 5. Como validar
```powershell
# unidade + integração
.\.venv-projmap\Scripts\pytest.exe -q tests/projmap/test_av_inputs.py tests/projmap/test_mcp_server.py

# e2e ao vivo (abre o show do lançador numa cópia, em tela cheia no projetor, toca ~7 s de bumbo)
$env:PROJMAP_LIVE=1; .\.venv-projmap\Scripts\pytest.exe -q -s tests/projmap/test_e2e_live_av.py

# MCP com o Claude Code: suba o mestre e reabra a sessão neste repositório (.mcp.json)
.\.venv-projmap\Scripts\python.exe -m projmap.master --project C:\Users\pedro\Documents\ProjMap\rancho.projmap
```
Resultado do e2e neste PC (RTX 4060, projetor na tela 1, HD Webcam):
saída a 60 fps; webcam 17→115 quadros durante o teste; 9 batidas detectadas
pelo loopback; grave máx. 0,85; luma p10 da parede 139 em silêncio × 227
(mediana) / 255 (pico) com música — 80 de 114 snapshots no flash.

## 6. Critério de aceite
- [x] Superfície aceita entrada de vídeo ao vivo, escolhida por nome/índice/`auto`.
- [x] Entrada de áudio configurável no projeto (loopback/mic/nome + ganho).
- [x] Efeitos reativos ao áudio sobre qualquer fonte, GPU = CPU (> 98% dos pixels).
- [x] E2E no projetor conectado: superfície do show em tela cheia, webcam ao vivo, flash na batida.
- [x] Servidor MCP operando o fluxo completo (o e2e roda inteiro pelo MCP).
- [x] UI: fonte "Entrada de vídeo", "Efeitos de áudio" e "Tela cheia" com testes (TDD).

## 7. Pendências / próximos
- Painel de entrada de áudio na UI (escolher dispositivo/ganho e ver os níveis ao vivo); hoje é via API/MCP.
- Looks (`SurfaceLook`) ainda não guardam `fx`.
- Câmera aberta pelo VisionProcessor (efeitos do visual_frames) e por uma fonte `capture` ao mesmo tempo disputam o dispositivo no Windows.
- `test_motion_ai.py::test_api_motions_ai_config_nunca_expoe_chave_e_faz_streaming_sse` lê o keyring real: falha quando a máquina tem uma chave Anthropic salva (problema antigo de isolamento do teste).
