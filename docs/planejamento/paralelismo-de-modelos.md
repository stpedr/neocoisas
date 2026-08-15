# Paralelismo de modelos — como as big techs fazem e como replicar aqui

> **Status:** proposta · **Alvo:** Sprint 12 (materializador) + Sprint 16 (escala)
> Como executar várias chamadas de modelo em paralelo **numa única GPU**, sem cair na
> armadilha de copiar padrões desenhados para frota de GPUs.

## 1. O que a literatura mostra

### 1.1. Camada de serving — *continuous batching*

O padrão de produção em 2026 é o **vLLM**, que popularizou **PagedAttention** e o
**continuous batching**: em vez de esperar um lote fechar, novas requisições entram na
batelada **no meio da geração**, assim que abre um slot. Isso derruba a latência de cauda e
mantém a GPU ocupada.

| Cenário | vLLM | Ollama |
|---|---|---|
| 8 usuários concorrentes (Llama 3 8B) | ~187 tok/s | ~82 tok/s |
| Pico com muitas requisições | **~793 tok/s** | **~41 tok/s** |

Fonte: [Swfte](https://www.swfte.com/blog/vllm-continuous-batching-deep-dive),
[aifoss](https://aifoss.dev/blog/vllm-review-2026/). Sob concorrência alta a diferença chega a
**~19×** — o Ollama *degrada* quando o paralelismo sobe, enquanto o vLLM ganha escala.

### 1.2. Camada de agentes — *fan-out* orquestrador→trabalhadores

A Anthropic descreve o sistema de Research como orquestrador que **dispara 3–5 subagentes em
paralelo**, com paralelismo em **dois níveis** (o líder abre N subagentes; cada subagente faz
chamadas de ferramenta em paralelo) — até **90% menos tempo** em consultas complexas, ao custo
de **~15× mais tokens**. A falha clássica relatada: subagentes **duplicando trabalho** por não
saberem dos vizinhos; a correção foi **fronteira explícita na delegação** ("não pesquise X,
isso é de outro subagente").
([Anthropic/Claude](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them),
[ByteByteGo](https://blog.bytebytego.com/p/how-anthropic-built-a-multi-agent))

## 2. O problema que isso revela no nosso sistema

**`OLLAMA_NUM_PARALLEL` tem default `1`.** Ou seja: hoje, mesmo que a gente dispare dez
chamadas de uma vez, **o Ollama as processa uma a uma**. Todo o pipeline é serial na prática.

E a restrição de VRAM é dura: o consumo escala **linearmente** —
`VRAM ≈ NUM_PARALLEL × CONTEXT_LENGTH` — e, na GPU, um modelo só carrega concorrentemente se
**couber inteiro** na VRAM; faltando memória, as requisições **enfileiram**
([Ollama FAQ](https://docs.ollama.com/faq)).

> **A armadilha:** big techs paralelizam sobre **frota de GPUs**. Nós temos **uma**. Copiar
> "dispare 5 subagentes" sem mais nada não acelera nada — só troca espera por fila.

## 3. A adaptação: paralelismo **por classe de recurso**

A ideia central é que nem todo trabalho disputa o mesmo recurso. Classificando cada etapa,
aparece paralelismo **real e grátis**:

| Classe | Etapas nossas | Recurso | Concorrência |
|---|---|---|---|
| **GPU** | LLM de texto, imagem (SD/ComfyUI), visão | GPU/VRAM | **escassa** — semáforo = `NUM_PARALLEL` |
| **CPU** | **motor de slides (Pillow)**, FFmpeg, parsing, calendário | núcleos | **ampla** — nº de núcleos |
| **Rede** | Graph API, coleta de métricas, downloads | banda/latência | **ampla** — dezenas |

O motor de slides que acabamos de entregar é **CPU puro** — ele pode compor os PNGs de um post
**enquanto a GPU já trabalha no próximo**. Esse é o ganho maior e não custa VRAM nenhuma.

### 3.1. Onde o fan-out é legítimo

Paralelizável (itens independentes):

- **N slots** da janela de materialização;
- **N regiões** por slot (o fan-out de variantes);
- **N artes** de um carrossel (uma por slide);
- **crítico + titler** sobre o mesmo conteúdo.

**Não** paralelizável (dependência real): `copy → arte` (a arte precisa do `visual_prompt` que
a copy produz) e `arte → layout` (o layout precisa da imagem).

### 3.2. Pipelining — o truque que funciona com uma GPU

Com as etapas classificadas, o ganho vem de **sobrepor estágios de classes diferentes**, como
num pipeline de CPU:

```
post 1:  [copy GPU][arte GPU x8][layout CPU][publica REDE]
post 2:            [copy GPU   ][arte GPU x8][layout CPU][publica REDE]
post 3:                         [copy GPU   ][arte GPU x8][layout CPU]
                    ↑ GPU nunca ociosa        ↑ CPU e rede em paralelo
```

A GPU vira o **recurso serializado** que dita o ritmo; CPU e rede escondem seus custos atrás
dela. É isso que transforma um lote de 20 posts de "soma de tudo" em "tempo de GPU + ε".

### 3.3. Fronteira explícita (a lição da Anthropic)

Ao abrir variantes por região ou slides de um carrossel, cada tarefa recebe **escopo
explícito** — "você é o slide 4 de 8, papel *conteúdo*, não repita o gancho" — exatamente a
correção que a Anthropic aplicou para subagentes pararem de duplicar trabalho. Sem isso, o
carrossel sai com 3 slides dizendo a mesma coisa.

## 4. Desenho proposto

### 4.1. Executor com semáforo por classe

```python
# Uma fila de trabalho, três limites — o de GPU espelha o servidor de modelos.
LIMITES = {"gpu": int(os.environ.get("ANE_GPU_CONCURRENCY", "2")),
           "cpu": os.cpu_count() or 4,
           "io":  16}
```

- Cada tarefa declara sua **classe**; o executor respeita o limite daquela classe.
- O limite de `gpu` **acompanha** `OLLAMA_NUM_PARALLEL` — passar disso só cria fila no Ollama
  e gasta VRAM à toa.
- Falha de uma tarefa **não derruba o lote** (mesmo contrato do `post_approved` e do
  `run_scheduled_posts`, que já registram o erro na `note` e seguem).

### 4.2. Serving trocável — o padrão do repo aplicado à escala

O `text_provider` já é um factory. Basta um provider novo:

| Provider | Quando | Concorrência |
|---|---|---|
| `ollama` | solo / desenvolvimento / uma GPU | 1–4 (`NUM_PARALLEL`) |
| **`vllm`** *(novo)* | agência, muitos clientes | dezenas (continuous batching) |
| `gemini` | nuvem opt-in | limite da API |

Isso replica a prática de big tech **sem quebrar** a arquitetura: quem roda em casa continua
no Ollama; quem opera uma agência sobe o vLLM e ganha ~19× em pico — trocando **uma linha de
config**.

### 4.3. Ajuste do Ollama (ganho imediato, custo zero)

```bash
OLLAMA_NUM_PARALLEL=2        # começar em 2 e medir; VRAM escala linearmente
OLLAMA_MAX_LOADED_MODELS=2   # ex.: texto + visão carregados juntos
```

Como `VRAM ≈ NUM_PARALLEL × CONTEXT_LENGTH`, subir sem medir **degrada**: os modelos param de
caber e tudo enfileira. Regra: subir de 1 em 1, medindo.

## 5. O que **não** vamos fazer

- **Não** disparar fan-out ilimitado: numa GPU só, vira fila com mais consumo de memória.
- **Não** paralelizar o que tem dependência real (copy→arte→layout).
- **Não** adotar vLLM como padrão: ele quer GPU dedicada e mais setup; o padrão segue Ollama,
  local-first e simples (persona **Léo**).
- **Não** perseguir os "15× tokens" do fan-out agressivo: aqui o produto é conteúdo em lote,
  não uma resposta melhor — o objetivo é **throughput**, não profundidade.

## 6. Cards (Sprint 16 · Escala e paralelismo)

1. **Executor com semáforo por classe de recurso** (gpu/cpu/io) + falha isolada. `alta`, backend.
2. **Materializador em lote paralelo** — N slots e N regiões concorrentes, respeitando os limites. `alta`, backend.
3. **Pipelining das etapas** — sobrepor layout (CPU) e publicação (rede) com a geração (GPU). `alta`, backend.
4. **Fronteira explícita na delegação** — escopo por slide/região no prompt (anti-duplicação). `média`, conteúdo.
5. **Provider `vllm` no factory de texto** — continuous batching para escala de agência. `média`, backend, infra.
6. **Config de concorrência do Ollama** (`NUM_PARALLEL`/`MAX_LOADED_MODELS`) + doc de tuning. `média`, infra.
7. **Medição** — tempo por etapa e ocupação por classe, para achar o gargalo real. `alta`, backend, testes.

## 7. Critério de aceite

- [ ] Um lote de N posts usa **concorrência limitada por classe**, sem estourar VRAM.
- [ ] Layout (CPU) e publicação (rede) **sobrepõem** a geração (GPU) — medido, não presumido.
- [ ] Falha de um post não derruba o lote.
- [ ] Trocar `text_provider` para `vllm` **não exige mudança nos agentes**.
- [ ] Fan-out de slides/regiões não produz conteúdo duplicado.

## 8. Referências

- [vLLM continuous batching deep dive](https://www.swfte.com/blog/vllm-continuous-batching-deep-dive) · [vLLM review 2026](https://aifoss.dev/blog/vllm-review-2026/) · [LLM serving optimization](https://www.spheron.network/blog/llm-serving-optimization-continuous-batching-paged-attention/)
- [Ollama FAQ — concorrência e VRAM](https://docs.ollama.com/faq) · [Como o Ollama trata requisições paralelas](https://www.glukhov.org/llm-performance/ollama/how-ollama-handles-parallel-requests/)
- [Anthropic — quando usar sistemas multi-agente](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them) · [ByteByteGo — como a Anthropic construiu](https://blog.bytebytego.com/p/how-anthropic-built-a-multi-agent)
</content>
