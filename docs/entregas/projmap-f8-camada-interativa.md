# ProjMap F8 — Camada interativa: IA + sensores + TouchDesigner

## Resumo

Projeções que reagem às pessoas. Você descreve a experiência em texto (por
exemplo *"fantasmas que param quando eu olho e me buscam quando viro de
costas"*) e o sistema monta a cena. Um sensor (pessoa simulada, webcam ou
Kinect via TouchDesigner) informa posição e direção do olhar, e o visual sai
numa superfície do ProjMap ou no TouchDesigner, via OSC. A mecânica dos
"fantasmas tímidos" funciona ponta a ponta, na parede.

## Motivação

Pedido: gerar visuais com TouchDesigner, integrar câmera, Kinect ou sensores,
usar NLP para descrever o que gerar, e reproduzir a mecânica "param quando você
olha, te buscam quando você vira" dentro das projeções, para experiências
imersivas e interativas.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `projmap/interact/world.py` | Parede, pessoa e **região do olhar**: ponto onde o olhar cruza a parede + disco do FOV. De costas ou sem rosto, não olha nada. |
| `projmap/interact/scene.py` | `SceneSpec` (pydantic): sprites `ghost/orb/firefly/fish` e comportamentos `chase_player`, `flee_player`, `wander`, `seek_gaze`, `freeze_when_watched`. Presets: fantasmas tímidos, vaga-lumes do olhar, cardume. |
| `projmap/interact/sim.py` | Simulação determinística: soma de comportamentos, congelar quando olhado, separação entre entidades, evento `caught` com flash e reset. |
| `projmap/interact/nlp.py` | Texto → cena. Usa o LLM do repo (`agents.llm`), com validação e uma rodada de correção; se falhar, parser por palavras-chave em pt/en. A resposta informa a origem. |
| `projmap/interact/sensors.py` | Factory `get_sensor`: `sim` (manual/automático), `osc` (Kinect via TD, NI mate, etc.) e `webcam` (MediaPipe FaceLandmarker + `solvePnP` para o yaw). |
| `projmap/interact/outputs.py` | OSC para o TouchDesigner: `/projmap/frame`, `entity`, `player`, `event`, `scene`. |
| `projmap/interact/render.py` | Renderer nativo: fantasma original (tímido cobre o rosto), orbes, vaga-lumes, peixes; overlay de debug do olhar. |
| `projmap/interact/runtime.py`, `api.py`, `__main__.py` | Laço a 60 Hz, rotas `/api/interact/*` e CLI standalone (`python -m projmap.interact`, com `--preview`). |
| `projmap/interact/touchdesigner/*.py` | Callbacks do OSC In DAT (tabela para instancing) e Execute DAT Kinect→OSC. **Não executados no TD.** |
| `projmap/interact/README.md` | Guia: mecânica, NLP, webcam, Kinect via TD, TD desenhando, protocolo, API, licenças. |
| `projmap/core/project.py`, `content/factory.py` | Nova fonte de superfície `interactive`, que passa pelo warp/blend como um vídeo. |
| `projmap/master/*` | Mestre sobe a camada por padrão (`--sensor`, `--sensor-port`, `--osc-out`, `--no-interact`) e salva a cena em `scenes/active.json`. |
| `projmap/ui/*` | Card **Interativo** (texto → cena, presets, pessoa simulada, estado ao vivo, "Pegou!") e fonte "Cena interativa". |
| `tests/projmap/test_interact.py` | 27 testes: olhar, perseguir/congelar/pegar, fuga, seguir olhar, determinismo, separação, NLP (LLM falso + fallback), yaw por solvePnP, OSC ida e volta, render, superfície na GPU, API. |
| Docs/board/reqs | `ARCHITECTURE.md` §8, README, PLANO (F8), card F8 em Revisão, `python-osc` nos requirements. |

## Como funciona

1. **Texto → cena.** Pelo LLM, ou pelo fallback, sai uma `SceneSpec` validada.
   Só há peças prontas; o LLM não gera código.
2. **Sensor → pessoas.** Para cada pessoa: `x`, `distance`, `yaw`, `tracked` e
   `face`.
3. **Simulação a 60 Hz.** Calcula a região do olhar de cada pessoa. Os
   perseguidores vão para o ponto da parede à frente dela. Quem está dentro do
   olhar congela (e o tímido cobre o rosto). Encostar dispara `caught`.
4. **Visual.**
   - Nativo: a fonte `interactive` desenha o estado em RGBA, e o ProjMap aplica
     warp, máscara e mistura.
   - TouchDesigner: recebe o estado por OSC e desenha com instancing.
5. **Kinect.** O TD lê o Kinect (Kinect CHOP) e manda `/player` por OSC. Para
   detectar "de costas" com segurança, soma-se `face` de um detector de rosto.

## Como validar

```bash
pip install -r requirements-projmap-master.txt
xvfb-run -a pytest -q tests/projmap          # 75 passed

# Na UI (pessoa simulada): card "Interativo" → texto → "Gerar cena";
# numa superfície, Fonte = "Cena interativa"; "Olhar a parede" / "Virar de costas".
python -m projmap.master --project shows/demo.projmap --windowed --open

# Só o motor + TouchDesigner
python -m projmap.interact --preset fantasmas-timidos --osc-out 127.0.0.1:7000 --preview --windowed --debug
```

Validação feita nesta entrega, com Xvfb, Chromium/Playwright e um ouvinte OSC:

- **A sua frase, digitada no card da UI**, virou "Fantasmas tímidos" pelo
  fallback (não há LLM configurado neste ambiente).
- **Olhando a parede:** os 5 fantasmas ficaram `shy`. A captura da saída
  mostra os do olhar parados cobrindo o rosto e os de fora avançando.
- **De costas:** os 5 passaram a `move`, e o flash de "pegou" disparou.
- **OSC na porta 7000:** ~57 frames/s com as 5 entidades e a pessoa.
- **Zero erros de JS.**

## Critério de aceite

- [x] Texto em linguagem natural gera uma cena válida, com e sem LLM, e a
      origem é informada.
- [x] Mecânica dos fantasmas: param e cobrem o rosto quando olhados, perseguem
      quando a pessoa está de costas, "pegou" dispara flash e reset.
- [x] Sensores plugáveis: simulado, OSC (Kinect via TD) e webcam (pose da
      cabeça testada com rostos sintéticos).
- [x] Visual no ProjMap, em qualquer superfície mapeada, e estado via OSC para
      o TouchDesigner.
- [x] Testes automatizados (27 novos) e E2E com UI e saída.
- [ ] Validar com **webcam real** e **Kinect real**.
- [ ] Validar os **scripts dentro do TouchDesigner**.
- [ ] Testar com o **LLM configurado** (`config.json`/Ollama).

## Pendências / próximos

- Rodar no seu hardware: webcam, Kinect com TD e o LLM do repo configurado.
- Várias pessoas e várias paredes (modelo 3D da sala).
- Sons nos eventos ("pegou").
- Sprites gerados por IA (factories de imagem do repo).
- NDI do TD de volta para o ProjMap (F5).
- Direitos autorais: o fantasma é um design original. Não usar o nome nem a
  arte do Boo (Nintendo) em show público.
