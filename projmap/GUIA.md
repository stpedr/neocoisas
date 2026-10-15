# ProjMap: guia de configuração e uso

Este guia leva do zero até a projeção rodando, com o controle pelo celular.
Detalhes técnicos estão no [README](README.md) e em [ARCHITECTURE](ARCHITECTURE.md).

**O que você precisa**
- Um PC com Windows ou Linux. É o **mestre**: roda o programa e liga no projetor
  como segundo monitor.
- Python 3.11 ou mais novo e Node.js 20 ou mais novo (o Node só para compilar
  a interface).
- Um projetor (para testar, dá para usar uma janela de prévia).
- Opcional: um celular Android ou iPhone na mesma rede Wi-Fi, e uma conta do
  Google Drive se as suas mídias estiverem lá (seção 4.1).

---

## 1. Instalar (uma vez)

No terminal, dentro da pasta do repositório:

```bash
python -m venv .venv-projmap
# Windows:
.venv-projmap\Scripts\activate
# Linux/macOS:
source .venv-projmap/bin/activate

pip install -r requirements-projmap-master.txt

cd projmap/ui
npm ci
npm run build
cd ../..
```

Repita o `npm run build` sempre que atualizar o código.

**Atalho no Menu Iniciar (recomendado):** com o ambiente ativado, rode uma vez:

```bash
python -m projmap.desktop.install            # cria "ProjMap" no Menu Iniciar
python -m projmap.desktop.install --desktop  # + atalho na Área de Trabalho
python -m projmap.desktop.install --uninstall  # remove
```

## 2. Abrir o programa

**Pelo Menu Iniciar:** procure **ProjMap**. Abre um lançador:
1. Em **Show**, escolha um show ou **＋ Novo show…**. Os shows ficam em
   `Documentos\ProjMap`; troque em **Pasta…**.
2. Em **Onde sai a imagem**, escolha:
   - **Projetor:** tela cheia no monitor indicado; o projetor costuma ser o 1.
   - **Janela de teste:** quando não há projetor.
   - **Só o editor:** sem saída.
3. **Interação** é opcional. Marque **Quero interação** só se o show tiver
   cenas que reagem ao público (como os fantasmas). Aí aparecem, na mesma
   janela, as opções de sensor:
   - **Celular ligado no cabo USB (ADB):** a câmera do celular vira o sensor.
     Ative a *Depuração USB* no celular e aceite o aviso; o ProjMap abre a
     página do sensor nele sozinho.
   - **Webcam deste computador** ou **Sem sensor (simulação)**, para testar.
   Desmarcado, o editor não mostra nada de interação.
4. Em **Celular**, marque **Controlar o show pelo celular** para usar o
   celular como controle remoto na mesma rede Wi-Fi.
5. Clique em **Abrir**. O editor abre no navegador, e **Copiar link do
   celular** copia o endereço com o token.

A janela do lançador pode ser redimensionada: o conteúdo rola e o botão
**Abrir** fica sempre à vista. Fechar o lançador encerra o show. As escolhas
ficam salvas para a próxima vez.

**Pelo terminal** (o que o lançador faz por baixo):

```bash
python -m projmap.master --project shows/meu-show.projmap --display 1 --host 0.0.0.0 --open
```

| Opção | Para que serve |
|---|---|
| `--project` | Pasta do show. É criada se não existir. Tudo é salvo sozinho nela. |
| `--display 1` | Abre a saída em tela cheia no 2º monitor (o projetor). `0` é o monitor principal. |
| `--windowed` | Em vez de tela cheia, abre a saída numa janela (para testar sem projetor). |
| `--host 0.0.0.0` | Libera o acesso pelo celular na mesma rede. Sem isso, só o próprio PC acessa. |
| `--library PASTA` | Pasta de mídias para a galeria (pode repetir). Também dá para configurar pela interface. |
| `--open` | Abre o editor no navegador. |
| `--no-interact` | Desliga a camada interativa (o lançador usa quando **Quero interação** está desmarcado). |
| `--sensor phone --adb` | Interação com o celular como sensor, ligado pelo cabo USB. |

O editor fica em **http://localhost:8100**. Na janela de saída, `F` alterna
tela cheia e `Ctrl+Q` fecha. O `Esc` não fecha, de propósito, para um esbarrão
não derrubar o show.

### Como o editor está organizado

- **Barra de cima:** padrões de alinhamento, **⇋ Retroprojeção**, **⇅ Teto**,
  contornos, intensidade, Blackout e Exportar.
- **Atalhos acima da foto:** **🖼 Mídias** (biblioteca: projeto, pastas do PC
  e Google Drive), **📱 Celular** (QR do controle remoto e status do celular
  sensor), **✨ Criar com IA** (só aparece com a interação ligada; a IA só é
  usada quando você clica) e **◧ Painel** (esconde o painel e deixa a foto em
  tela cheia).
