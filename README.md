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
   Agente Roteirista/Estrategista  (Ollama, GPU local)
              │
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
├── agents/
│   ├── __init__.py
│   ├── niche_creator.py      # Agente de estratégia de nicho (Ollama)
│   └── video_pipeline.py     # Pipeline de geração de vídeo (esqueleto)
└── dashboard/
    └── app.py                # Painel do Criador (Streamlit)
```

## Como executar localmente

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
   python main.py                      # usa o nicho de config.json
   python main.py "Gatos Astronautas"  # sobrescreve o nicho pontualmente
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
