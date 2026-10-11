# ProjMap — Galeria de mídias (pastas/Google Drive) + sugestões por superfície

## Resumo
Galeria com miniaturas no lugar das listas suspensas, ligada às pastas do PC
(inclusive o Google Drive sincronizado). Sugestões de mídia para cada região
mapeada. Guia de configuração e uso para o operador.

## Motivação
Pedidos do usuário:
- "quero subir minhas mídias no Drive, ou outra alternativa mais fácil, para
  que ele veja as pastas e me sugira o que colocar nas regiões";
- "a lista da caixa de seleção fica muito grande";
- "não entendi o Blackout nem o Exportar";
- "uma documentação de como configurar para usar".

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/library.py` | Novo: biblioteca de pastas (varredura recursiva, metadados via PIL/PyAV, miniaturas JPEG em cache, raízes em `~/.projmap/library.json`) |
| `projmap/suggest.py` | Novo: nota por proporção, resolução e tipo, com motivos; `suggest_all` sem repetir mídias |
| `projmap/master/library_api.py` | Novo: `GET /api/library`, `PUT /api/library/roots` (só no mestre), `GET /api/library/{id}/thumb`, `POST /api/library/{id}/import`, `GET /api/media-info`, `GET /api/media/{sha}/thumb`, `POST /api/suggest` |
| `projmap/master/app.py` · `__main__.py` | Liga o router; `--library PASTA` |
| `projmap/ui/app/components/MediaGallery.tsx` | Novo: galeria (No projeto / Minhas pastas, busca, tipo, pasta, ⭐ sugeridas) |
| `projmap/ui/app/components/SuggestAll.tsx` | Novo: "⭐ Sugerir mídias" para todas as superfícies |
| `projmap/ui/app/components/LibraryCard.tsx` | Novo: configurar as pastas (só no PC) |
| `SurfacePanel.tsx` · `LayersPanel.tsx` · `remote/page.tsx` | Lista suspensa trocada por botão com miniatura que abre a galeria (editor e celular) |
| `projmap/ui/app/page.tsx` | Estado da galeria/sugestões; dicas (tooltips) em **Blackout** e **Exportar .pmz** |
| `projmap/GUIA.md` | Novo: guia do operador (instalar, mapear, galeria/Drive, camadas, celular, show, backup, problemas) |
| `tests/projmap/test_library.py` | 8 testes |

## Como funciona
- **Por que não a API do Google Drive:** ela exige projeto no Google Cloud,
  chave OAuth e login dentro do app. O *Google Drive para computador* já
  espelha o Drive numa pasta local. O ProjMap só lê essa pasta, o que serve
  também para OneDrive, Dropbox e HD externo, e funciona offline no local do
  show.
- **Segurança:** a API nunca recebe caminhos. Os itens têm ids opacos (hash do
  caminho), e só o próprio mestre (loopback) pode trocar as pastas. Importar
  copia por hash para `media/`, sem duplicar.
- **Sugestões:** nota = 0,6 × proporção (em log) + 0,25 × resolução suficiente
  + bônus por tipo (vídeo em superfície grande). "Sugerir para todas": as
  maiores escolhem primeiro e pegam a melhor ainda não usada, se não for 40%
  pior que a melhor. Cada sugestão traz o motivo.

## Como validar
```bash
pytest -q                                     # 387 verdes (8 novos)
cd projmap/ui && npm run build
python -m projmap.master --project shows/x.projmap --windowed --library "G:\Meu Drive\Projeção" --open
```
Verificado ao vivo no Chrome, com uma pasta simulando o Drive
(`Meu Drive/Projeção/{Natal,Fachada}`, com vídeo, GIF e fotos de formatos
variados) e o projeto da foto real do usuário (4 superfícies detectadas):
- "⭐ Sugerir mídias" propôs uma mídia por superfície, com motivos, e
  "Aplicar" trocou as 4;
- a galeria mostrou as sugeridas, as abas, as miniaturas, a duração e a
  resolução, e os filtros funcionaram.

## Critério de aceite
- [x] Galeria com miniaturas no editor e no celular (sem listas enormes)
- [x] Pastas do PC/Drive sincronizado, configuráveis só no mestre
- [x] Sugestões por superfície com motivo; sugerir para todas sem repetir
- [x] Blackout e Exportar explicados (dicas na UI e no guia)
- [x] Guia de configuração e uso (`projmap/GUIA.md`)
- [x] `pytest -q` verde e `npm run build` ok

## Pendências / próximos
- Integração direta com a API do Drive (sem o app de desktop), se fizer falta.
- Sugestão por **conteúdo** (cores/tema da mídia vs. a parede, com o modelo de
  visão), além do formato.
- Pré-visualizar a mídia na parede antes de confirmar ("passar o mouse").
- Paginação/virtualização da galeria para pastas com milhares de arquivos.
