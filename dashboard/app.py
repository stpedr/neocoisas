"""Painel de Controle do Criador (Streamlit).

Interface para definir o nicho ativo e disparar a geração de estratégia de
conteúdo com IA local (Ollama + GPU).

Execução:
    streamlit run dashboard/app.py
"""

import json
import os
import sys

import streamlit as st

# Permite importar o pacote `agents` a partir da raiz do projeto.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.niche_creator import LocalNicheAgent, OllamaError  # noqa: E402

CONFIG_FILE = os.path.join(
    os.path.dirname(__file__), "..", "config.json"
)

st.set_page_config(page_title="Auto Niche Engine - Painel do Criador", layout="wide")

st.title("🤖 Painel de Controle: Motor de Nichos Automatizados")
st.sidebar.header("Configurações do Sistema")


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"active_niche": "LoLzeiros", "ollama_model": "llama3"}


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)


config = load_config()

st.sidebar.subheader("Perfil Ativo")
creator_name = st.sidebar.text_input("Nome do Criador", value=config.get("creator_name", "Admin"))
selected_niche = st.sidebar.text_input(
    "Definir Novo Nicho", value=config.get("active_niche", "")
)

if st.sidebar.button("Atualizar Nicho Base"):
    config["creator_name"] = creator_name
    config["active_niche"] = selected_niche
    save_config(config)
    st.sidebar.success("Nicho atualizado com sucesso!")

col1, col2 = st.columns(2)

with col1:
    st.header("🎯 Estratégia de Nicho (via Ollama + GPU)")
    if st.button("Gerar Estratégia e Ideias com IA Local"):
        with st.spinner("Processando na sua GPU local via Ollama..."):
            try:
                agent = LocalNicheAgent(config_path=CONFIG_FILE)
                strategy = agent.setup_niche_campaign(selected_niche)
                st.session_state["strategy"] = strategy
                st.success("Estratégia gerada!")
            except (OllamaError, FileNotFoundError) as exc:
                st.error(str(exc))

    if "strategy" in st.session_state:
        st.json(st.session_state["strategy"])

with col2:
    st.header("🚀 Execução & Automação de Posts")
    st.info(
        "Conecte os geradores de mídia/voz e o renderizador (FFmpeg) para "
        "produzir os vídeos a partir da estratégia gerada."
    )
    if st.button("Iniciar Pipeline de Renderização"):
        st.warning(
            "O pipeline iniciará a renderização dos clipes a partir do roteiro. "
            "(Conecte os geradores de mídia em agents/video_pipeline.py)"
        )
