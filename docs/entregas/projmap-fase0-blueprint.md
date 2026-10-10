# ProjMap — Fase 0: blueprint de engenharia reversa + plano de implementação

## Resumo

Fase 0 do sistema de **projeção mapeada assistida por IA**, com múltiplos
projetores em rede: estudo de WZRD, ifnull/projection-mapping-workflow,
mapamok, OpenCV `structured_light` e seed42, consolidado num blueprint
(arquitetura, pipeline, algoritmos e formatos de dados) e num plano por fases
(F1–F7). **Nenhum código de produto foi escrito.** O plano aguarda aprovação.

## Motivação

O pedido define que a fase 0 vem antes de codar, com uma regra explícita:
reimplementar do zero, respeitar licenças e não executar binários de
repositórios desconhecidos. O blueprint fixa as decisões que mais custam caro
se forem erradas: o modelo de warp, os espaços de coordenadas, o protocolo e a
sincronia, e o renderer no Raspberry Pi 5. Assim cada fase seguinte tem
critério de aceite mensurável.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `docs/projmap/BLUEPRINT.md` | Novo. Método REA aplicado, licenças por alvo, ledger de achados (observação com `arquivo:linha` no commit fixado / inferência / desconhecido), síntese da arquitetura, formatos (`project.json`, protocolo mestre↔nó), sincronia, seed42 → remote mobile. |
| `docs/projmap/PLANO.md` | Novo. Decisões D1–D8 para aprovação, estrutura de módulos, fases F1–F7 com tarefas e checklists de aceite, testes, riscos, dependências e licenças. |
| `board/seed.py` | Sprint 11 · Projeção mapeada: card F0 em **Revisão** e F1–F7 em **Backlog**. |
| `docs/entregas/projmap-fase0-blueprint.md` | Este documento. |

## Como funciona

- **Uso do REA:** o skill oficial do REA manda *não* usá-lo para analisar
  repositórios com código-fonte, e rodá-lo exigiria executar pacotes de
  terceiros. Então foi usada a **metodologia** dele: checklist de perguntas,
  ledger de evidências e marcação de lacunas. As ferramentas não foram usadas.
  Os repositórios foram clonados só como dados, num diretório temporário fora
  do repo, sem executar nada.
- **Principais achados que viram decisões:**
  - warp = homografia base + correção local (lição do WZRD: spline direto nos
    4 cantos entorta retas);
  - LUT de warp assado só quando muda;
  - Gray code com inversos + máscara de sombra + confiança + descarte de LSBs;
  - detecção do quad projetado melhorada (`approxPolyDP`/`fitLine` em vez de
    `minAreaRect`);
  - modo *baked* para robustez no Pi;
  - relógio NTP-like + contrato de playback + latência por projetor;
  - remote mobile por QR + Capacitor no Android, porque câmera/PWA exigem
    HTTPS e a LAN é HTTP.
- **Licenças:** WZRD e ifnull **não têm licença**, então só ideias foram
  aproveitadas. mapamok é MIT. O módulo do OpenCV é Apache-2.0 e entra como
  dependência e oráculo de teste. Evitar ultralytics (AGPL), mpv embutido
  (GPL) e redistribuir o NDI SDK.

## Como validar

```bash
# Documentos
less docs/projmap/BLUEPRINT.md docs/projmap/PLANO.md

# Board: os novos cards entram em boards novos (seed). Em board existente, use force:
python -c "from board.seed import SEED_CARDS; print([c['title'] for c in SEED_CARDS if 'ProjMap' in c['title']])"

# Testes (nada de código mudou além do seed)
python -m pytest -q        # 151 passed
```

## Critério de aceite

- [x] Blueprint com arquitetura, pipeline, algoritmos e formatos de dados.
- [x] Cada achado ligado a evidência (`arquivo:linha` no commit lido) ou
      marcado como inferência/desconhecido.
- [x] Licenças de cada referência verificadas. Nenhum código copiado.
- [x] Nenhum binário ou script de terceiros executado.
- [x] Plano por fases F1–F5 (do pedido) + F6 (web no celular/app Android,
      seed42) + F7 opcional, cada uma com aceite mensurável.
- [x] Kanban atualizado (Sprint 11).
- [ ] **Aprovação do usuário** das decisões D1–D8 → só então começa a F1.

## Pendências / próximos

- **Aguardando aprovação** (D1–D8 no `PLANO.md §1`).
- Desconhecidos que exigem hardware: U1 (moderngl no Pi 5), U2 (decode de
  vídeo na CPU do Pi 5), U3 (NDI no Pi 5), U4 (SAM 2 no Windows), U5 (input lag
  dos projetores).
- seed42 analisado só pela página pública: o acesso direto foi bloqueado pelo
  proxy deste ambiente.
- Após aprovação: F1 (1 projetor local, quads + vídeo/GIF).