- **Painel lateral em gavetas:** *Foto e área projetada*, *Superfícies*,
  *Imagem do projetor*, *Interação* (só com a interação ligada) e *Projetor*.
  Clique no título para abrir ou fechar; o editor lembra quais deixou abertas.
- **Largura do painel:** arraste a divisória entre a foto e o painel. Duplo
  clique nela volta à largura automática, que acompanha o tamanho da janela.

## 3. Mapear a parede

1. **Foto.** Fique no lugar do projetor e tire uma foto da parede: gaveta
   *Foto e área projetada*. No celular, o botão abre a câmera.
2. **Detectar superfícies (automático).** Na mesma gaveta, em *Detectar superfícies*,
   clique em **Detectar na foto**. O programa sugere paredes, portas, teto,
   colunas e painéis, já numerados sobre a foto.
   - As regiões grandes vêm marcadas. Clique numa região para marcar ou
     desmarcar.
   - **Criar N superfícies** cria todas de uma vez.
   - A **sensibilidade** vai de poucas regiões grandes a muitas e detalhadas.
3. **Área projetada.** Ligue **Branco** na barra do topo, veja onde a luz cai
   e, em **Marcar área projetada**, arraste os 4 cantos amarelos até essa
   área na foto. Confira com **Bordas da foto**: as quinas da foto devem cair
   sobre as quinas reais da parede.
4. **Ajuste fino.** Arraste os cantos das superfícies (a lupa ajuda; no
   celular, com o dedo). Na vista **Projetor**, as setas movem 1 px (com
   Shift, 10 px) e o Tab troca de canto. Também dá para criar superfícies à mão
   com **+ Nova**.
5. **Escalar e girar.** A superfície selecionada ganha duas alças acima da
   borda de cima: a quadrada (**↕**) escala (puxe para cima para aumentar,
   para baixo para diminuir) e a redonda (**⟳**) gira em torno do centro
   (com Shift, de 15 em 15°).
6. **Excluir.** Com a superfície selecionada, aperte **Delete**. Se foi sem
   querer, clique em **Desfazer** no aviso que aparece embaixo. Com uma camada
   selecionada, o Delete exclui só a camada.

Dica: não use o keystone (correção de trapézio) do projetor nem mexa no tripé
depois da foto.

## 4. Escolher as mídias

### 4.1 Galeria e Google Drive

Abra pelo atalho **🖼 Mídias** (ou **Escolher na galeria** de uma superfície).
A galeria mostra miniaturas de tudo o que você pode usar:
- **No projeto:** o que já foi enviado.
- **Minhas pastas:** pastas do seu PC (botão **⚙ Pastas** para configurar).
- **☁ Google Drive:** a sua pasta do Drive, direto pela internet.

Com uma superfície selecionada, a mídia escolhida já vai para ela. Sem
seleção, entra no projeto para usar depois.

**Google Drive direto (recomendado).** Você navega pelas pastas do Drive (por
exemplo `Projeção/Natal`, `Projeção/GIFs`) e o arquivo só é baixado quando é
escolhido. Configuração, uma vez só, no PC do mestre:
1. Em <https://console.cloud.google.com>, crie um projeto, ative a **Google
   Drive API** e crie uma credencial **ID do cliente OAuth** do tipo **App para
   computador**. (Na tela de consentimento, adicione o seu e-mail como usuário
   de teste.)
2. No arquivo `.env` da pasta do ProjMap (copie de `.env.example`), preencha:
   ```
   PROJMAP_GDRIVE_CLIENT_ID=...
   PROJMAP_GDRIVE_CLIENT_SECRET=...
   PROJMAP_GDRIVE_FOLDER=https://drive.google.com/drive/folders/<id da pasta>
   ```
   A pasta é opcional: sem ela, aparece o *Meu Drive* inteiro. Também dá para
   colar o link da pasta na própria galeria (**Trocar pasta**).
3. Reabra o ProjMap. Na galeria, aba **☁ Google Drive**, clique em **Conectar
   Google Drive** e autorize. O acesso é só de leitura e fica salvo neste PC
   (`~/.projmap/gdrive-token.json`); **Desconectar** apaga.

Sem login: use `PROJMAP_GDRIVE_API_KEY` (chave de API do mesmo projeto) e
compartilhe a pasta como "qualquer pessoa com o link". É mais simples, mas a
pasta fica pública para quem tiver o link.

As chaves ficam **só no `.env`**, que não vai para o git. Não cole chaves no
chat nem em prints.

