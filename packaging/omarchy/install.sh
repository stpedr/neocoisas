#!/usr/bin/env bash
# ProjMap — instalador para Omarchy / Arch Linux.
#
#   ./install.sh                 instala em ~/.local/share/projmap e cria o atalho
#   ./install.sh --no-pacman     pula os pacotes do sistema (já instalados)
#   ./install.sh --uninstall     remove o atalho e a instalação
#
# Variáveis: PROJMAP_HOME (destino), PROJMAP_PYTHON (versão do Python do venv, padrão 3.12).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${PROJMAP_HOME:-$HOME/.local/share/projmap}"
PY_VER="${PROJMAP_PYTHON:-3.12}"
BIN_DIR="$HOME/.local/bin"
USE_PACMAN=1

for arg in "$@"; do
  case "$arg" in
    --no-pacman) USE_PACMAN=0 ;;
    --uninstall)
      if [ -x "$DEST/.venv/bin/python" ]; then
        (cd "$DEST" && "$DEST/.venv/bin/python" -m projmap.desktop.install --uninstall) || true
      fi
      rm -f "$BIN_DIR/projmap" "$BIN_DIR/projmap-master" "$BIN_DIR/projmap-node"
      rm -rf "$DEST"
      echo "ProjMap removido (shows em ~/.projmap e na pasta de shows foram mantidos)."
      exit 0 ;;
    -h|--help) sed -n 2,9p "$0"; exit 0 ;;
    *) echo "Opção desconhecida: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1;35m==>\033[0m %s\n' "$*"; }

if [ "$USE_PACMAN" = 1 ] && command -v pacman >/dev/null 2>&1; then
  say "Pacotes do sistema (pacman)"
  # uv: venv com Python gerenciado (já inclui tkinter p/ o lançador)
  # mesa/libglvnd/libx*: OpenGL + XWayland p/ moderngl+pyglet · portaudio/libpulse: captura de áudio (PipeWire)
  # xdg-utils: abrir o editor no navegador · android-tools: sensor do celular via ADB (opcional)
  sudo pacman -S --needed --noconfirm uv mesa libglvnd libx11 libxext libxrandr libxinerama libxi portaudio libpulse xdg-utils android-tools
elif ! command -v uv >/dev/null 2>&1; then
  echo "Instale o 'uv' (sudo pacman -S uv) ou rode sem --no-pacman." >&2
  exit 1
fi

say "Copiando arquivos para $DEST"
mkdir -p "$DEST"
# preserva .venv e .env de uma instalação anterior (atualização)
rm -rf "$DEST/projmap"
cp -r "$SRC/projmap" "$DEST/"
cp "$SRC"/pyproject.toml "$SRC"/requirements-projmap-*.txt "$SRC"/LICENSE "$SRC"/README-OMARCHY.md "$SRC"/VERSION "$DEST/"
cp "$SRC/install.sh" "$DEST/install.sh"

say "Ambiente Python $PY_VER (uv)"
if [ ! -x "$DEST/.venv/bin/python" ]; then
  uv venv --python "$PY_VER" "$DEST/.venv"
fi
uv pip install --python "$DEST/.venv/bin/python" -r "$DEST/requirements-projmap-master.txt"

say "Comandos em $BIN_DIR"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/projmap" <<EOF
#!/usr/bin/env bash
cd "$DEST" && exec "$DEST/.venv/bin/python" -m projmap.desktop "\$@"
EOF
cat > "$BIN_DIR/projmap-master" <<EOF
#!/usr/bin/env bash
cd "$DEST" && exec "$DEST/.venv/bin/python" -m projmap.master "\$@"
EOF
cat > "$BIN_DIR/projmap-node" <<EOF
#!/usr/bin/env bash
cd "$DEST" && exec "$DEST/.venv/bin/python" -m projmap.node "\$@"
EOF
chmod +x "$BIN_DIR/projmap" "$BIN_DIR/projmap-master" "$BIN_DIR/projmap-node"

say "Atalho no menu de apps (Super+Espaço)"
(cd "$DEST" && "$DEST/.venv/bin/python" -m projmap.desktop.install)

say "Pronto! ProjMap $(cat "$DEST/VERSION") instalado."
echo "  Abra pelo menu (Super+Espaço → ProjMap) ou rode: projmap"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "  (adicione $BIN_DIR ao PATH para usar os comandos no terminal)";; esac
