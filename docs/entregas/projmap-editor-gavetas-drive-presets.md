# ProjMap — editor em gavetas, Google Drive direto, presets de imagem, escalar/girar

## Resumo

Rodada de ajustes pedida depois de usar o ProjMap: o editor virou um painel de
**gavetas** com **atalhos** (Mídias, Celular, Criar com IA) e largura ajustável;
a **interação** e o **celular** passaram a ser opcionais no lançador; a galeria
navega o **Google Drive direto** (API oficial); dá para salvar **presets de
imagem** e aplicá-los numa superfície; **Delete** exclui (com Desfazer); as
superfícies ganharam **alças de escalar e girar**; e a **borda suave** passou a
aparecer na prévia do editor.

## Motivação

Pedidos do operador ao testar:

- "Não é responsivo": o painel lateral ficava preso em 340 px e o lançador não
  se adaptava ao tamanho da janela (o botão Abrir sumia em janelas baixas).
- Interação e celular apareciam sempre; devem aparecer só quando pedidos, na
  mesma janela.
- A galeria deveria mostrar a pasta do Drive (um Drive só, com subpastas de
  GIFs etc.) direto no app.
- "Borda suave" parecia não fazer nada: o shader do projetor aplicava, mas a
  prévia do editor ignorava o efeito.
- Presets próprios de brilho/contraste aplicáveis a uma superfície inteira.
- Tudo em gavetas/widgets; retroprojeção/teto à mão; IA só por botão; botões
  mais claros para o remote e para a biblioteca.
- Delete deve apagar o elemento; alças estilo MindManager para escalar e girar.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `projmap/gdrive.py` (novo) | Cliente da Drive API v3 (só leitura): listar pasta (com atalhos de pasta), miniaturas (thumbnailLink → JPEG, cache em disco), download com limite; auth **OAuth de app instalado** (loopback 127.0.0.1 + PKCE, guarda só o refresh token com 0600) ou **chave de API** (pasta pública); factory `get_drive` + `drive_config` lendo o `.env`. |
| `projmap/master/gdrive_api.py` (novo) | Rotas `/api/gdrive/{status,folder,connect,callback,disconnect,list}`, `/api/gdrive/{id}/thumb`, `/api/gdrive/{id}/import`; rotas de presets `/api/color-presets`. Configurar/conectar só no próprio mestre; navegação restrita à raiz e pastas já listadas; importação só de arquivos vistos; reimportar não baixa de novo. |
| `projmap/color_presets.py` (novo) | Presets do operador em `~/.projmap/color-presets.json` (mesmo nome atualiza; escrita atômica; limite 100). |
| `projmap/library.py` | `library.json` passa a guardar também a pasta do Drive (sem apagar as outras chaves). |
| `projmap/master/app.py`, `__main__.py` | Liga o router novo (`config_dir`, `drive_config`, `drive_http` injetáveis para testes); o mestre lê o `.env` da raiz (python-dotenv, opcional). |
| `projmap/master/remote.py` | `PATCH /api/surfaces/{id}` aceita `color` (aplicar preset numa superfície pelo celular). |
| `projmap/desktop/core.py`, `__main__.py` | Lançador: seção **Interação** opcional (sensor celular USB/ADB, webcam ou simulação; desmarcado = `--no-interact`) e **Celular** opcional, abrindo opções na mesma janela; corpo com rolagem, rodapé fixo com Abrir/log e textos que quebram na largura da janela. |
| `projmap/ui/app/page.tsx` | Layout novo: gavetas (Foto e área, Superfícies, Imagem do projetor, Interação, Projetor), atalhos 🖼 Mídias / 📱 Celular / ✨ Criar com IA / ◧ Painel, divisória arrastável (lembrada; duplo clique = automática), ⇋ Retroprojeção e ⇅ Teto na barra de cima, Delete com Desfazer (superfície ou camada), biblioteca como widget (aplica na superfície selecionada). |
| `projmap/ui/app/components/Drawer.tsx` (novo) | Gaveta com estado salvo e `openDrawer(id)`. |
| `projmap/ui/app/components/DriveBrowser.tsx` (novo) | Aba ☁ Google Drive da galeria: conectar, trocar pasta, migalhas, pastas, cartões com miniatura e importação. |
| `projmap/ui/app/components/ColorPresets.tsx` (novo) | Presets prontos + "Meus presets" (salvar/aplicar/apagar), usados no editor e no celular. |
| `projmap/ui/app/components/AiDialog.tsx` (novo) | "Criar cena com IA": o LLM só é chamado por esse botão. |
| `projmap/ui/app/components/PhoneDialog.tsx` (era RemoteCard) | Widget Celular: QR do remote e status do celular-sensor. |
| `projmap/ui/app/components/Editor.tsx` | Alças ↕ (escala) e ⟳ (giro, Shift = 15°) acima da borda de cima; cursor nas alças; borda suave na prévia (canvas auxiliar + rampas smoothstep por borda). |
| `SurfacePanel`, `ImageCard`, `InteractPanel`, `MediaGallery`, `LibraryCard`, `remote/page.tsx` | Adaptados às gavetas; presets por superfície e do projetor; teto também no celular; gerenciador de pastas dentro da galeria; Esc fecha diálogos. |
| `projmap/ui/app/globals.css` | Painel fluido `clamp(300px, 27vw, 480px)`, divisória, gavetas, atalhos, diálogos, chips de preset, Drive. |
| `tests/projmap/test_gdrive.py` (novo), `test_desktop.py` | Drive com `httpx.MockTransport` (navegação, segurança, miniatura, importação sem rebaixar, OAuth completo com PKCE/token 0600/Bearer/desconectar), presets via API e via remote, comando do lançador com/sem interação. |
| `requirements-projmap-master.txt`, `.env.example` | `httpx`, `python-dotenv`; variáveis `PROJMAP_GDRIVE_*`. |
| `projmap/GUIA.md` | Lançador, organização do editor, escalar/girar/Delete, Google Drive passo a passo, presets, borda suave, problemas comuns. |
| `board/seed.py` | Card da entrega em `done`. |

