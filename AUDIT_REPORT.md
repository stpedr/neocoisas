# AUDIT_REPORT.md — Diagnóstico e Auditoria Profunda (Escopo: **ProjMap Standalone**)

**Data da Auditoria:** 2026-10-16  
**Escopo:** **Exclusivamente o ProjMap** (`projmap/`, `projmap/ui/`, `projmap/android/`, `tests/projmap/`, `requirements-projmap-*.txt`) — sistema de projeção mapeada em tempo real (mestre FastAPI, nó OpenGL/ModernGL, camada interativa 60 Hz, editor web Next.js + remote/sensor mobile e app Android Capacitor), operando **100% independente** do legado Auto Niche Engine.  
**Modo:** Somente leitura (Fase 1 do protocolo de estabilização e blindagem).

---

## 1. Mapa da Stack Real do ProjMap

### 1.1 Frameworks, Runtimes e Bibliotecas Reais
| Camada | Stack Real (Evidência) |
|---|---|
| **Mestre HTTP / WebSocket** | **FastAPI** `>=0.111` + **Uvicorn** `>=0.30` + **Pydantic v2** `>=2.6` + `python-multipart>=0.0.9` (`requirements-projmap-master.txt:8-11`, `projmap/master/app.py`) |
| **Renderização GPU e Janela** | **ModernGL** `>=5.10` + **Pyglet** `>=2.0` (`requirements-projmap-master.txt:12-13`, `projmap/node/renderer.py`, `projmap/node/window.py`), shaders GLSL `#version 330 core` / `#version 300 es` |
| **Visão, Vídeo e Áudio** | **NumPy** `>=1.26`, **OpenCV** `opencv-python-headless>=4.9`, **Pillow** `>=10.0`, **PyAV** `av>=12.0`, **ONNX Runtime** (`onnxruntime-directml>=1.18` no Windows / `onnxruntime>=1.18` no Linux, rodando `yolo26n-seg.onnx` e `yolo26s-pose.onnx` em `projmap/effects/detector.py`), **SoundCard** `>=0.4` (loopback WASAPI em `projmap/effects/audio.py`), **MediaPipe** (opcional, `projmap/interact/sensors.py`) |
| **Rede, Integrações e Desktop** | **python-osc** `>=1.8` (UDP OSC), **httpx** `>=0.27` (Google Drive API v3 em `projmap/gdrive.py`), **segno** `>=1.6` (QR SVG), **python-dotenv** `>=1.0`, **tkinter** (lançador desktop em `projmap/desktop/`), **ffmpeg** / **adb** via `subprocess` |
| **Frontend (`projmap/ui/`)** | **Next.js 14.2.35** (`output: "export"` estático em `projmap/ui/next.config.mjs:7`), **React 18.3.1**, **TypeScript 5.5.3**, **Tailwind CSS v4.3.3**, **shadcn/ui (Radix UI)**, **Framer Motion 14.3**, **@mediapipe/tasks-vision 1.0.1**, **Vitest 5.0.5** + **Playwright 1.64.1** |
| **App Mobile (`projmap/android/`)** | **Capacitor 7** + **Android Gradle 8.7.2** (`minSdk 23`, `targetSdk 35`) + `jsqr 1.4.0` (`projmap/android/www/launcher.js`) |

### 1.2 Acoplamento Remanescente com o Auto Niche Engine e Sobreposições Internas
1. **Único acoplamento de código entre o ProjMap e o Auto Niche Engine (`projmap/interact/nlp.py:107`):**
   ```python
   # projmap/interact/nlp.py:107
   from agents.llm import get_text_client
   ```
   Viola a Decisão D1 (`docs/projmap/PLANO.md:11` — *"Isolado em `projmap/`"*). Ao substituir essa chamada por um cliente HTTP direto/leve dentro de `projmap/interact/` (usando o `httpx` que já faz parte de `requirements-projmap-master.txt`), o ProjMap passa a rodar **100% sem nenhum arquivo da raiz do Auto Niche Engine**.
