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

## 3-bis. Multi-modelo: **dois modelos ao mesmo tempo** na mesma GPU

A seção anterior trata a GPU como **uma pista serializada**. Isso é verdade para *um* modelo —
mas o nosso pipeline usa **modelos diferentes em estágios diferentes** (texto, imagem, visão).
Se dois deles couberem juntos na VRAM, a pista da GPU **se divide**: a `copy` do post N+1 roda
**enquanto** a `arte` do post N está sendo gerada.

### 3-bis.1. Os três modos de compartilhar uma GPU

| Modo | Execução | Isolamento | Hardware | Onde serve |
|---|---|---|---|---|
| **Time-slicing** | **não** concorrente — contextos em *round-robin* | fraco | qualquer (padrão pós-Volta) | dev, tráfego baixo |
| **MPS** (Multi-Process Service) | **concorrente de verdade** — kernels simultâneos | espaços de endereço virtuais isolados, **sem** isolamento de falha | qualquer Volta+ | **cargas confiáveis do mesmo time** ← o nosso caso |
| **MIG** (Multi-Instance GPU) | concorrente, particionada | **isolamento de hardware** (compute, memória, cache) | A100/H100+ (até 7 instâncias) | produção multi-tenant com SLA |

Fontes: [NVIDIA](https://developer.nvidia.com/blog/maximize-ai-infrastructure-throughput-by-consolidating-underutilized-gpu-workloads/),
[Spheron](https://www.spheron.network/blog/run-multiple-llms-one-gpu-mig-time-slicing-guide/),
[Colfax](https://research.colfax-intl.com/sharing-nvidia-gpus-at-the-system-level-time-sliced-and-mig-backed-vgpus/).

Detalhe que importa: o **padrão** de uma GPU pós-Volta é **time-slicing**, que **não** executa
em paralelo — só reveza. Em concorrência baixa (1–2 requisições por modelo) a latência extra é
desprezível; sob carga sustentada aparecem **picos de latência** quando a fatia de tempo expira
no meio de uma requisição. Para paralelismo real entre processos é preciso **MPS**.

### 3-bis.2. O que o Triton ensina (mesmo sem adotá-lo)

O Triton resolve isso com **instance groups**: vários modelos — ou várias instâncias do mesmo —
carregados na GPU, cada um em seu **CUDA stream**. Quando chegam duas requisições para dois
modelos distintos, ele agenda as duas e **o escalonador de hardware trabalha nas duas em
paralelo**. Duas instâncias costumam melhorar o desempenho porque **sobrepõem transferência de
memória (CPU↔GPU) com computação**
([NVIDIA Triton](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/model_execution.html)).

Duas ressalvas honestas, também da doc do Triton:

- O isolamento é **parcial**: a inferência de um modelo **pode impactar** a do outro — eles
  disputam os mesmos SMs, mesmo com a VRAM sobrando.
- Em dispositivo restrito, o recomendado é **1–3 instâncias**, não mais.

> Ou seja: **caber na VRAM é necessário, não suficiente.** O ganho não é "2× porque são dois
> modelos" — vem de **sobrepor fases complementares**.

### 3-bis.3. Por que, no nosso caso, a combinação é boa

O par que mais aparece no nosso pipeline é **LLM de texto + difusão de imagem**, e eles são
**complementares** no uso do hardware:

| Estágio | Perfil dominante |
|---|---|
| Decodificação do LLM (copy, crítico) | **limitado por banda de memória** |
| Difusão (SDXL/ComfyUI) | **limitado por computação** |

Rodar os dois juntos tende a preencher a ociosidade um do outro — exatamente o caso em que
co-locação compensa. Já dois LLMs de texto juntos disputam o mesmo gargalo e rendem menos.

### 3-bis.4. Faixas de GPU (ordem de grandeza)

Consumo aproximado dos nossos modelos: texto 8B Q4 ≈ **5 GB** · visão 11B Q4 ≈ **8 GB** ·
SDXL fp16 ≈ **7 GB** · Piper ≈ **0** (CPU). Somar ainda o KV cache
(`NUM_PARALLEL × CONTEXT_LENGTH`).

| VRAM | Exemplo | Residentes | Config | Efeito no pipeline |
|---|---|---|---|---|
| **8–12 GB** | RTX 3060/4070 | **1** modelo | `MAX_LOADED_MODELS=1`, `NUM_PARALLEL=1–2` | GPU é **uma** pista; troca de estágio custa *swap* |
| **16–24 GB** | 4080/4090/3090 | **2** (texto + imagem) | `MAX_LOADED_MODELS=2`, `NUM_PARALLEL=2` | **duas sub-pistas**: copy e arte simultâneas |
| **32–48 GB** | A6000 / 2×24 GB | **3** (+ visão) | `MAX_LOADED_MODELS=3`, `NUM_PARALLEL=2–4` | onboarding (visão) sem despejar os outros |
| **A100/H100** | datacenter | MIG | partições isoladas | latência determinística por classe |

### 3-bis.5. O modo de falha: *thrashing* de modelos

Este é o risco real de exagerar. Pela doc do Ollama: **faltando memória para carregar um novo
modelo, as requisições ficam em fila** e, conforme modelos ficam ociosos, **um ou mais são
descarregados** para abrir espaço ([Ollama FAQ](https://docs.ollama.com/faq)).

Num pipeline que alterna `texto → imagem → texto → imagem`, subscrever demais a VRAM produz
**carrega/descarrega em looping** — cada troca custa segundos de leitura de disco. O resultado
fica **pior** que rodar serializado.

**Regra de segurança:** `soma dos modelos residentes + KV cache ≤ ~85% da VRAM`. Acima disso,
reduza `MAX_LOADED_MODELS` em vez de torcer.

### 3-bis.6. Como entra na nossa arquitetura

1. **Perfil de hardware detectado/declarado** — `ANE_GPU_PROFILE` (`small|medium|large`) ou
   detecção por VRAM disponível, definindo `MAX_LOADED_MODELS`, `NUM_PARALLEL` e os limites do
   semáforo.
2. **Semáforo por *modelo*, não só por classe** — em vez de um único contador "gpu", um por
   modelo residente (`gpu:texto`, `gpu:imagem`), refletindo que são pistas distintas. Quando só
   cabe um modelo, os semáforos colapsam em um — mesmo código, comportamento correto nas duas
   faixas.
3. **Escalonamento consciente do residente** — preferir despachar trabalho cujo modelo **já
   está carregado**, agrupando tarefas do mesmo modelo antes de forçar troca. Isso, sozinho,
   elimina a maior parte do *thrashing*.
4. **MPS opcional** para quem tem GPU forte e quer concorrência real entre processos
   (Ollama + ComfyUI são **processos separados** — sem MPS eles se revezam por time-slicing).

## 4. Desenho proposto

### 4.1. Executor com semáforo por classe

```python
# Limites por classe; a classe "gpu" se subdivide por MODELO residente quando
# a VRAM comporta mais de um (ver §3-bis).
LIMITES = {
    "gpu:texto":  int(os.environ.get("ANE_GPU_TEXT", "2")),   # = OLLAMA_NUM_PARALLEL
    "gpu:imagem": int(os.environ.get("ANE_GPU_IMAGE", "1")),
    "cpu":        os.cpu_count() or 4,
    "io":         16,
}
# Em GPU pequena, ANE_GPU_PROFILE=small colapsa gpu:* num único semáforo — o
# mesmo código roda certo nas duas faixas de hardware.
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

### 4.4. Ajuste multi-modelo por faixa de GPU

```bash
# GPU média (16-24 GB): texto e imagem residentes ao mesmo tempo
OLLAMA_MAX_LOADED_MODELS=2
OLLAMA_NUM_PARALLEL=2
ANE_GPU_PROFILE=medium

# GPU pequena (8-12 GB): um modelo por vez, sem thrashing
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1
ANE_GPU_PROFILE=small
```

Opcional em GPU forte, para concorrência **real** entre processos separados
(Ollama e ComfyUI são processos distintos — sem MPS eles se revezam):

```bash
nvidia-cuda-mps-control -d      # habilita o Multi-Process Service
```

## 5. O que **não** vamos fazer

- **Não** disparar fan-out ilimitado: numa GPU só, vira fila com mais consumo de memória.
- **Não** paralelizar o que tem dependência real (copy→arte→layout).
- **Não** adotar vLLM como padrão: ele quer GPU dedicada e mais setup; o padrão segue Ollama,
  local-first e simples (persona **Léo**).
- **Não** subscrever a VRAM para "caber mais um modelo": o *thrashing* de carga/descarga custa
  segundos por troca e fica **pior** que serializar (§3-bis.5).
- **Não** co-locar dois LLMs de texto: disputam o mesmo gargalo (banda de memória) e rendem
  pouco. A co-locação boa é **texto + imagem**, que são complementares.
- **Não** exigir MIG: é A100/H100. Para nós, MPS cobre o caso e roda em GPU de consumidor.
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
8. **Perfil de GPU (`ANE_GPU_PROFILE`)** — detecta/declara a faixa de VRAM e deriva
   `MAX_LOADED_MODELS`, `NUM_PARALLEL` e os semáforos. `alta`, backend, infra.
9. **Semáforo por modelo residente** (`gpu:texto`, `gpu:imagem`) que colapsa em um só quando a
   GPU comporta um modelo. `alta`, backend.
10. **Escalonamento consciente do residente** — agrupar tarefas do modelo já carregado antes de
    forçar troca (anti-*thrashing*). `alta`, backend.
11. **MPS opcional documentado** — concorrência real entre Ollama e ComfyUI em GPU forte.
    `baixa`, infra, docs.

## 7. Critério de aceite

- [ ] Um lote de N posts usa **concorrência limitada por classe**, sem estourar VRAM.
- [ ] Layout (CPU) e publicação (rede) **sobrepõem** a geração (GPU) — medido, não presumido.
- [ ] Falha de um post não derruba o lote.
- [ ] Trocar `text_provider` para `vllm` **não exige mudança nos agentes**.
- [ ] Fan-out de slides/regiões não produz conteúdo duplicado.
- [ ] Em GPU de 16–24 GB, **texto e imagem ficam residentes juntos** e os estágios `copy` e
      `arte` de posts diferentes rodam **simultaneamente** (medido).
- [ ] Em GPU de 8–12 GB, o sistema **degrada para uma pista** sem *thrashing* — mesma base de
      código, só o perfil muda.
- [ ] A soma dos modelos residentes + KV cache fica **≤ ~85% da VRAM**.

## 8. Referências

- [vLLM continuous batching deep dive](https://www.swfte.com/blog/vllm-continuous-batching-deep-dive) · [vLLM review 2026](https://aifoss.dev/blog/vllm-review-2026/) · [LLM serving optimization](https://www.spheron.network/blog/llm-serving-optimization-continuous-batching-paged-attention/)
- [Ollama FAQ — concorrência e VRAM](https://docs.ollama.com/faq) · [Como o Ollama trata requisições paralelas](https://www.glukhov.org/llm-performance/ollama/how-ollama-handles-parallel-requests/)
- [Anthropic — quando usar sistemas multi-agente](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them) · [ByteByteGo — como a Anthropic construiu](https://blog.bytebytego.com/p/how-anthropic-built-a-multi-agent)
- **Multi-modelo na mesma GPU:** [NVIDIA — consolidar cargas subutilizadas](https://developer.nvidia.com/blog/maximize-ai-infrastructure-throughput-by-consolidating-underutilized-gpu-workloads/) · [Spheron — MIG, time-slicing e MPS](https://www.spheron.network/blog/run-multiple-llms-one-gpu-mig-time-slicing-guide/) · [Colfax — compartilhamento em nível de sistema](https://research.colfax-intl.com/sharing-nvidia-gpus-at-the-system-level-time-sliced-and-mig-backed-vgpus/) · [Triton — execução concorrente de modelos](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/model_execution.html) · [Demystifying NVIDIA MPS](https://sagar-parmar.medium.com/demystifying-nvidia-mps-how-multi-process-service-improves-gpu-sharing-and-performance-9f633878318a)
</content>
