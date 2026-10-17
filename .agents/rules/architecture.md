# Regras Estritas de Arquitetura — ProjMap Standalone (`.agents/rules/architecture.md`)

> Este documento é a referência arquitetural obrigatória para agentes de IA e desenvolvedores atuando neste repositório. O foco ativo é exclusivamente o **ProjMap** (`projmap/` + `tests/projmap/`), que deve operar **100% independente** dos arquivos legados do Auto Niche Engine na raiz.

---

## 1. Isolamento Absoluto do ProjMap (Standalone)

1. **Fronteira de Pacote Rígida:**
   - Todo o código de produção do ProjMap vive sob `projmap/` e seus testes sob `tests/projmap/`.
   - **PROIBIDO** importar qualquer módulo do legado Auto Niche Engine (`agents`, `server`, `engine`, `jobs`, `scheduler`, `settings`, `registry`, `review`, `publishers`, `telegram_bot`, `raspberry_pi`, `render`, `render_carousel`, `brand`, `carousel_art`, `dashboard`, `web`) dentro de `projmap/` ou `tests/projmap/`.
   - Essa regra é fiscalizada automaticamente pelo Ruff (`flake8-tidy-imports` / `TID251` em `pyproject.toml`).
2. **Ambiente Virtual Dedicado:**
   - O ProjMap usa exclusivamente `.venv-projmap` (`requirements-projmap-master.txt` / `requirements-projmap-node.txt`), nunca misturado com `requirements.txt` do Auto Niche Engine.

---

## 2. Estrutura de Pastas Obrigatória (`projmap/`)

```text
projmap/
├── core/           # Domínio puro e persistência do projeto (project.py, geometry.py, state.py, store.py)
│                   # Zero dependência de FastAPI, OpenGL, Pyglet ou UI.
├── master/         # Servidor HTTP/WS FastAPI (app.py, auth.py, remote.py, library_api.py, gdrive_api.py, db/)
│                   # Apenas roteamento, autenticação/autorização e delegação para serviços/domínio.
├── node/           # Janela Pyglet + Renderizador ModernGL (window.py, renderer.py)
├── mapping/        # Matemática de warp, homografia e malha (warp.py)
├── content/        # Fontes de mídia (video.py, gif.py, factory.py)
├── detect/         # Detecção clássica/IA de candidatos de superfície na foto (classic.py)
├── interact/       # Camada interativa 60 Hz (runtime.py, sim.py, render.py, sensors.py, nlp.py, stream.py, api.py)
├── effects/        # Motor visual_frames: shaders GL, YOLO26 ONNX, áudio loopback, critters, paraquedas
├── desktop/        # Lançador desktop nativo (tkinter, install.py, core.py)
├── tools/          # Utilitários de CLI, ADB e download de modelos (fetch_models.py, adb.py, demo.py)
├── ui/             # Frontend Next.js 14 (export estático) + Tailwind v4 + shadcn/ui + Framer Motion
│   ├── app/
│   │   ├── components/
│   │   │   └── ui/ # Primitivos shadcn/ui (Button, Card, Checkbox, Dialog, Input, Select, Slider, Badge)
│   │   ├── lib/    # Cliente de API (api.ts), geometria (geometry.ts), preview (preview.ts), tipos (types.ts)
│   │   ├── remote/ # Controle mobile de palco (/remote)
│   │   └── sensor/ # Sensor facial mobile (/sensor)
│   └── e2e/        # Testes E2E Playwright (editor.spec.ts)
└── android/        # Wrapper Capacitor 7 + lançador mobile (www/launcher.js)
```

---

## 3. O Que é ESTRITAMENTE PROIBIDO ("Anti-Vibe-Code Guardrails")

### 3.1 Segurança (P0)
- **PROIBIDO** confiar apenas em `is_loopback` sem validar `Host` e `Origin` em requisições mutáveis (`POST`/`PUT`/`PATCH`/`DELETE`) ou conexões `WebSocket`.
- **PROIBIDO** receber `dict[str, Any]` solto em rotas FastAPI ou repassar `**kwargs` vindos da rede direto para construtores (`get_sensor(**body.options)`, `setattr` dinâmico sem schema Pydantic com limites `ge`/`le` e `allow_inf_nan=False`).
- **PROIBIDO** usar `dangerouslySetInnerHTML` em `projmap/ui/` sem sanitização explícita.
- **PROIBIDO** passar tokens/senhas em argumentos de linha de comando (`--token` em `subprocess`) ou logar URLs contendo segredos sem mascaramento (`rtsps?://`).
- **PROIBIDO** criar arquivos/diretórios temporários (`tempfile.mkdtemp` / `mkstemp`) sem limpeza garantida (`try/finally` ou `BackgroundTask`).

### 3.2 Arquitetura e Estado (P1)
- **PROIBIDO** adicionar lógica de geometria matricial, chamadas diretas `fetch()` (fora de `app/lib/api.ts`) ou regras de negócio dentro de componentes visuais React em `projmap/ui/app/components/`.
- **PROIBIDO** criar novos seletores CSS globais de tag (`input`, `select`, `label`, `h2`, `button`) em `projmap/ui/app/globals.css`. Todo componente novo ou migrado deve usar Tailwind v4 + primitivos em `app/components/ui/`.
- **PROIBIDO** gravar arquivos JSON de configuração ou estado (`project.json`, `active.json`, `library.json`, `color-presets.json`, `launcher.json`) com `Path.write_text()` direto — toda escrita persistente deve ser **atômica** (`tempfile` no mesmo diretório + `os.replace` com limpeza do `.tmp` em caso de exceção).
- **PROIBIDO** criar variáveis globais mutáveis (`global _x`) sem encapsulamento ou `threading.Lock`.

### 3.3 Confiabilidade, Tipagem e Testes (P2)
- **PROIBIDO** usar `except Exception: pass`, `except: pass` ou `.catch(() => {})` mudo em operações de rede, banco ou leitura de configuração sem registrar log (`logging.warning`/`debug`) ou expor estado de erro na UI.
- **PROIBIDO** usar `any` ou `@ts-ignore` em `projmap/ui/`.
- **PROIBIDO** migrar ou criar componente/rota em `projmap/ui/` sem escrever o teste (Vitest / Playwright) **antes** da implementação (TDD obrigatório).

---

## 4. Fluxo Obrigatório de Validação (Quality Gates)

Antes de qualquer commit na branch de trabalho do ProjMap, **todos** os comandos abaixo devem passar com código de saída `0`:

```powershell
# 1. Linter e Typecheck Python (ProjMap isolado)
.\.venv-projmap\Scripts\ruff.exe check projmap tests/projmap
.\.venv-projmap\Scripts\mypy.exe projmap

# 2. Testes Automatizados do Backend ProjMap
.\.venv-projmap\Scripts\pytest.exe -q tests/projmap

# 3. Typecheck, Lint, Testes Unitários e Build do Frontend ProjMap
cd projmap/ui
npm run typecheck
npm run lint
npm run test
npm run build
```
