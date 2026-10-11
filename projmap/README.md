# ProjMap — projeção mapeada assistida por IA

Mapeamento de projeção com vários projetores em rede, controlados a partir de um
único computador. Neste estágio (**F1**) o sistema tem **um projetor, local**:
você desenha as superfícies sobre uma foto, arrasta os cantos, escolhe vídeo,
GIF ou imagem para cada uma, e a parede atualiza ao vivo.

- **Guia de configuração e uso (comece por aqui): [`GUIA.md`](GUIA.md)**
- Plano e fases: [`docs/projmap/PLANO.md`](../docs/projmap/PLANO.md)
- Estudo das referências: [`docs/projmap/BLUEPRINT.md`](../docs/projmap/BLUEPRINT.md)
- Decisões de engenharia: [`ARCHITECTURE.md`](ARCHITECTURE.md)

| Fase | Status |
|---|---|
| F0 Blueprint + plano | ✅ aprovado |
| **F1 Um projetor: quads manuais + vídeo/GIF** | ✅ entregue (este README) |
| F2 Mestre/nós em rede + sincronia | próxima |
| **F3a Detecção automática de superfícies (OpenCV)** | ✅ entregue — ver "Detectar superfícies" abaixo · SAM 2 e área projetada automática (F3b) pendentes |
| F4 Calibração Gray code + edge blending | — |
| F5 NDI + PJLink | — |
| **F6a Remote no celular (web/PWA)** | ✅ entregue — ver abaixo |
| **F6b App Android (APK)** | ✅ APK de debug — [`android/README.md`](android/README.md) |
| **F9 Prévia ao vivo no editor + camadas por superfície** | ✅ entregue — ver "Prévia e camadas" abaixo |
| **F8 Camada interativa (IA + sensores + TouchDesigner)** | ✅ MVP — [`interact/README.md`](interact/README.md) |

---

## Mestre (Windows ou Linux)

Requisitos: Python 3.11+ e, para compilar a UI uma vez, Node.js 20+. O mestre
roda **nativo**, sem Docker: na F2 ele precisa enxergar a rede local (mDNS), e
o Docker Desktop no Windows não repassa multicast.

```bash
# 1) Ambiente Python
python -m venv .venv-projmap
# Windows: .venv-projmap\Scripts\activate   ·   Linux/macOS: source .venv-projmap/bin/activate
pip install -r requirements-projmap-master.txt

# 2) UI (só uma vez, ou depois de atualizar o código)
cd projmap/ui && npm ci && npm run build && cd ../..

# 3) Rodar
python -m projmap.master --project shows/meu-show.projmap --display 1 --open
```

- `--display 1` abre a saída em tela cheia no 2º monitor, que é o projetor
  (`0` é o monitor principal).
- Sem projetor à mão, use `--windowed`: a saída abre numa janela de preview.
- A UI fica em http://localhost:8100. Por padrão o servidor escuta só nesta
  máquina.
- Na janela de saída: `F` alterna tela cheia e `Ctrl+Q` fecha. `Esc` não fecha
  de propósito, para um esbarrão no teclado não derrubar o show.

### Testar sem projetor (projeto de exemplo)

```bash
python -m projmap.tools.demo --project shows/demo.projmap
python -m projmap.master --project shows/demo.projmap --windowed --open
```

O exemplo traz uma "foto" sintética de parede com 2 caixas e uma coluna, e já
vem com 3 superfícies mapeadas: vídeo, GIF e cartela de teste.

### Fluxo de trabalho (na parede de verdade)

1. **Foto.** Com a câmera ou o celular no lugar do projetor, tire uma foto da
   parede e envie no passo 1 da UI. No celular, o botão abre a câmera.
2. **Área projetada.** Na barra do topo, clique em **Branco**. Veja onde a luz
   cai e, no passo 2, arraste os 4 cantos amarelos até essa área na foto.
   Clique em **Bordas da foto**: as quinas da foto são projetadas na parede e
   devem cair sobre as quinas reais. Se não caírem, ajuste os cantos amarelos.
3. **Superfícies.** Clique em **+ Nova** e arraste os cantos sobre a parede,
   coluna ou caixa. A lupa ajuda na precisão, e no celular funciona com o dedo.
4. **Ajuste fino olhando a parede.** Ligue **Contornos**, troque para a vista
   **Projetor** e use:
   - **Setas** para mover 1 px do projetor (**Shift** move 10 px);
   - **Tab** para trocar de canto.