2. **Dois sistemas de estilo coexistindo em `projmap/ui/app/globals.css`:**
   - Carrega Tailwind v4 (`@import "tailwindcss";` e `@theme inline`, linhas 1–95), mas mantém **537 linhas de CSS artesanal global** (linhas 97–633), incluindo seletores globais de tag (`h2`, `label`, `input, select`, `textarea` nas linhas 115, 218, 224–235, 345–353) que afetam componentes Radix/shadcn.
   - Três implementações de Slider coexistem: Radix Slider (`app/components/ui/slider.tsx`), `Slider` manual com throttle em `app/remote/page.tsx:287-316` e `<input type="range">` nativo em `app/page.tsx:560-567`.
3. **Dois carregadores de `.env` no mesmo processo do mestre:**
   - `python-dotenv` (`load_dotenv`) em `projmap/master/__main__.py:72, 168-175`;
   - Parser manual `carregar_env()` reimplementado em `projmap/interact/stream.py:51-73`.
4. **Ciclo de importação entre pacotes internos do ProjMap:**
   - `projmap/interact/runtime.py:151` importa `projmap.effects.engine.EffectsEngine`, enquanto `projmap/effects/vision.py:135` importa `projmap.interact.cameras`.

### 1.3 Persistência e Fluxo de Estado/Dados Hoje
- **Persistência em disco:**
  - `<show>.projmap/project.json`: fonte de verdade do mapeamento validada por Pydantic (`projmap/core/project.py:238-246`), salva com escrita atômica (`tempfile.mkstemp` + `os.fsync` + `os.replace` em `projmap/core/store.py:56-69`).
  - `<show>.projmap/media/<sha256><ext>` e `captures/<node_id>/photo.<ext>`.
  - **Arquivos JSON sem escrita atômica (risco de truncamento):** `<show>.projmap/scenes/active.json` (`projmap/interact/runtime.py:124`), `~/.projmap/library.json` (`projmap/library.py:78`), `<show>.projmap/cache/library-meta.json` (`projmap/library.py:162`) e `~/.projmap/launcher.json` (`projmap/desktop/core.py:53`).
  - **Banco SQLite (`projmap/master/db/`):** Decisão D9 documentada em `CLAUDE.md:82-86` (SQLAlchemy 2.0 async + `aiosqlite` + Alembic para catálogo/biblioteca/presets), ainda pendente de implementação (Fase 8 da Sprint 12).
- **Fluxo de dados em tempo real:**
  - **UI ↔ Mestre:** `projmap/ui/app/page.tsx` concentra 19 `useState` e 6 `useRef`, enviando o `Project` inteiro via `PUT /api/project` a cada edição (~20 req/s durante arraste no canvas) e fazendo polling em `GET /api/health` (1,5s) e `GET /api/interact/state` (0,5s).
  - **Mestre ↔ Janela OpenGL:** A thread principal (`projmap/node/window.py:76-86`) lê `state.snapshot()` a 60 Hz e desenha via ModernGL; `InteractionRuntime` roda numa thread de 60 Hz expondo o frame via singleton global `_current` (`projmap/interact/runtime.py:28`).

---

## 2. Vulnerabilidades Críticas no ProjMap (P0)

### [P0-01] Bypass de Autenticação via `is_loopback` (`projmap/master/auth.py`): CSWSH, CSRF e DNS Rebinding
- **Onde:** `projmap/master/auth.py:35-37, 59-64`, `projmap/interact/api.py:180-187`.
- **Evidência:**
  ```python
  def is_loopback(scope) -> bool:
      client = scope.get("client")
      return bool(client) and client[0] in LOOPBACK
  ```
