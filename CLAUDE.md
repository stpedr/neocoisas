# CLAUDE.md — Convenções e Guardrails do ProjMap (Standalone)

Instruções obrigatórias para qualquer sessão de IA ou desenvolvedor trabalhando neste repositório.

> **Foco e Isolamento:** O projeto ativo neste repositório é o **ProjMap** ([`projmap/`](projmap/) e [`tests/projmap/`](tests/projmap/)). O ProjMap é um sistema **100% autônomo (standalone)** de projeção mapeada e **NÃO deve depender nem importar absolutamente nada** dos arquivos legados do Auto Niche Engine na raiz (`agents/`, `server.py`, `engine.py`, `review/`, `publishers/`, `web/`, etc.).
>
> As regras arquiteturais completas e proibições estritas estão em [`.agents/rules/architecture.md`](.agents/rules/architecture.md) e o diagnóstico atual em [`AUDIT_REPORT.md`](AUDIT_REPORT.md).

---

## 1. Regras Estritas (Travas contra "Vibe Code")

1. **Isolamento Total (`TID251`):** É **PROIBIDO** importar qualquer módulo fora de `projmap/` (como `agents.*`, `server`, `settings`, etc.). O linter `ruff` bloqueia automaticamente esses imports.
2. **TDD Obrigatório no Frontend (`projmap/ui/`):** Todo componente ou rota novo/migrado exige teste escrito **antes** (Vitest + Testing Library em `*.test.tsx` e/ou Playwright em `e2e/`).
3. **Proibido Quebra Silenciosa:**
   - Proibido `except Exception: pass` ou `catch {}` sem log ou tratamento explícito de estado de erro.
   - Proibido `any` ou `@ts-ignore` em TypeScript (`strict: true`).
   - Proibido `dangerouslySetInnerHTML` sem sanitização.
   - Proibido `dict[str, Any]` solto ou `**kwargs` da rede direto para construtores em rotas FastAPI — use sempre schemas Pydantic v2 com limites (`ge`, `le`, `max_length`, `allow_inf_nan=False`).
   - Proibido escrita não-atômica (`write_text` direto) em JSONs de projeto/configuração.
4. **Canvas e Geometria Protegidos:** Não misture cálculos de homografia/geometria dentro de componentes React quando puderem viver em `projmap/ui/app/lib/geometry.ts` com testes unitários.
5. **Segredos e Configs:** Nunca coloque tokens/senhas no git, no chat ou em linha de comando (`argv` de subprocessos). Use variáveis de ambiente / `.env`.

---

## 2. Regra de Entrega (Obrigatória)

Toda entrega (feature, fase de migração, correção de segurança ou card concluído) deve incluir um documento em `docs/entregas/<slug>.md` contendo:
1. **Resumo** · 2. **Motivação** · 3. **O que mudou** · 4. **Como funciona** · 5. **Como validar** · 6. **Critério de aceite** · 7. **Pendências / próximos**.

Atualize também o card correspondente em `board/seed.py` quando aplicável.

---

## 3. Ambiente e Comandos de Validação (Quality Gates)

- **Guias do ProjMap:** [`projmap/GUIA.md`](projmap/GUIA.md) (uso), [`projmap/README.md`](projmap/README.md) e [`projmap/ARCHITECTURE.md`](projmap/ARCHITECTURE.md) (engenharia), [`docs/projmap/PLANO.md`](docs/projmap/PLANO.md) (decisões D1–D9), [`docs/planejamento/design-system-projmap-ui.md`](docs/planejamento/design-system-projmap-ui.md) (design system).
- **Venv dedicada:** `.venv-projmap` (`pip install -r requirements-projmap-master.txt`).
- **ORM (Fase 8):** SQLAlchemy 2.0 async + `aiosqlite` + Alembic para catálogo/biblioteca/presets; `project.json` continua sendo a fonte de verdade de cada show.
- **Sincronia de branch:** Confira sempre se o branch está atualizado com `origin/claude/new-session-heke9n` / `origin/main` antes de abrir uma frente grande.

### Checklist obrigatório antes de cada commit:
```powershell
# Backend ProjMap (Ruff + Mypy + Pytest)
.\.venv-projmap\Scripts\ruff.exe check projmap tests/projmap
.\.venv-projmap\Scripts\mypy.exe projmap
.\.venv-projmap\Scripts\pytest.exe -q tests/projmap

# Frontend ProjMap UI (Typecheck + ESLint + Vitest + Build)
cd projmap/ui
npm run typecheck
npm run lint
npm run test
npm run build
```