5. **Conteúdo.** No painel da superfície escolha vídeo, GIF, imagem, cor ou
   cartela. Também há:
   - **ajuste**: esticar, preencher ou caber;
   - opacidade, borda suave, modo de mistura e camada.
6. **Salvar.** Não há botão: cada edição é gravada na hora em
   `shows/<nome>.projmap/project.json`, com escrita atômica. Para levar o
   projeto a outra máquina, use **Exportar .pmz** e depois:
   `python -m projmap.master --import show.pmz --project shows/copia.projmap`.

Dicas que vêm do estudo (BLUEPRINT §3):
- **Não use o keystone do projetor.** Corrija tudo no mapeamento.
- Não mexa no tripé entre a foto e o show.
- Use a resolução nativa do projetor (card "Projetor" na UI).

### Projeção interativa (fantasmas tímidos, vaga-lumes, cardume…)

No card **Interativo** da UI, descreva a cena em texto (ex.: *"5 fantasmas que
param quando eu olho e me perseguem quando viro de costas"*) e escolha a fonte
**Cena interativa** numa superfície. Sem sensor, a pessoa é simulada. Para
webcam, Kinect via TouchDesigner e visuais no TD, siga o
[guia da camada interativa](interact/README.md).

**Sem Kinect?** Use um celular Android na parede como sensor, ligado por USB:
```bash
python -m projmap.tools.fetch_models                     # uma vez: modelo do rosto (offline)
python -m projmap.master --project shows/meu-show.projmap --sensor phone --adb
```
A página `/sensor/` abre no celular; toque em **Iniciar sensor**. Passo a
passo em [interact/README.md](interact/README.md#celular-por-usbadb-phone--recomendado-sem-kinect).

### Detectar superfícies automaticamente

Depois de enviar a foto, use o card **Detectar superfícies**. O mestre analisa
a foto (OpenCV, em menos de 1 s, sem placa de vídeo) e sugere as regiões
lisas com arestas retas: paredes, portas, teto, colunas, painéis.

- As sugestões aparecem numeradas sobre a foto. As grandes e retangulares já
  vêm marcadas. Clique numa região (no editor ou na lista) para marcar ou
  desmarcar.
- **Criar N superfícies** cria todas de uma vez, já no lugar certo do projetor.
  Depois é só ajustar os cantos e escolher a mídia.
- **Sensibilidade:** à esquerda, poucas regiões grandes; à direita, mais regiões
  e menores.
- Algo na frente da superfície (um carrinho diante da porta, uma fita
  pendurada) não a parte em pedaços: o detector junta os pedaços e estende o
  quadrilátero por trás do objeto.
- Funciona melhor com superfícies lisas e boa luz. Textura forte, sombra dura e
  pouco contraste confundem; para isso virá o modo com IA (SAM 2).

### Galeria de mídias (pastas do PC e Google Drive) e sugestões

A galeria substitui as listas suspensas: miniaturas de tudo o que está no
projeto e nas suas **pastas** (`--library PASTA` ou o card *Biblioteca de
mídias*). Para o Google Drive, use o *Google Drive para computador* e aponte
para a pasta espelhada (ex.: `G:\Meu Drive\Projeção`). Escolher um arquivo da
pasta o importa para o projeto (por hash, sem duplicar).

**Sugestões:** para cada superfície, as mídias são ordenadas pelo formato
(proporção), pela resolução para o tamanho na parede e pelo tipo (vídeo em
superfícies grandes). **⭐ Sugerir mídias** propõe uma por superfície, evitando
repetir. Passo a passo no [GUIA](GUIA.md#4-escolher-as-mídias).

### Prévia e camadas (ver a mídia enquanto mapeia)

O editor mostra o conteúdo **dentro** de cada superfície, já em perspectiva:
vídeo tocando, GIF animado, imagem, cor ou cartela. Assim dá para mapear olhando
o resultado, nas vistas Foto e Projetor. Para mapear só pelos contornos,
desmarque **Prévia da mídia** na barra acima do editor.

Cada superfície tem um **fundo** (a fonte do card *Superfície*) e quantas
**camadas** quiser por cima (card *Camadas*):

- **+ Vídeo/foto/GIF** envia um arquivo e já cria a camada. **+ Do projeto…**
  reaproveita uma mídia enviada antes.
- Clique na camada para selecioná-la. No editor aparecem quadrados brancos:
  **arraste um canto** para redimensionar (mantém a proporção; **Shift** solta)
  e **arraste por dentro** para mover. Também dá para digitar X/Y/largura/altura
  em %.
- ▲▼ mudam a ordem (o topo da lista fica na frente). Há ainda visibilidade,
  opacidade, ajuste (esticar/caber/preencher), velocidade e os atalhos
  *Preencher superfície*, *Proporção da mídia* e *Centralizar*.
- A camada pode passar das bordas: o que sai fica recortado pela superfície.
- Os looks do remote guardam e restauram as camadas.

A prévia é aproximada no tempo (o vídeo do navegador não segue o relógio do
projetor). A posição e a deformação são as mesmas da saída.

### Controlar pelo celular (remote)

```bash
python -m projmap.master --project shows/meu-show.projmap --display 1 --host 0.0.0.0
```

O log mostra `http://<ip>:8100/remote/#t=<token>`, e o card **Remote no
celular** do editor mostra o mesmo link em QR. Com o celular na mesma rede
Wi-Fi, escaneie e pronto: blackout, dimmer, padrões de teste, contornos,
**looks** (salve a parede como cena e troque com um toque), fonte/opacidade/
visibilidade por superfície, foto da posição do projetor e envio de mídia.
No menu do navegador, **Adicionar à tela inicial** instala como app.

- Fora do mestre, nada é aceito sem o token (401). Ele muda a cada execução;
  use `--token <valor>` para fixar.
- **App Android:** o APK faz o mesmo e lembra o mestre. Build em
  [`android/README.md`](android/README.md).
- O QR usa `segno` (já em `requirements-projmap-master.txt`). Sem ele, copie o
  link do log.

### Medir desempenho

```bash
python -m projmap.tools.bench --surfaces 4 --seconds 10                         # 4 vídeos 720p → 1080p30
python -m projmap.tools.bench --surfaces 4 --seconds 10 --video-size 1920x1080
```

A janela de saída também registra no log, a cada 5 s, o fps e o pior frame.

---

## Nó (Linux / Raspberry Pi OS / mini PC)

Na F1 o nó pode tocar sozinho um projeto salvo, sem mestre. Ele recarrega
quando o `project.json` muda. Isso já atende uma instalação fixa. Na F2 o mesmo
processo passa a receber configuração e mídia do mestre pela rede.

```bash
python -m venv ~/projmap-venv && source ~/projmap-venv/bin/activate
pip install -r requirements-projmap-node.txt
python -m projmap.node --project /caminho/meu-show.projmap --display 0
```

Para iniciar com o sistema, crie `/etc/systemd/system/projmap-node.service`:

```ini
[Unit]
Description=ProjMap nó
After=graphical.target

[Service]
User=pi
Environment=DISPLAY=:0
ExecStart=/home/pi/projmap-venv/bin/python -m projmap.node --project /home/pi/shows/meu-show.projmap
WorkingDirectory=/home/pi/neocoisas
Restart=always

[Install]
WantedBy=graphical.target
```

> **Raspberry Pi 5:** dois pontos ainda não foram medidos no hardware
> (BLUEPRINT U1/U2) e serão validados no início da F2.
> - **GL:** o Pi 5 expõe OpenGL ES 3.1. Os shaders já são GLSL ES 3.00
>   compatíveis, mas o contexto moderngl+pyglet nele precisa de teste.
> - **Vídeo:** o Pi 5 não decodifica H.264 por hardware. Prefira poucos
>   vídeos simultâneos, em até 1080p30.

---

## Desenvolvimento

```bash
pip install -r requirements-dev.txt -r requirements-projmap-master.txt
xvfb-run -a pytest -q tests/projmap   # sem xvfb os testes de GPU são pulados
cd projmap/ui && npm run dev          # UI com hot reload em :3100
#   em outro terminal: python -m projmap.master --project shows/dev.projmap --windowed
#   e rode a UI com NEXT_PUBLIC_PROJMAP_API=http://localhost:8100
```

Estrutura:

```
projmap/
  core/      geometry (homografia), project (esquema), store (disco/.pmz), state (revisão)
  content/   fontes: imagem, GIF, vídeo (PyAV), cor, cartela; padrões de teste/alinhamento
  mapping/   warp (uniforms do shader + referência em CPU)
  node/      renderer moderngl + shaders GLSL, janela pyglet, CLI do nó
  master/    API FastAPI + CLI do mestre
  ui/        editor Next.js (export estático servido pelo mestre)
  interact/  camada interativa: sensores, comportamentos, NLP texto→cena, OSC p/ TouchDesigner
  tools/     demo (projeto de exemplo), bench (desempenho)
```