- **Risco:** `PairingTokenMiddleware` dispensa o token para qualquer conexão originada de `127.0.0.1`/`::1` sem validar os cabeçalhos `Origin` ou `Host`:
  1. **Cross-Site WebSocket Hijacking (CSWSH):** Navegadores não aplicam Same-Origin Policy em WebSockets. Qualquer site aberto no navegador do PC do mestre pode conectar em `ws://127.0.0.1:8100/api/interact/phone`, trocar o sensor do show para `PhoneSensor` e injetar coordenadas falsas.
  2. **CSRF via Simple Requests:** Qualquer aba web pode disparar `POST` sem preflight CORS (`multipart/form-data` ou query params) para `http://127.0.0.1:8100/api/media`, `/api/nodes/{id}/photo`, `/api/looks/{id}/recall`, `/api/interact/pause?paused=true`, `/api/gdrive/disconnect`, etc.
  3. **DNS Rebinding:** Sem `TrustedHostMiddleware` validando o header `Host`, um domínio externo com rebinding para `127.0.0.1` lê `GET /api/remote/pair` (roubando o token da LAN) e altera `PUT /api/library/roots` (`projmap/master/library_api.py:59-71`) para listar arquivos arbitrários do disco.

### [P0-02] Injeção de Parâmetros Arbitrários em `POST /api/interact/sensor` (`**body.options`) e `PATCH /api/interact/effects/params`
- **Onde:** `projmap/interact/api.py:38-39, 118-128, 158-164`, `projmap/interact/sensors.py:105, 300-318`.
- **Evidência:**
  ```python
  class SensorBody(BaseModel):
      kind: str
      options: dict[str, Any] = Field(default_factory=dict)
  ...
  runtime.set_sensor(get_sensor(body.kind, aspect=runtime.spec.aspect, **body.options))
  ```
- **Risco:**
  1. Enviar `{"kind": "webcam", "options": {"model_path": "C:/caminho/secreto"}}` funciona como oráculo de existência de arquivos no servidor (via erro 422) e passa o arquivo para o parser C++ do MediaPipe.
  2. Enviar `{"kind": "osc", "options": {"host": "0.0.0.0", "port": 9999}}` abre um servidor UDP em qualquer porta livre do host.
  3. Em `PATCH /api/interact/effects/params` (`interact/api.py:126`), `setattr(eng.params, k, type(getattr(eng.params, k))(v))` avalia `bool("false")` como `True`, aceita `NaN`/`Inf` ou `0` (causando divisão por zero no shader) e gera HTTP 500 se receber tipos inválidos.

### [P0-03] Ausência de Autorização Granular na LAN + DoS de Disco/RAM em Uploads e Exportação
- **Onde:** `projmap/master/auth.py:59-64`, `projmap/master/app.py:97, 131, 153, 202-208`.
- **Risco:**
  1. O token de 12 caracteres compartilhado via QR code para celulares na LAN concede acesso irrestrito a rotas destrutivas/administrativas que deveriam ser exclusivas do editor local (`PUT /api/project`, `POST /api/media`, `GET /api/project/export`, `/api/library/*`, `/api/gdrive/*`, `DELETE /api/color-presets/*`).
  2. `GET /api/project/export` (`projmap/master/app.py:202-208`) cria um `tempfile.mkdtemp(prefix="projmap-export-")` com cópia ZIP de todos os vídeos do show a cada chamada e **jamais apaga o diretório temporário** (DoS imediato de disco).
  3. `POST /api/nodes/{node_id}/photo` (`app.py:158`) faz `await file.read()` inteiramente na RAM sem limite de tamanho, e `POST /api/media` (`store.py:130`) grava em disco sem teto de bytes.

### [P0-04] XSS via `dangerouslySetInnerHTML` em `PhoneDialog.tsx` e Faixa `172.*.*.*` Permissiva no Android
- **Onde:** `projmap/ui/app/components/PhoneDialog.tsx:50-52`, `projmap/android/capacitor.config.json:6-17`, `projmap/android/android/app/src/main/AndroidManifest.xml:5, 11-12`.
- **Risco:**
  1. `PhoneDialog.tsx:51` usa `dangerouslySetInnerHTML={{ __html: pair.qr_svg }}` sem sanitização em vez de renderizar o SVG de forma isolada (`<img src="data:image/svg+xml;utf8,..." />`).
  2. `capacitor.config.json:11` libera `"allowNavigation": [..., "172.*.*.*"]`, abrangendo IPs **públicos** (`172.0.x.x`–`172.15.x.x` e `172.32.x.x`–`172.255.x.x`, já que apenas `172.16.0.0/12` é privada RFC 1918), com `usesCleartextTraffic="true"`, `allowMixedContent: true` e `allowBackup="true"`.