**Alternativa sem configurar nada:** instale o **Google Drive para
computador**. O Drive aparece como uma unidade (ex.: `G:\Meu Drive`). Na
galeria, aba **Minhas pastas** → **⚙ Pastas**, cole o caminho (ex.:
`G:\Meu Drive\Projeção`) e clique em **Adicionar**. Funciona igual com
OneDrive, Dropbox, pen drive ou HD externo. Só o arquivo que você escolher é
copiado para o projeto.

### 4.2 Pôr mídia numa superfície

- Selecione a superfície (gaveta *Superfícies*) e toque em **Escolher na
  galeria**. No topo aparecem as **⭐ Sugeridas** para aquela superfície, com o
  motivo (formato igual, resolução etc.).
- Ou use **⭐ Sugerir mídias para todas** na gaveta *Superfícies*: o programa propõe uma
  mídia para cada superfície, sem repetir quando possível. Desmarque o que não
  quiser e clique em **Aplicar**.

O editor mostra a mídia **dentro** de cada superfície, já em perspectiva e
animada. Para mapear só pelos contornos, desmarque **Prévia da mídia**.

### 4.3 Várias mídias na mesma superfície (camadas)

No card **Camadas**, use **+ Da galeria** ou **+ Vídeo/foto/GIF**.
- Clique na camada para selecioná-la. No editor aparecem quadrados brancos:
  arraste um canto para **redimensionar** (mantém a proporção; Shift solta) e
  arraste por dentro para **mover**.
- ▲▼ mudam a ordem (o topo da lista fica na frente). Também há opacidade,
  ajuste, velocidade e os atalhos *Preencher superfície*, *Proporção da mídia*
  e *Centralizar*.

## 5. Controlar pelo celular

O celular precisa estar na **mesma rede Wi-Fi** do PC, e o mestre aberto com
**Controlar o show pelo celular** marcado no lançador (ou `--host 0.0.0.0`).

**Pelo navegador:** no editor do PC, clique no atalho **📱 Celular** e
escaneie o QR com a câmera do celular. O celular abre o controle do show:
- Blackout, dimmer (brilho), padrões de teste e contornos;
- Looks;
- Mídia, opacidade e visibilidade de cada superfície, pela galeria;
- Foto e envio de mídia.

No menu do navegador, **Adicionar à tela inicial** instala como app.

**Pelo app Android (APK):** instale o `app-debug.apk` (ver
[`android/README.md`](android/README.md)), abra, toque em **Escanear QR** ou
digite o IP e o token que o mestre mostra no terminal. Nas próximas vezes ele
reconecta sozinho.

**Se o celular não conecta pelo Wi-Fi** (no Windows é quase sempre o
firewall), abra o PowerShell **como administrador** e rode:

```powershell
# se for a rede da sua casa/estúdio, marque-a como Privada
Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
# libere a porta do ProjMap
New-NetFirewallRule -DisplayName "ProjMap 8100" -Direction Inbound -Protocol TCP -LocalPort 8100 -Action Allow -Profile Private
```

**Alternativa pelo cabo USB (Android):** com a depuração USB ligada no
celular, rode `adb reverse tcp:8100 tcp:8100` e abra
`http://localhost:8100/remote/` no celular. Pelo cabo não precisa de token nem
de mexer no firewall.

**Segurança:** pelo Wi-Fi, nada é aceito sem o **token**. Ele muda a cada vez
que o mestre abre; use `--token MEUSEGREDO` para fixar um.

## 6. Durante o show

| Botão | O que faz | Quando usar |
|---|---|---|
| **Blackout** | Apaga o projetor na hora (tela preta) **sem perder nada**: mapeamento, mídias e ajustes continuam lá. Clique de novo para voltar. | Entre cenas, para ajustar algo na parede sem a luz no rosto, numa emergência ou para "abrir" o show com efeito. |
| **Intensidade** | Dimmer geral do projetor. | Fade manual, ou baixar o brilho num ambiente escuro. |
| **Branco / Grade / Bordas da foto** | Padrões de alinhamento em tela cheia. | Só na montagem. Volte para **Conteúdo** para o show. |
| **Contornos** | Desenha as bordas das superfícies na parede. | Conferir o encaixe. |
| **Looks** (no celular) | Salva a combinação atual (mídia e visibilidade de cada superfície) e troca tudo de uma vez com um toque. | Cenas do show: "Abertura", "Natal", "Final". |

## 6.1 Melhorar a imagem projetada

No editor, gaveta **Imagem do projetor** (também no celular, aba *Show* →
*Imagem*):

| Predefinição | Quando usar |
|---|---|
| **Ambiente claro** | Luz acesa, fim de tarde, vitrine iluminada: realça os médios e as cores. |
| **Ambiente escuro** | Sala ou fachada à noite: pretos mais pretos, menos ofuscante. |
| **Cores vivas** | Festas e conteúdo colorido. |
| **Parede amarelada** | Parede creme, bege ou madeira: esfria a imagem para as cores ficarem certas. |
| **Parede azulada** | Parede cinza-fria ou azulada: aquece a imagem. |

