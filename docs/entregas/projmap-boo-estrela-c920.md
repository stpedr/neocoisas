# ProjMap — Castelo dos Boos (sprites PNG, estrela de poder) + webcam C920

## Resumo
- O jogo interativo aceita **imagens do usuário**: fundo (castelo) e sprites
  com par normal/vergonha. Os fantasmas são opacos quando perseguem e
  translúcidos quando olhados, como no Mario.
- Uma **estrela** atravessa a parede em senoide. Quem a pega fica
  invencível e derrota os fantasmas que tocar.
- Suporte à **Logitech C920**: escolha por nome, MJPG 720p a 30 fps e foco
  fixo, com seleção no lançador.

## Motivação
Pedidos do usuário:
- usar a C920 nas interações;
- recortar os Boos das fileiras 2 e 3 da folha enviada e usar o castelo de
  fundo;
- "vivos quando não olham, translúcidos quando olham";
- uma estrela que passa em senoide e, se pega, derrota os fantasmas.

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/interact/scene.py` | Sprite `image` + `Skin` (normal/vergonha), `shy_alpha`, `pixelated`; `background_image`/`background_fit`; `StarSpec`; preset `castelo-boo`; imagens só de `~/.projmap/scenes` (sem caminho absoluto nem `..`) |
| `projmap/interact/sim.py` | Estrela (aparece, senoide, pegar, sumir), invencibilidade (`power`), fantasmas `scared` fugindo, `defeated` com volta (`respawn_s`); eventos `star_appeared/caught/missed`, `defeated` |
| `projmap/interact/render.py` | Fundo com imagem; sprites PNG nítidos (vizinho mais próximo); vergonha translúcida; assustado piscando; estrela (PNG ou pixelada de arco-íris) com brilho e faíscas; "puf"; borda de arco-íris com barra de tempo |
| `projmap/interact/cameras.py` | Novo: lista câmeras por nome (DirectShow/v4l2), `auto` prefere C920/Logitech e ignora virtuais, abre em MJPG 1280×720@30 com foco fixo; `python -m projmap.interact.cameras` |
| `projmap/interact/sensors.py` · `master/__main__.py` | Webcam usa o módulo de câmeras; `--camera`, `--camera-size` |
| `projmap/desktop/*` | Lançador: card *Interação* (simulada / webcam / celular) e escolha da câmera |
| `README.md` (raiz) | Aviso apontando para o ProjMap (o usuário abriu o Auto Niche pelo README da raiz) |
| `projmap/GUIA.md` · `board/seed.py` | Seção do jogo e da C920; card |
| `tests/projmap/test_boo_star.py` · `test_desktop.py` | 16 testes novos |

As imagens (recortes dos Boos, castelo e estrela) ficam em
`~/.projmap/scenes/boo/` e **não** são versionadas (arte da Nintendo, de uso
do usuário).

## Como funciona
- **Recorte:** preenche o fundo quadriculado (cinza/branco pouco saturado) a
  partir da borda de cada célula, até o contorno escuro do fantasma, e fica
  com o maior pedaço (sem o número da célula). Pares de vergonha: 10→9 e
  4/5/6/7→8.
- **Pegar a estrela:** o ponto da parede à frente da pessoa (o mesmo usado
  pelos fantasmas) fica a menos de `catch_radius` da estrela enquanto ela
  passa. Ou seja, é preciso se posicionar na trajetória.
- **Poder:** perseguidores invertem a direção e fogem (`flee_speed`); um toque
  derrota (some com "puf" e volta após `respawn_s`); não há "pegou você".
  A próxima estrela vem `interval_s` depois do fim do poder.
- **C920:** sem MJPG ela entrega 1080p a ~5 fps; em MJPG 720p, 30 fps. O
  índice do DirectShow (ordem do `ffmpeg -list_devices`) é o mesmo do
  `cv2.CAP_DSHOW`.

## Como validar
```bash
pytest -q                                      # 423 verdes (16 novos)
python -m projmap.interact.cameras             # lista câmeras; marca a 'auto'
python -m projmap.master --project shows/x.projmap --windowed --open --sensor webcam --camera C920
# editor → Interativo → "Castelo dos Boos"; superfície com fonte "Cena interativa"
```
Verificado:
- quadros renderizados do jogo: de costas (Boos opacos perseguindo), olhando
  (vergonha + translúcidos), estrela em voo (senoide 0,25↔0,64),
  invencibilidade (borda e barra) e Boo derrotado ("puf");
- render 1280×720 em 11 ms/quadro;
- sensor de webcam ao vivo (câmera do notebook, a C920 não estava conectada):
  escolha automática da câmera física, 1280×720 e rosto detectado em 25/30
  amostras.

## Critério de aceite
- [x] Boos recortados das fileiras 2 e 3, castelo de fundo
- [x] Opacos perseguindo, translúcidos (vergonha) quando olhados
- [x] Estrela em senoide; pegar dá invencibilidade e derrota fantasmas, que voltam
- [x] Câmera por nome, `auto` prefere C920 e ignora virtuais; MJPG 720p30; no lançador
- [x] `pytest -q` verde
- [ ] Testado com a C920 conectada e com o projetor (a câmera não estava presente)

## Pendências / próximos
- Ajustar `catch_radius`/velocidades no espaço real (depende da distância da câmera).
- Placar (fantasmas derrotados) e som (estrela/derrota) por OSC para o TouchDesigner.
- Editar a cena (imagens, estrela) pela UI; hoje é pelo preset/JSON.
