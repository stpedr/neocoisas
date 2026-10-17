# ProjMap — Motion (HTML) como mídia do projeto, projetado numa superfície

## 1. Resumo
Um motion (Motion Module v1, o `.html` audio-reativo do Motion Studio ou gerado com
Claude) agora entra no projeto **igual a uma imagem**: botão `+ Motion` no painel da
superfície (ou "📽 Projetar" no Motion Studio), e a superfície passa a mostrar o motion
**no projetor**, com warp, mistura, efeitos e ajuste de cor como qualquer vídeo. O motion
recebe o **áudio do show** e, opcionalmente, uma **entrada de vídeo** (webcam/placa de
captura). De quebra: o remote do celular ganhou "+ Nova superfície" / "+ Tela cheia".

## 2. Motivação
"Achei terrível a solução de app terceiro (OBS). Planeje uma forma intuitiva em que eu
posso adicionar um html ao projeto igual imagem e escolher uma superfície para mostrar o
motion (os motions podem ter entrada de vídeo). Faça um teste e2e completo." E: "no web
celular, nas superfícies, não aparecia o botão pra adicionar outras superfícies".

## 3. O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/core/project.py` | `MediaKind`/`SourceKind` ganham `motion`; `SourceSpec.params` (escalares, ≤ 64, chaves e textos limitados) e `SourceSpec.mode`; `device` também vale para o motion (câmera entregue a ele) |
| `projmap/core/store.py` | `.html`/`.htm` viram mídia `motion` **só se** tiverem manifesto Motion Module v1 válido (≤ 5 MB) |
| `projmap/motion/manifest.py` | **Novo**: lê/valida o manifesto sem executar o HTML (`id`, `name`, `version`, `video.input`) |
| `projmap/motion/browser.py` | **Novo**: Chromium headless dedicado (Playwright → Chrome → Edge), na GPU dedicada, sem estrangulamento de fundo, sem tarefas de primeira execução; morre junto com o mestre (Job Object no Windows, `PDEATHSIG` no Linux) |
| `projmap/motion/hub.py` | **Novo**: sessões abertas pelo renderer, quadros que chegam do navegador (JPEG → RGBA), watchdog que liga/religa/desliga o navegador |
| `projmap/motion/source.py` | **Novo**: a fonte `motion` (quadro mais novo, o render nunca espera) |
| `projmap/master/motion_host_api.py` | **Novo**: `WS /ws/motion-host` (sessões, áudio ~60/s, quadros da câmera ~30/s; recebe os quadros dos motions, decodificando fora do event loop) e `GET /api/motions/host` (status/fps) |
| `projmap/master/auth.py`, `app.py` | **Novo** `SameOriginWriteMiddleware`: escrita em `/api`/`/media` e WebSockets só da própria origem (ou do editor em dev). Bloqueia POST de qualquer site — e do iframe sandbox de um motion (origem `null`) |
| `projmap/ui/app/motion-host/`, `components/MotionHost.tsx`, `lib/motionHost.ts` | **Novo**: página host — um iframe `sandbox="allow-scripts"` por motion, shim que captura o canvas, protocolo binário, `motion:audio`/`motion:video` |
| `projmap/ui/app/components/SurfacePanel.tsx` | Fonte "Motion (HTML)", `+ Motion`, campo "Entrada de vídeo do motion" |
| `projmap/ui/app/components/MotionStudioDialog.tsx`, `page.tsx` | "📽 Projetar" em cada motion da biblioteca, escolhendo a superfície |
| `projmap/ui/app/remote/page.tsx` | "+ Nova superfície", "+ Tela cheia" e "⛶ Tela cheia" por superfície |
| `projmap/library.py` | Miniatura (cartão com nome/versão) e dimensões do motion |
| `projmap/mcp_server/` | Ferramentas `add_media` e `motion_status`; `set_surface_source` aceita `motion` + `params`/`mode` |
| `projmap/ai/motion_system_prompt.md` | Spec: `"video": {"input": true}`, mensagem `motion:video` (seção 6.1) e regras de projeção (8.1) |
| `packaging/omarchy/install.sh` | Instala `chromium` (navegador dos motions) |
| `tests/projmap/test_motion_projection.py` | 12 testes, incluindo o caminho inteiro com Chromium de verdade (motion → vídeo → batida → renderer) |
| `tests/projmap/test_e2e_live_motion.py` + `ui/e2e-live/` | E2E ao vivo no projetor, pela UI real (Playwright sem mocks) |
| `tests/projmap/test_motion_ai.py` | Isolado do keyring real (falhava em máquina com chave salva) |
| `ui/e2e/av-inputs.spec.ts` | Mock coerente com o polling do editor (era instável) |

