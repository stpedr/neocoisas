# ProjMap — Saída vai sozinha para o projetor + sensor da C920 não morre mais

## Resumo
A escolha do monitor não depende mais da ordem em que o Windows lista as telas.
`auto` (o novo padrão) escolhe o projetor, e o lançador mostra as telas com a
resolução de cada uma. Também corrige o sensor da C920, que parava com
"Input timestamp must be monotonically increasing".

## Motivação
"Mesmo escolhendo o monitor 2, ele não joga a projeção para o projetor." Na
máquina do usuário o Windows listou o **projetor como índice 0** (1024×768 em
x=2560) e o notebook como 1. O "monitor 1" caía no notebook, e o "2", que não
existe, também caía no notebook (a última tela).

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/node/screens.py` | Novo: ordem estável (0 = principal, depois da esquerda para a direita); `auto` = primeira não principal; `python -m projmap.node.screens` |
| `projmap/node/window.py` | Usa a escolha estável; avisa quando só há uma tela (modo Duplicar); protege o `WM_DPICHANGED` do pyglet (notebook 150% → projetor 100%) |
| `projmap/master/__main__.py` | `--display` aceita `auto` (padrão), `principal` ou número |
| `projmap/desktop/*` | Lista de telas com resolução no lançador; preferência antiga numérica vira `auto` |
| `projmap/interact/sensors.py` | Horário estritamente crescente para o MediaPipe; quadro com erro é ignorado em vez de matar a thread |
| `tests/projmap/test_screens.py` | 4 testes (inclui o arranjo real do usuário) |

## Como validar
```bash
python -m projmap.node.screens        # mostra as telas e qual o 'auto' usa
python -m projmap.master --project shows/x.projmap   # abre no projetor
```
Na máquina do usuário: a janela abriu em `\.\DISPLAY5` (x=2560..3584,
y=0..768, o projetor), sem o erro de DPI, a ~150 fps. `pytest -q`: 439 verdes.

## Critério de aceite
- [x] Saída abre no projetor sem precisar adivinhar o número
- [x] Lançador lista as telas
- [x] Sensor da C920 não para no erro de horário