Em **Ajuste fino** há brilho, médios (gama), contraste, saturação e
temperatura. Um duplo clique num controle volta ao padrão.

- **Para clarear sem estourar o branco, use Médios (gama) acima de 1.** O
  Brilho acima de 100% clareia tudo, mas os brancos "estouram" (perdem
  detalhe).
- **Retroprojeção (espelhar):** quando o projetor fica **atrás** de uma tela ou
  tecido translúcido (voile, lona de retroprojeção). Sem espelhar, o público vê
  tudo invertido.
- **Projetor no teto (inverter):** quando o projetor está preso de cabeça para
  baixo. Se o próprio projetor já tiver o modo "teto" ligado, deixe esta opção
  desligada (senão inverte duas vezes).
- **Imagem por superfície:** selecione a superfície → **Imagem desta
  superfície**. Equilibra uma parede mais escura ou colorida que as outras, e
  soma-se ao ajuste do projetor. No celular: aba *Superfícies* → **Imagem
  desta superfície**.
- **Meus presets:** deixe brilho, contraste etc. do jeito que gosta e clique em
  **＋ Salvar ajuste atual como preset** (ex.: "Parede da igreja"). O preset
  aparece com ⭐ em *Meus presets*, no editor e no celular, e um clique aplica
  na superfície selecionada (ou no projetor inteiro, na gaveta *Imagem do
  projetor*). Os presets ficam neste PC e valem para todos os shows. O × apaga.
- **Borda suave:** esmaece as bordas da superfície até o preto, para a imagem
  "fundir" com a parede em vez de terminar num corte seco. 0% = desligada; 10%
  a 20% já é bem visível. Aparece na prévia do editor e na parede.
- Os padrões de alinhamento (Branco, Grade, Bordas) saem sempre puros, sem
  ajuste.

**O que o software não faz (e como resolver no mundo real):**
- **Brilho real** vem do projetor (lúmens). O ajuste de software só redistribui
  a luz que o projetor tem. Para ganhar brilho de verdade:
  - desligue o modo *Eco* do projetor e use o modo *Brilhante/Dinâmico*;
  - aproxime o projetor da parede (imagem menor = mais luz por m²);
  - apague ou desvie as luzes que batem na parede;
  - prefira superfícies claras e foscas.
- **Foco** é ajustado na lente do projetor. Use o padrão **Grade** e foque
  pelo centro.
- **Não use o keystone** (correção de trapézio) do projetor: ele perde
  resolução. O mapeamento do ProjMap já corrige a perspectiva.

## 7. Salvar, fazer backup e levar para outro PC

- **Salvar:** não há botão. Cada mudança é gravada na hora na pasta do projeto
  (`shows/<nome>.projmap`).
- **Exportar .pmz:** baixa o projeto inteiro num **único arquivo**: o
  mapeamento, as mídias usadas e a foto. Serve de backup ou para abrir o mesmo
  show em outro computador. Para abrir:
  ```bash
  python -m projmap.master --import show.pmz --project shows/copia.projmap
  ```

## 8. Problemas comuns

| Sintoma | Solução |
|---|---|
| "UI não compilada" | Rode `cd projmap/ui && npm ci && npm run build`. |
| O build da UI falha com "memory allocation failed" | Pouca memória virtual: feche programas pesados (emulador Android, Gradle: `gradlew --stop`) e rode de novo. |
| O celular não abre o endereço | Mesma rede Wi-Fi? Mestre com `--host 0.0.0.0`? Firewall (seção 5)? Ou use o cabo USB. |
| O celular abre mas diz "Parear com o mestre" | O token mudou (o mestre foi reiniciado): escaneie o QR de novo. |
| A aba Google Drive pede configuração | Preencha `PROJMAP_GDRIVE_CLIENT_ID`/`SECRET` no `.env` (seção 4.1) e reabra o ProjMap. |
| "Google respondeu 403/404" no Drive | No modo chave de API, a pasta precisa estar compartilhada como "qualquer pessoa com o link". No modo OAuth, a conta conectada precisa ter acesso à pasta. |
| A galeria não mostra minhas pastas | Configure em **🖼 Mídias** → **Minhas pastas** → **⚙ Pastas** (no PC) e clique em **Reler pastas**. A pasta do Drive precisa estar sincronizada ("disponível offline" ajuda com vídeos grandes). |
| A detecção errou ou faltou uma superfície | Mude a sensibilidade e detecte de novo, ou crie com **+ Nova** e ajuste os cantos. Funciona melhor com superfícies lisas e boa luz. |
| A mídia aparece magenta na parede | Arquivo corrompido ou formato não suportado. Prefira MP4 (H.264), PNG/JPG e GIF. |