### [P0-05] Servidor UDP `OscSensor` Aberto em `0.0.0.0:7001` com Vazamento de Memória + Segredos em Logs/Argv
- **Onde:** `projmap/interact/sensors.py:105, 117, 122-137`, `projmap/desktop/core.py:93-94`, `projmap/interact/stream.py:44`, `projmap/gdrive.py:287-293, 391-392`.
- **Risco:**
  1. `OscSensor` escuta em `0.0.0.0:7001` por padrão e adiciona entradas em `self._players[pid]` para cada pacote UDP recebido sem limite máximo de jogadores e sem nunca remover IDs expirados (DoS de memória e CPU a 60 Hz).
  2. `projmap/desktop/core.py:93-94` passa `--token <segredo>` na linha de comando do processo filho (visível na lista de processos do SO), e `projmap/interact/stream.py:44` não mascara senhas em URLs `rtsps://`.
  3. `projmap/gdrive.py:391-392` envia o header `Authorization: Bearer` ou `?key=` do Google Drive ao baixar `e.thumb` com `follow_redirects=True` sem validar o domínio de destino.

---

## 3. Pecados Arquiteturais (P1)

### 3.1 "God Files" no ProjMap
| Arquivo | Linhas | Responsabilidades Misturadas |
|---|---:|---|
| `projmap/ui/app/page.tsx` | **887** | 19 `useState`, 6 `useRef`, fila de `PUT`, polling, homografia inversa (`onBoundary`), detecção, atalhos de teclado, undo e 330 linhas de JSX. |
| `projmap/ui/app/components/Editor.tsx` | **838** | `ResizeObserver`, matrizes de coordenada, pipeline Canvas 2D de 230 linhas, máquina de arraste de 7 estados e geometria de feathering/lupa. |
| `projmap/ui/app/globals.css` | **633** | Tokens Tailwind v4 (`@theme inline`) misturados com 537 linhas de CSS global legado e seletores de tag sem escopo. |
| `projmap/effects/parachutes.py` | **560** | Simulação física + gerador de nuvens/avião + engine gráfica 2D própria (`_Tela`) + recorte de rostos. |
| `projmap/gdrive.py` | **490** | Parser de `.env`, OAuth PKCE, API Key auth, cliente HTTP Drive v3, controle de acesso de pastas, cache de thumbs PIL e download em stream. |
| `projmap/ui/app/remote/page.tsx` | **468** | 6 componentes no mesmo arquivo (`RemotePage`, `PairScreen`, `Slider`, `SurfaceCard`, `Looks`, `InteractCard`) + polling próprio. |
| `projmap/effects/engine.py` | **417** | Contexto OpenGL standalone, FBOs, loop de 60 Hz, visão YOLO, loopback de áudio WASAPI, critters, paraquedas e 28 uniforms GL. |
| `projmap/desktop/__main__.py` | **400** | GUI `tkinter` inteira, descoberta de hardware em threads, controle de subprocesso e parser de logs. |
| `projmap/interact/sensors.py` | **390** | Contrato `Sensor`, `SimSensor`, `OscSensor` UDP, geometria `solvePnP`, `PhoneSensor`, `WebcamSensor` e factory. |
| `projmap/ui/app/components/LayersPanel.tsx` | **367** | Lista reordenável de camadas, upload, formulário de propriedades e cálculo geométrico `fittedRect`. |

