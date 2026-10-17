# ProjMap — Transmissão RTSP da camada interativa

## Resumo
O ProjMap agora **publica num servidor RTSP** o que a camada interativa está
mostrando (a cena ou o efeito do visual_frames), para assistir de outra
máquina. A URL — que carrega senha — fica só no `.env`.

## Motivação
"Tô recebendo um vídeo nesse endereço e quero que esse endereço seja o endereço
pra transmissão dos vídeos de interação."

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/interact/stream.py` | **Novo**: `RtspPublisher` (ffmpeg → H.264 → RTSP), leitor de `.env` sem dependência, `esconder_senha()` e `publisher_from_env()` |
| `projmap/interact/runtime.py` | Campo `publisher`, encerrado junto com o runtime |
| `projmap/master/__main__.py` | Sobe a transmissão quando `PROJMAP_RTSP_URL` existe no `.env` |
| `.env.example` | Bloco `PROJMAP_RTSP_*` comentado |
| `tests/projmap/test_stream.py` | 7 testes (nenhum usa rede) |

## Como funciona
Uma thread própria puxa `runtime.render(size)` a uma taxa fixa, converte RGBA →
BGR24 e escreve nos quadros crus do `stdin` do ffmpeg, que codifica em H.264
(`-tune zerolatency`, GOP de 2 s para quem entra no meio) e publica por RTSP.

Como é uma thread separada, **servidor lento ou fora do ar não trava a
projeção**: a transmissão reconecta sozinha com recuo progressivo (1 s → 15 s).
A senha é mascarada em todo log e mensagem de erro (`rtsp://viewer:***@…`).

Configuração (só `.env`, nunca linha de comando — ali a senha apareceria na
lista de processos):

```ini
PROJMAP_RTSP_URL=rtsp://usuario:senha@servidor:8554/cam
PROJMAP_RTSP_SIZE=1280x720
PROJMAP_RTSP_FPS=30
PROJMAP_RTSP_BITRATE=4M
PROJMAP_RTSP_TRANSPORT=tcp
```

Sem `PROJMAP_RTSP_URL`, nada sobe e o ProjMap funciona como antes.

## ⚠ A credencial atual não publica
Testado contra o servidor RTSP do usuário com a credencial `viewer`:

| Teste | Resultado |
|---|---|
| Servidor no ar | ✅ responde RTSP |
| `/cam` ocupado? | ❌ 404 — ninguém publicando no momento |
| Ler (`DESCRIBE`) | ✅ permitido |
| **Publicar (`ANNOUNCE`)** | ❌ **401 Unauthorized** |

O usuário `viewer` é **só de leitura**. Para o ProjMap transmitir, é preciso uma
credencial com permissão de publicação — no MediaMTX, `publishUser`/`publishPass`
do caminho (ou `publishIPs`). O código está pronto: trocando a credencial no
`.env`, transmite.

## Como validar
```bash
pytest -q                      # 452 verdes (7 novos)
```
Com a URL no `.env`, suba o mestre e assista de outra máquina:
```bash
ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay "rtsp://.../cam"
```
Verificado nesta máquina:
- o mesmo pipeline gravando em arquivo gera H.264 640×360 com **75 quadros em
  exatos 3,000 s a 25 fps** (o encoder e a conversão RGBA→BGR estão certos);
- contra o servidor real, o publicador informa `method ANNOUNCE failed: 401
  (Unauthorized)`, mantém a thread tentando e **não derruba** o resto;
- a senha não aparece no log, no status nem na mensagem de erro.

## Critério de aceite
- [x] Publica a camada interativa por RTSP, configurado só pelo `.env`
- [x] Senha nunca no git, no log ou na linha de comando
- [x] Servidor fora do ar não trava a projeção; reconecta sozinho
- [x] `pytest -q` verde
- [ ] Transmissão de ponta a ponta — **bloqueado**: falta credencial de publicação

## Pendências / próximos
- **Credencial de publicação** no servidor (ver acima). É o único item que falta.
- Hoje transmite a camada interativa. Se o que se quer é a **projeção composta**
  (todas as superfícies com warp/blend), o tap muda para a saída do renderer —
  é trocar a função passada ao `start()`.
- Áudio não vai junto (só vídeo).
