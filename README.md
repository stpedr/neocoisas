# Auto Niche Engine

Pipeline multi-agente para produção de conteúdo de nicho com **IA local**. O
motor usa o [Ollama](https://ollama.com/) rodando na GPU da própria máquina
(custo zero de inferência) para gerar a estratégia de nicho e os roteiros, e
monta vídeos curtos localmente com FFmpeg.

> **Escopo desta implementação.** Este repositório contém o **núcleo de
> geração de conteúdo**: o agente de estratégia via Ollama, o esqueleto do
> pipeline de vídeo e o painel de controle em Streamlit. A camada de
> _publicação automática em massa_ e as técnicas de _evasão de detecção_
> (fingerprint spoofing, proxies residenciais por conta, etc.) descritas no
> material original **não** fazem parte deste código — elas violam os Termos
> de Uso das plataformas. Faça a publicação pelas APIs oficiais e dentro das
> regras de cada rede.

## Arquitetura

```
[Prompt do Criador / Nicho Ativo]
              │
              ▼
   Agente Estrategista de Nicho  (Ollama, GPU local)
              │  (tópicos em alta)
              ▼
   Agente Roteirista cena-a-cena  (Ollama, GPU local)
              │  (lista de Scene → VideoJob)
              ▼
   Pipeline de Vídeo  (prompts visuais → mídia → TTS → FFmpeg)
              │
              ▼
        Vídeo curto pronto (.mp4)
```

## Estrutura de arquivos

```
neocoisas/
├── main.py                   # Orquestrador central (entrada via CLI)
├── config.example.json       # Modelo de configuração (copie para config.json)
├── requirements.txt
├── requirements-dev.txt      # Dependências de teste (pytest)
├── agents/
│   ├── __init__.py
│   ├── ollama_client.py      # Cliente compartilhado do Ollama (query + parse JSON)
│   ├── niche_creator.py      # Agente de estratégia de nicho (Ollama)
│   ├── script_writer.py      # Agente roteirista cena-a-cena (Ollama)
│   └── video_pipeline.py     # Pipeline de geração de vídeo (esqueleto)
├── dashboard/
│   └── app.py                # Painel do Criador (Streamlit)
└── tests/                    # Testes offline (parsing de JSON e de cenas)
```

## Rodar com Docker (recomendado)

Sobe a stack inteira — **Ollama + API (FastAPI) + frontend (Next.js)** — com um
comando. O Ollama roda no próprio Docker e baixa o modelo no primeiro start.

```bash
docker compose up -d --build
```

- Interface: http://localhost:3000
- API: http://localhost:8000/api/health
- Modelo: defina `OLLAMA_MODEL` (padrão `llama3`), ex.:
  `OLLAMA_MODEL=llama3 docker compose up -d --build`
- **GPU NVIDIA:** descomente o bloco `deploy` do serviço `ollama` no
  `docker-compose.yml` (requer o NVIDIA Container Toolkit).

Serviços: `ollama` (LLM local), `ollama-pull` (baixa o modelo uma vez), `api`
(aponta para `http://ollama:11434` via `ANE_OLLAMA_BASE_URL`) e `web`. O estado
(fila de ideias e Kanban) persiste no volume `ane_output`.

## Interface web (Next.js) + API (FastAPI)

Além do painel Streamlit, o projeto tem uma interface **Next.js** (`web/`) com
duas abas, servida pela API em `server.py`:

- **💡 Ideias** — solte um prompt e escolha o modo: **Manual (Tinder)**, onde
  você aprova/rejeita cada ideia (❌/♥, ou setas ← →) antes de postar; ou
  **Auto (prompta-e-posta)**, em que as ideias já entram aprovadas e a postagem
  fica num gancho para as APIs oficiais.
- **🗂️ Kanban** — planejamento em sprints do projeto (arrastar-e-soltar,
  adicionar/remover cartões), rumo a finalizar e publicar.

Sem Docker, em desenvolvimento (dois terminais):

```bash
# 1) API (mesma máquina do Ollama)
pip install -r requirements.txt
uvicorn server:app --reload --port 8000

# 2) Frontend
cd web && npm install && npm run dev
```

## Como executar localmente (CLI / Streamlit)

1. **Suba o Ollama** na sua máquina, usando a GPU:

   ```bash
   ollama run llama3
   ```

2. **Configure** o projeto copiando o modelo e ajustando os valores:

   ```bash
   cp config.example.json config.json
   ```

3. **Instale as dependências**:

   ```bash
   pip install -r requirements.txt
   ```

4. **Rode pela linha de comando**:

   ```bash
   python main.py                       # usa o nicho de config.json
   python main.py "Gatos Astronautas"   # sobrescreve o nicho pontualmente
   python main.py "Gatos" --script      # plano + roteiro do 1º tópico em alta
   ```

   **ou abra o painel**:

   ```bash
   streamlit run dashboard/app.py
   ```

## Configuração (`config.json`)

| Chave               | Descrição                                             |
| ------------------- | ----------------------------------------------------- |
| `creator_name`      | Nome exibido no painel.                               |
| `active_niche`      | Nicho alvo padrão (ex: `"League of Legends Memes"`).  |
| `ollama_model`      | Modelo do Ollama a usar (ex: `"llama3"`).             |
| `ollama_base_url`   | URL do servidor Ollama (padrão `http://localhost:11434`). |
| `request_timeout`   | Timeout (segundos) das chamadas ao Ollama.            |
| `platforms_target`  | Plataformas alvo (usado como metadado).               |

`config.json` está no `.gitignore` porque pode conter dados sensíveis.

## Pipeline de vídeo

`agents/video_pipeline.py` define a sequência de montagem (imagem + narração →
clipe → concatenação) usando FFmpeg. Os geradores de **imagem** e de **voz**
são pontos de extensão (`hooks`) que você conecta às ferramentas de sua
escolha:

```python
from agents.video_pipeline import VideoPipeline, VideoJob, Scene

pipeline = VideoPipeline(
    image_generator=minha_funcao_de_imagem,  # (prompt, dest) -> Path
    voice_generator=minha_funcao_de_voz,      # (texto, dest) -> Path
)
job = VideoJob(title="meu_video", scenes=[Scene("Narração...", "Prompt visual...")])
pipeline.render(job)
```

Requer o **FFmpeg** instalado e disponível no `PATH`.

## Agente roteirista (cena-a-cena)

`agents/script_writer.py` transforma um tópico em alta num roteiro concreto:
uma lista de `Scene` (narração + prompt visual + duração) pronta para virar um
`VideoJob`. Ele conversa com o mesmo Ollama local; a conversão da resposta em
cenas (`build_scenes`) é pura e coberta por testes.

```python
from agents.script_writer import ScriptWriterAgent

agent = ScriptWriterAgent()
job = agent.build_video_job("Gatos Astronautas", num_scenes=5)  # -> VideoJob
# job.scenes já pode ser passado ao VideoPipeline.render(job)
```

## Geração de mídia e publicação (pré-configurado)

Os geradores de imagem/voz e o publisher são **plugáveis** e escolhidos por
config (`config.json`) ou variável de ambiente:

| Config | Opções | Padrão |
|---|---|---|
| `image_provider` / `ANE_IMAGE_PROVIDER` | `placeholder`, `stability` | `placeholder` |
| `voice_provider` / `ANE_VOICE_PROVIDER` | `placeholder`, `elevenlabs` | `placeholder` |
| `publisher` / `ANE_PUBLISHER` | `none`, `youtube` | `none` |

- **placeholder** usa só o FFmpeg (fundo colorido + áudio) — o vídeo renderiza
  **out of the box**, sem chave nenhuma.
- **stability / elevenlabs** exigem `STABILITY_API_KEY` / `ELEVENLABS_API_KEY`
  (ver `.env.example`).
- **youtube** é um stub pré-configurado (valida render + credenciais OAuth);
  falta completar a chamada de upload — ver `publishers/youtube.py`.

Renderizar uma ideia aprovada: botão **Renderizar vídeo** no frontend, ou
`POST /api/ideas/{id}/render` (o vídeo fica em `POST` → preview via
`GET /api/ideas/{id}/video`). Nada de automação de evasão — publicação só via
APIs oficiais.

## Testes

Os testes cobrem o parsing de JSON do Ollama e a montagem de cenas — tudo
**offline**, sem precisar do Ollama no ar:

```bash
pip install -r requirements-dev.txt
pytest
```