### 3.2 Lógica de Negócio/Geometria na UI, Closures HTTP e Globais Mutáveis
1. **Closures gigantes nas rotas FastAPI (`projmap/master/app.py:57-244`, `gdrive_api.py:30-191`, `interact/api.py:42-232`, `library_api.py:29-144`):** Todas as rotas são funções aninhadas dentro de `create_app`/`create_router`, guardando estado mutável em dicts locais (`holder`, `imported`, `media_meta`) sem locks de thread.
2. **Geometria matricial e I/O espalhados na camada de View (`projmap/ui/`):** `page.tsx:242-261, 313-360, 864-876` calcula inversão e multiplicação de matrizes 3×3 e transformação de vértices dentro do componente React; 13 componentes fazem chamadas diretas a `api.*`, e `sensor/page.tsx:83` chama `fetch()` direto sem passar por `api.ts`.
3. **Globais mutáveis no backend (`projmap/`):**
   - `projmap/interact/runtime.py:28`: `_current: Optional["InteractionRuntime"] = None` mutado com `global _current`.
   - `projmap/interact/nlp.py:100`: `_client_error` mutado com `global _client_error` sem lock.
   - `projmap/detect/classic.py:120`: `cv2.setRNGSeed(7)` altera a semente global do OpenCV no processo inteiro a cada chamada HTTP.
4. **Duplicações diretas de código:**
   - `rgbToHex` / `hexToRgb` triplicadas em `SurfacePanel.tsx:295-302`, `LayersPanel.tsx:360-367` e `remote/page.tsx:460-467`.
   - `order_quad` duplicada em `projmap/core/geometry.py:150-159` e `projmap/detect/classic.py:29-36`.
   - `load_image_rgba` duplicada em `projmap/content/factory.py:74-85` e `projmap/interact/render.py:171-185`.

---

## 4. Riscos de Quebra Silenciosa (P2) e Estado dos Quality Gates

### 4.1 Erros Engolidos Silenciosamente e Falhas de Thread/Render
1. **Crash da janela do projetor ao vivo quando um vídeo falha no 1º frame (`projmap/node/renderer.py:191` + `projmap/content/video.py:134`):** `VideoSource.frame_at()` levanta `RuntimeError("falha ao decodificar ...")` se o decodificador em background falhar antes do primeiro frame; `Renderer._draw_item()` não captura essa exceção, derrubando o `on_draw` do Pyglet durante o show.
2. **Thread `interact` sem `try/except` (`projmap/interact/runtime.py:84-92`):** Qualquer exceção em `self.step()` encerra a thread silenciosamente e congela a camada interativa.
3. **Perda silenciosa de dados de configuração (`projmap/library.py:63-64, 71-72` e `projmap/color_presets.py:55-56`):** `except (OSError, ValueError): return []` sem log — se o JSON falhar na leitura, retorna vazio e o próximo `save()` apaga todas as pastas/presets do usuário.
4. **UI presa eternamente em loading (`projmap/ui/app/components/DriveBrowser.tsx:47-49, 69`):** `catch { setStatus(null); }` mantém a mensagem `"Verificando o Google Drive…"` para sempre quando a API falha.
5. **Falso positivo de conectividade no Android (`projmap/android/www/launcher.js:83-94`):** `fetch(..., { mode: "no-cors" })` retorna resposta opaca e resolve `true` mesmo para HTTP 404/500, redirecionando a WebView para páginas de erro sem botão de voltar.
6. **Non-null assertion após `await` em `projmap/ui/app/sensor/page.tsx:117`:** `const video = videoRef.current!;` após carregamento assíncrono do MediaPipe/câmera lança `TypeError` se o componente desmontar antes.

### 4.2 Lacunas nos Quality Gates Atuais (Alvo da Fase 2)
- **Python (`projmap/`):** Nenhum `pyproject.toml`, `ruff` ou `mypy` configurado.
- **Frontend (`projmap/ui/`):** Script `"lint": "next lint"` existia sem `eslint` / `eslint-config-next` instalados, e faltava script `"typecheck": "tsc --noEmit"`.
- **CI (`.github/workflows/ci.yml`):** Misturava dependências do Auto Niche Engine com o ProjMap e **não executava os testes do `projmap/ui` (`npm test`) nem lint/typecheck**.
- **Hooks (`.claude/settings.json` e `.git/hooks/pre-commit`):** Inexistentes.
