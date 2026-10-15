# ProjMap — Sincronização da documentação com o código atual

## Resumo
Revisão da documentação do ProjMap contra o estado real do código e dos
últimos commits: corrige informação defasada (os 5 efeitos do visual_frames,
não 3), documenta duas entregas que ainda não apareciam fora dos MDs de
entrega (GPU dedicada/tela do projetor e transmissão RTSP) e adiciona os
cards correspondentes ao Kanban, que estava sem eles.

## Motivação
Pedido do usuário para analisar o projeto, atualizar a documentação e
explicar a arquitetura/funcionamento atual. Na leitura, três coisas estavam
fora de sincronia com o código:

1. `GUIA.md` ainda dizia "Bichinho espelho e Paraquedas virão numa segunda
   etapa", mas os dois já foram entregues (commit `11a958b`).
2. A correção de GPU dedicada (`tools/gpu.py`) e de seleção automática de
   tela (`node/screens.py`) e a transmissão RTSP (`interact/stream.py`)
   tinham MD de entrega, mas não apareciam nos guias de uso/arquitetura nem
   no Kanban (`board/seed.py`) — útil só para quem já sabia procurar em
   `docs/entregas/`.

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/GUIA.md` | §6.3: lista os 5 efeitos (antes só 3) e troca a nota de pendência por instrução de usar `python -m projmap.tools.gpu` em notebooks híbridos |
| `projmap/README.md` | Nota sobre `--display auto` (antes só `--display 1`/`0`), GPU dedicada, e link para a transmissão RTSP na seção "Projeção interativa" |
| `projmap/interact/README.md` | Nova seção "Assistir de outra máquina (RTSP)": variáveis de `.env`, comando `ffplay`, comportamento de reconexão |
| `projmap/ARCHITECTURE.md` | §4 (Renderer): bullets sobre ordem estável das telas e preferência de GPU dedicada. §8 (camada interativa): bullet sobre o `RtspPublisher` |
| `board/seed.py` | 2 cards novos: "Saída automática pro projetor + GPU dedicada + sensor C920 estável" (`done`) e "Transmissão RTSP da camada interativa" (`review` — falta credencial de publicação no servidor do usuário) |
| `docs/entregas/sincronizacao-docs-projmap.md` | Este arquivo |

Nenhum código de produto foi alterado — só documentação e o seed do Kanban.

## Como funciona
Cada entrega recente (`projmap-efeitos-visual-frames-fase2.md`,
`projmap-tela-projetor-auto.md`, `projmap-transmissao-rtsp.md`) já descrevia
a mudança corretamente; o gap era que os guias de uso (`GUIA.md`,
`README.md`, `interact/README.md`) e o `ARCHITECTURE.md` — que é o que
alguém lê para saber "como o ProjMap funciona hoje" sem vasculhar o
histórico de commits — não tinham sido atualizados junto. Esta entrega fecha
esse gap, e o Kanban passa a ter um card por entrega, inclusive as que não
vieram de um card de fase pré-existente.

## Como validar
```bash
pytest -q                      # nenhum código mudou; deve continuar verde
cd projmap/ui && npm run build  # UI não mudou, build inalterado
```
Revisão visual: abrir `projmap/GUIA.md` §6.3, `projmap/interact/README.md`
e `projmap/ARCHITECTURE.md` e confirmar que batem com `effects/catalog.py`,
`interact/stream.py` e `node/screens.py`/`tools/gpu.py`.

## Critério de aceite
- [x] `GUIA.md` lista os 5 efeitos e não tem mais a nota de pendência
- [x] GPU dedicada, seleção automática de tela e transmissão RTSP
      documentadas nos guias de uso/arquitetura (não só no MD de entrega)
- [x] Kanban com um card por entrega recente
- [x] `pytest -q` segue verde (sem mudança de código)

## Pendências / próximos
- A transmissão RTSP continua em `review` no Kanban: falta uma credencial de
  publicação no servidor do usuário (a atual, `viewer`, é só leitura — ver
  `docs/entregas/projmap-transmissao-rtsp.md`).
- F2 (mestre/nós em rede), F3b (SAM 2), F4 (Gray code) e F5 (NDI/PJLink)
  continuam no backlog, sem mudança nesta entrega.
