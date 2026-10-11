# ProjMap — Lançador com janela + atalho no Menu Iniciar

## Resumo
Atalho **ProjMap** no Menu Iniciar que abre um lançador com janela: escolher
ou criar o show, onde sai a imagem e se o celular pode conectar, e **Abrir**.
Não precisa mais usar o terminal.

## Motivação
Pedido do usuário: "que a aplicação tenha um executável no menu iniciar".

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/desktop/core.py` | Lógica sem interface: preferências (`~/.projmap/launcher.json`), lista de shows, nome seguro de pasta, comando do mestre, leitura do link do celular no log |
| `projmap/desktop/__main__.py` | Lançador tkinter no tema do app: Show, Onde sai a imagem, Celular, Abrir/Parar, Abrir editor, Copiar link do celular, registro |
| `projmap/desktop/install.py` | Gera o ícone `.ico` e cria o atalho `.lnk` (Menu Iniciar; `--desktop`; `--uninstall`); `.desktop` no Linux |
| `tests/projmap/test_desktop.py` | 10 testes (inclui criar um `.lnk` real) |
| `projmap/GUIA.md` · `README.md` · `.gitignore` · `board/seed.py` | Instruções, ícone gerado fora do git, card |

## Como funciona
- O atalho chama `pythonw.exe -m projmap.desktop` (sem janela de terminal) do
  ambiente que tem as dependências, na pasta do repositório.
- **Abrir** inicia o mestre com `python.exe` em segundo plano (sem console),
  lê o log, mostra o link do celular (com token) e abre o editor. **Parar** e
  fechar a janela encerram o mestre, com confirmação se houver um show rodando.
- **Por que não um `.exe` único (PyInstaller):** com OpenCV, PyAV e
  OpenGL/pyglet, o pacote passa de centenas de MB e quebra com facilidade. O
  atalho reaproveita o ambiente Python já instalado e atualiza junto com o
  código.

## Como validar
```bash
pytest -q tests/projmap/test_desktop.py       # 10 verdes
python -m projmap.desktop.install             # cria o atalho
# Menu Iniciar → ProjMap
```
Verificado na máquina do usuário:
- o atalho foi criado em `%APPDATA%\...\Start Menu\Programs\ProjMap.lnk`, com
  ícone, `pythonw.exe` e a pasta do repositório;
- abrir pelo atalho mostra o lançador;
- o caminho do **Abrir** (mesmo comando e leitor de log) subiu o mestre: o
  editor respondeu 200, o link do celular foi capturado e o `terminate()`
  encerrou o processo.

## Critério de aceite
- [x] "ProjMap" no Menu Iniciar, com ícone, sem terminal
- [x] Escolher/criar show, saída e celular; preferências lembradas
- [x] Link do celular à mão; fechar encerra o show com confirmação
- [x] Remover atalhos (`--uninstall`)
- [ ] Instalador para outra máquina (hoje: clonar, criar o ambiente, rodar o install)

## Pendências / próximos
- Instalador completo para PCs sem Python (ex.: Inno Setup + Python embutido).
- Mostrar o QR do celular no próprio lançador.
- Escolher o monitor do projetor por nome/resolução (hoje: número).
