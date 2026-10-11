# ProjMap F3a — Detecção automática de superfícies (OpenCV)

## Resumo
Botão **Detectar na foto**: o mestre analisa a foto da posição do projetor e
sugere as superfícies (paredes, porta, teto, colunas, painéis). O operador
marca as que quer e cria todas de uma vez, já posicionadas no projetor.

## Motivação
Até aqui cada superfície era desenhada à mão, canto por canto, sobre a foto.
O pedido foi "tirei a foto de uma casa e ela já mapeia o muro, cada coluna,
cada canto". É a F3 do `docs/projmap/PLANO.md`. Esta entrega é o motor
clássico (sem torch); o SAM 2 entra pelo mesmo contrato (F3b).

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/detect/__init__.py` · `base.py` · `factory.py` | Contrato `Detector`/`Candidate` e `get_detector(name)` (padrão do repo) |
| `projmap/detect/classic.py` | Detector OpenCV (ver "Como funciona") |
| `projmap/master/app.py` | `POST /api/nodes/{id}/detect` (`detector`, `sensitivity`, `max_candidates`); não altera o projeto |
| `projmap/ui/app/components/DetectPanel.tsx` | Novo card: sensibilidade, detectar, lista com marcação, criar |
| `projmap/ui/app/components/Editor.tsx` | Candidatos numerados sobre a foto/projetor; clique marca/desmarca |
| `projmap/ui/app/page.tsx` · `lib/api.ts` · `lib/types.ts` · `globals.css` | Estado dos candidatos e criação das superfícies (foto → projetor, `polygon_src` guardado) |
| `tests/projmap/test_detect.py` | 9 testes (imagens sintéticas + API) |
| `projmap/README.md` · `board/seed.py` | Guia de uso; F3a em done e F3b no backlog |

## Como funciona
Foto reduzida a 640 px no lado maior:
1. **Mean-shift:** alisa a textura (madeira, reboco, ruído de celular) e
   preserva as bordas.
2. **Bordas Canny dilatadas** viram barreiras. É o que separa as duas paredes
   de uma quina, que têm a mesma cor.
3. **k-means em Lab** com a claridade pesando 0,35. O degradê de luz numa
   parede ou porta não a parte em faixas. Centros próximos (ΔE < 10) se unem,
   e o número de cores se adapta à foto.
4. **Componentes conexos por cor**, com os buracos preenchidos: uma mancha de
   luz ou um quadro na parede não interrompem a superfície.
5. **Junção de oclusões:** pedaços da mesma cor a até 15 px um do outro se
   juntam quando a união continua sendo um bom quadrilátero. Exemplo: a porta
   cortada por uma fita.
6. **Quadrilátero:** o casco convexo é reduzido a 4 vértices (várias
   tolerâncias + retângulo mínimo) e fica o de maior IoU com o casco. O
   objeto na frente "morde" a borda da região; o casco ignora a mordida.
   **Nota** = IoU × √solidez.
7. **Filtros:** NMS por IoU; uma faixa contida numa superfície **da mesma cor**
   sai (teto em degradê, mancha de luz). Uma região de outra cor contida noutra
   fica (porta na parede).

A UI converte cada quad (foto normalizada → px da foto → projetor, pela
homografia da área projetada), valida e cria a superfície com `polygon_src`.

## Como validar
```bash
pytest -q tests/projmap/test_detect.py        # 9 testes, sem GPU
python -m projmap.master --project shows/teste.projmap --windowed --open
# 1 · Foto → enviar → "Detectar superfícies" → Detectar na foto → Criar
```
Na foto real do usuário (quarto com porta aberta, paredes e teto, carrinho e
aspirador na frente), em 0,4 s:
- foram pré-marcados teto, faixa da parede acima da porta, a **porta inteira**
  (inclusive atrás do carrinho) e a parede direita;
- objetos soltos (aspirador, mochila) aparecem desmarcados;
- a criação gerou as 4 superfícies no mestre, e a prévia da F9 mostrou a
  cartela em cada uma.

A foto não foi versionada (é da casa do usuário); os testes usam cenas
sintéticas.

## Critério de aceite
- [x] `classic` funciona sem torch (roda no CI)
- [x] Quad em perspectiva com erro de canto < 1% da diagonal (teste)
- [x] Superfície cortada por um objeto vira uma só (teste)
- [x] Detectar não altera o projeto; criar só o que foi marcado
- [x] `pytest -q` verde (285) e `npm run build` ok
- [ ] Re-detecção mantém ids das superfícies existentes (F3b)
- [ ] SAM 2 (F3b)

## Pendências / próximos (F3b)
- **SAM 2:** clicar no objeto ou desenhar uma caixa (fotos com textura e
  sombra).
- **Área projetada automática:** foto com o projetor em branco → acha o quad
  da luz → preenche o passo 2.
- Re-detecção que preserva superfícies existentes (casar por IoU).
- Superfícies não quadradas (polígono completo, quando o renderer suportar
  máscaras).
