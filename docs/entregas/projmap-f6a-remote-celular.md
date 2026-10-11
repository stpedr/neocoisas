# ProjMap F6a — Remote no celular (web/PWA)

## Resumo
Controle da projeção pelo celular: rota `/remote` pareada por QR + token, com
blackout, dimmer, padrões, looks (cues), fonte/opacidade/visibilidade por
superfície, foto da posição do projetor e envio de mídia. Instalável como PWA.

## Motivação
Durante a montagem e o show, quem opera fica perto da parede, não do PC. A F6
do plano (`docs/projmap/PLANO.md`) pede um remote no celular. Esta entrega
cobre a parte web. O app Android (Capacitor) fica para a F6b.

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/master/auth.py` | Novo: middleware ASGI com token de pareamento (HTTP + WebSocket), loopback dispensa |
| `projmap/master/remote.py` | Novo: `PATCH /api/surfaces/{id}`, `POST/DELETE /api/looks`, `POST /api/looks/{id}/recall`, `GET /api/remote/pair` (URL + token + QR SVG) |
| `projmap/master/app.py` | Liga o middleware e o router; `create_app(token=, host=, port=)` |
| `projmap/master/__main__.py` | `--token`; gera um token quando `--host` não é loopback e mostra a URL do remote no log |
| `projmap/core/project.py` | `Look`/`SurfaceLook` e `Project.looks` (campo opcional, sem subir versão do esquema) |
| `projmap/ui/app/remote/page.tsx` | Novo: UI mobile (abas Show / Superfícies / Foto-Mídia, tela de pareamento) |
| `projmap/ui/app/components/RemoteCard.tsx` | Novo: card com QR no editor |
| `projmap/ui/app/lib/api.ts` · `types.ts` | Token em todo pedido (`X-ProjMap-Token`, `?token=` p/ img/WS), métodos do remote, `Look` |
| `projmap/ui/app/page.tsx` | Editor recarrega quando a revisão do mestre avança sem ele |
| `projmap/ui/app/sensor/page.tsx` | WebSocket do sensor manda o token |
| `projmap/ui/public/manifest.webmanifest` · `layout.tsx` | PWA (abre direto em `/remote/`) |
| `projmap/ui/app/globals.css` | Estilos do remote (alvos de toque ≥ 44 px, blackout grande) |
| `tests/projmap/test_remote.py` | 16 testes: token, pareamento, comandos, looks |
| `requirements-projmap-master.txt` | `segno` (QR) |
| `projmap/README.md` · `ARCHITECTURE.md` · `board/seed.py` | Docs; card F6a em done e F6b no backlog |

## Como funciona
1. `python -m projmap.master ... --host 0.0.0.0` gera um token e loga
   `http://<ip-lan>:8100/remote/#t=<token>`. O card **Remote no celular** do
   editor mostra o mesmo link em QR. `GET /api/remote/pair` só responde na
   própria máquina.
2. O celular abre a URL. A página lê `#t=`, guarda o token no `localStorage` e
   limpa o hash. Todo pedido leva `X-ProjMap-Token`. Para `<img>`/WebSocket, o
   token vai em `?token=`.
3. O middleware recusa com 401 (ou fecha o WS com 4401) qualquer `/api/*` ou
   `/media/*` sem token vindo de fora da máquina. Os arquivos estáticos da UI
   são públicos.
4. Os comandos são pequenos (PATCH de uma superfície, recall de look) para
   conviver com o editor. O editor consulta `/api/health` a cada 1,5 s e
   recarrega se a revisão avançou sem ele, para que o próximo `PUT` não apague
   a mudança feita no celular.
5. Um look guarda `visible`/`opacity`/`source` de cada superfície, sem
   geometria. O recall ignora superfícies ou mídias apagadas e devolve
   `skipped`.

## Como validar
```bash
pytest -q tests/projmap                       # 104 passam (16 novos)
cd projmap/ui && npm run build                # gera /remote
python -m projmap.tools.demo --project shows/demo.projmap
python -m projmap.master --project shows/demo.projmap --windowed --host 0.0.0.0
# no celular (mesma Wi-Fi): escaneie o QR do card "Remote no celular"
curl -i http://<ip>:8100/api/project          # 401 sem token
```
Smoke test feito pela LAN (192.168.x): sem token → 401; com token → 200;
`/remote/` e manifesto → 200; `PATCH` de superfície → 200; `/api/remote/pair`
de fora → 403.

## Critério de aceite
- [x] Sem token → nenhum comando aceito (teste `test_sem_token_nenhum_comando_aceito`)
- [x] Remote responsivo: blackout, dimmer, padrões, contornos, looks, fonte/opacidade/visibilidade
- [x] Foto da posição do projetor e upload de mídia pelo celular
- [x] QR de pareamento no editor; token só visível no mestre
- [x] Editor não sobrescreve mudanças feitas pelo remote
- [x] `pytest -q` verde e `npm run build` ok
- [ ] Testado em Android/iOS reais pelo navegador
- [ ] APK de debug (F6b)

## Pendências / próximos
- **F6b:** app Android (Capacitor) com descoberta mDNS e câmera nativa.
- Energia dos projetores via PJLink (depende da F5) e status dos nós (fps,
  deriva, temperatura; depende da F2).
- Play/pause/seek de vídeo por superfície. O renderer ainda não expõe isso.
- O sync do editor por polling tem uma janela pequena de corrida (edição no
  editor no mesmo ~1,5 s de um comando do celular). Na F2 isso migra para
  eventos por WebSocket.
