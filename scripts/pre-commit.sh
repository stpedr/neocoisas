#!/usr/bin/env sh
# Git pre-commit hook — ProjMap Standalone Quality Gates
# Trava commits que falhem no linter (Ruff / ESLint) ou no typecheck (Mypy / tsc).

set -e

echo "[pre-commit] Verificando Quality Gates do ProjMap..."

# 1. Backend Python (ProjMap)
if [ -x ".venv-projmap/Scripts/ruff.exe" ]; then
  .venv-projmap/Scripts/ruff.exe check projmap tests/projmap
  .venv-projmap/Scripts/mypy.exe
elif command -v ruff >/dev/null 2>&1; then
  ruff check projmap tests/projmap
  mypy
fi

# 2. Frontend Next.js (projmap/ui) — roda quando houver alterações em projmap/ui
if git diff --cached --name-only | grep -q "^projmap/ui/"; then
  echo "[pre-commit] Validando projmap/ui (typecheck + lint)..."
  (cd projmap/ui && npm run typecheck && npm run lint)
fi

echo "[pre-commit] OK — todos os checks passaram."