## Como funciona

- **Drive:** o mestre fala com a API oficial (`drive/v3/files`). No modo OAuth,
  "Conectar Google Drive" redireciona ao consentimento do Google com
  `redirect_uri=http://127.0.0.1:<porta>/api/gdrive/callback`, PKCE S256 e
  escopo `drive.readonly`; o callback troca o código e guarda só o refresh
  token. Listagens alimentam um conjunto de pastas/arquivos "vistos": o cliente
  nunca manda caminhos, só ids opacos já listados. Importar baixa para
  `cache/downloads/` do show, `store.add_media` copia por hash e o temporário é
  apagado.
- **Presets:** ficam na máquina (não no show) e são só `ColorAdjust` com nome;
  aplicar = gravar `surface.color` (editor: PUT do projeto; celular: PATCH da
  superfície) ou `output.color`.
- **Escalar/girar:** transformação em torno do centroide no espaço da vista
  (foto ou projetor) e volta ao projetor pela homografia, validada como
  qualquer arraste de canto (quad cruzado é recusado).
- **Borda suave na prévia:** o conteúdo da superfície é pintado num canvas
  auxiliar e multiplicado (`destination-in`) por 4 rampas smoothstep, uma por
  borda, com largura = feather × distância à borda oposta (mesma conta do
  shader, aproximada em tela).

## Como validar

```bash
xvfb-run -a pytest -q                 # 418 passed, 1 skipped
cd projmap/ui && npm run build         # build estático OK
```

Ao vivo (feito nesta entrega, com Chromium e o show de exemplo):

```bash
python -m projmap.tools.demo --project shows/demo.projmap
python -m projmap.master --project shows/demo.projmap --windowed --open
```

- Redimensionar a janela: painel 300→480 px conforme a largura; divisória
  arrastável e lembrada; ◧ Painel deixa a foto em tela cheia; no celular
  (390 px) sem rolagem lateral.
- Selecionar uma superfície → ↕ para cima aumenta (530→772 px) e para baixo
  volta; ⟳ gira (−2,8° → 27,2°); Delete exclui e Desfazer devolve.
- Borda suave 20%: visível na prévia do editor e na janela de saída.
- Galeria → ☁ Google Drive (validado com Drive simulado): pastas, migalhas,
  miniatura, importação aplicada na superfície selecionada.
- Lançador (Linux/Xvfb): Interação/Celular abrem as opções na mesma janela; em
  760×560 o conteúdo rola e o Abrir continua visível.

Drive real: preencha `PROJMAP_GDRIVE_CLIENT_ID/SECRET` no `.env`, abra a
galeria → ☁ Google Drive → Conectar (passo a passo no GUIA, seção 4.1).

## Critério de aceite

- [x] Editor acompanha o tamanho da janela (painel fluido + divisória + esconder painel).
- [x] Lançador redimensionável; Interação e Celular opcionais, opções na mesma janela.
- [x] Interação some do editor quando desligada; IA só por botão.
- [x] Galeria navega e importa do Google Drive (API oficial, credenciais só no `.env`).
- [x] Borda suave visível na prévia do editor (e na saída, como antes).
- [x] Presets de imagem do operador: salvar, aplicar numa superfície/projetor, apagar; também no celular.
- [x] Gavetas e atalhos (Mídias, Celular, Criar com IA, Painel); retroprojeção/teto na barra de cima.
- [x] Delete exclui a superfície (ou a camada) com Desfazer.
- [x] Alças de escalar e girar no topo da superfície selecionada.
- [x] `pytest -q` verde e `npm run build` OK.

## Pendências / próximos

- Testar o OAuth com uma conta Google real (aqui o Drive foi simulado).
- Miniaturas de vídeo do Drive dependem do `thumbnailLink` do Google; sem ele
  aparece um ícone.
- Sugestões (⭐) ainda não consideram arquivos do Drive (só projeto e pastas do PC).
- Girar/escalar camadas (hoje só superfícies; camadas têm cantos/mover).
- Lançador testado no Linux (Xvfb); conferir no Windows com DPI alto.
