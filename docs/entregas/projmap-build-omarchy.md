# ProjMap — build de release para Omarchy (Arch Linux / Hyprland)

## 1. Resumo
Pacote `projmap-<versão>-omarchy-x86_64.tar.gz` que instala o ProjMap num
Omarchy (ou Arch) com um comando: `./install.sh`. Leva a UI já compilada, cria
um venv com Python 3.12 gerenciado pelo `uv`, os comandos `projmap`,
`projmap-master`, `projmap-node` e o atalho no menu de apps (Super+Espaço).
Publicado junto com a release v1.1.0.

## 2. Motivação
"faça uma build dessa versão mais atual para o omarchy". Até aqui o Linux só
tinha o passo a passo manual do `projmap/README.md` (venv + `npm run build`),
o que exige Node.js e Python com tkinter na máquina do show.

## 3. O que mudou
| Arquivo | Mudança |
|---|---|
| `packaging/omarchy/build.py` | **Novo**: gera o tarball em `dist/` a partir do `projmap/` (da UI só `ui/out`, sem `android/`, `node_modules`, caches), requirements, `LICENSE`, `VERSION`; converte finais de linha para LF |
| `packaging/omarchy/install.sh` | **Novo**: instalador (pacman → `uv`, mesa/libglvnd, libs X11 do XWayland, PortAudio/libpulse, `xdg-utils`, `android-tools`), cópia para `~/.local/share/projmap`, venv `uv` com Python 3.12, wrappers em `~/.local/bin`, atalho via `projmap.desktop.install`; `--no-pacman`, `--uninstall`, atualização reaproveitando `.venv` e `.env` |
| `packaging/omarchy/README-OMARCHY.md` | **Novo**: instalar, usar, dicas de Hyprland (regra de janela do projetor pelo título `ProjMap · <nó>`) |
| `.gitignore` | `dist/` |
| `pyproject.toml`, `projmap/ui/package.json` | versão 1.1.0 |

## 4. Como funciona
- **Python gerenciado pelo `uv`**: o Arch atualiza o `python` do sistema rápido
  (3.14+), e algumas rodas (onnxruntime, moderngl, av) chegam depois. O venv usa
  Python 3.12 do `uv` (python-build-standalone), que já traz tkinter — o
  Lançador funciona sem o pacote `tk`. Dá para trocar com `PROJMAP_PYTHON=3.13`.
- **Saída no Hyprland**: pyglet roda via XWayland (ligado por padrão no Omarchy).
- **Atualização**: rodar o `install.sh` de uma versão nova troca `projmap/` e
  mantém `.venv`/`.env`; as dependências são reconciliadas pelo `uv pip install`.
- Nada no `projmap/` mudou — o instalador reusa `projmap.desktop.install` para
  o `.desktop` (FreeDesktop) já existente.

## 5. Como validar
```bash
cd projmap/ui && npm ci && npm run build && cd ../..
python packaging/omarchy/build.py
# numa máquina Linux:
tar xzf dist/projmap-1.1.0-omarchy-x86_64.tar.gz && cd projmap-1.1.0-omarchy-x86_64
./install.sh            # (ou --no-pacman fora do Arch, com uv instalado)
projmap-master --project /tmp/teste.projmap --no-output --no-interact --port 8199
curl -I http://127.0.0.1:8199/        # 200
```
Validado em Ubuntu 26.04 (WSL) com `--no-pacman` e HOME isolado: instalação
completa, `.desktop` criado, imports de todos os módulos (moderngl, pyglet, cv2,
av, onnxruntime, tkinter, mcp) e o mestre respondendo 200 em `/`, `/remote/` e
`/api/project`.

## 6. Critério de aceite
- [x] `build.py` gera o tarball só com o necessário (~7,5 MB) e scripts em LF.
- [x] `install.sh` instala, cria comandos e atalho, e desinstala.
- [x] Mestre sobe a partir da instalação e serve UI + API.
- [ ] Teste num Omarchy real com projetor (janela pyglet/XWayland, áudio PipeWire).

## 7. Pendências / próximos
- Validar a saída em tela cheia no projetor sob Hyprland e confirmar a sintaxe
  de `windowrule` da versão instalada.
- Gerar o tarball no CI (GitHub Actions) a cada tag, em vez de localmente.
- Avaliar um `PKGBUILD` (AUR) se a instalação virar rotina.