## 4. Como funciona
```
renderer (superfície kind=motion) ──open_session──▶ MotionHub ──watchdog──▶ Chromium headless dedicado
                                                        ▲                      └─ /motion-host/ (página host)
          quadro mais novo ◀── JPEG ◀── WS /ws/motion-host ◀── iframe sandbox do motion + shim
   áudio do show (AudioBus) ──▶ motion:audio ──▶ │
   entrada de vídeo (câmera) ──▶ motion:video ──▶│
```
- O shim (injetado no `srcdoc` antes do código do motion) cadencia o `requestAnimationFrame`
  do motion a ~60 Hz e, logo depois de cada quadro, codifica o maior `<canvas>` em JPEG
  (`toBlob`, fora da thread principal). Um quadro em voo; o host libera o próximo.
- O mestre decodifica numa thread (o OpenCV libera o GIL) e entrega o quadro à fonte; a
  textura só sobe para a GPU quando chega quadro novo.
- O áudio vai como níveis (`bass/mid/high/level`, contador de batidas); a página host monta
  o payload da spec (`energy`, `kick`/`beat`/`downbeat`, `bpm`/fases estimados).
- Por que JPEG e não pixels crus: medido, o uvicorn só aguenta ~29 fps de 720p cru (3,7 MB/quadro).
- **Limitações conhecidas:** fundo transparente compõe como preto (preto = sem luz; use
  "Somar"); só o maior canvas é capturado (DOM por cima não aparece); a taxa oscila — 20–30 fps
  com o motion isolado nesta máquina, menos com a janela do projetor e outro mestre ativo
  disputando a mesma GPU (no e2e, o status chegou a 6 fps em alguns momentos).

## 5. Como validar
```powershell
# unidade + integração (inclui Chromium de verdade; pula se não houver navegador ou UI compilada)
.\.venv-projmap\Scripts\pytest.exe -q tests/projmap/test_motion_projection.py

# e2e ao vivo no projetor: UI real → motion com a webcam em tela cheia → bumbo no som do PC
$env:PROJMAP_LIVE=1; .\.venv-projmap\Scripts\pytest.exe -q -s tests/projmap/test_e2e_live_motion.py

# UI
cd projmap/ui; npm run test; npm run test:e2e
```
Uso: no editor, selecione a superfície → `+ Motion` (o `.html`) → (opcional) "Entrada de
vídeo do motion" = `auto` → Cantos → **Tela cheia**. Ou no Motion Studio: escolha a
superfície ao lado do motion e **📽 Projetar**.

Resultado do e2e neste PC (show `rancho` copiado, projetor na tela 1, HD Webcam): passo de
UI ok; marcador do motion na saída; webcam no centro (107 → 233 quadros); 10 batidas
captadas pelo loopback; barra de graves em 9/9 snapshots e flash da batida em 3/9.

## 6. Critério de aceite
- [x] `.html` entra no projeto como mídia (validado), com miniatura, igual imagem.
- [x] Escolher a superfície pelo painel ou pelo Motion Studio; o motion aparece no projetor.
- [x] O motion recebe o áudio do show e a entrada de vídeo escolhida.
- [x] Motion isolado: sem acesso de escrita à API (sandbox + guarda de origem).
- [x] Navegador não fica órfão se o mestre cair.
- [x] E2E completo no projetor conectado, pela UI real.
- [x] Remote do celular cria superfícies e mapeia em tela cheia.

## 7. Pendências / próximos
- Desempenho: caminho por WebCodecs (H.264 na GPU) ou resolução adaptativa para manter 30 fps
  com o projetor ativo; medir com um único mestre na máquina.
- Editar `params`/`mode` do motion pela UI da superfície (hoje: Motion Studio → Projetar usa
  os padrões; MCP aceita `params`).
- Prévia do motion no canvas do editor (hoje mostra o rótulo "motion · nome").
- Canal alfa (motions transparentes) — exigiria PNG/WebP ou pixels crus a menor resolução.
