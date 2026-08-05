"""Provedores locais via ComfyUI (imagem e text-to-video), grátis/offline.

O ComfyUI executa *workflows* (grafos de nós) próprios dos modelos que você tem
instalados. Em vez de embutir um grafo fixo, este provider usa um **template de
workflow** que você exporta do ComfyUI em **formato API** ("Save (API Format)"),
contendo o marcador `%prompt%` no campo de texto do prompt. O provider injeta o
prompt, submete via API (`/prompt`), aguarda (`/history`) e baixa a saída
(`/view`).

Config:
    COMFYUI_URL             (padrão http://host.docker.internal:8188)
    COMFYUI_IMAGE_WORKFLOW  caminho do JSON (formato API) para imagem
    COMFYUI_VIDEO_WORKFLOW  caminho do JSON (formato API) para text-to-video

`inject_prompt` e `find_output_files` são puros e cobertos por testes.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import requests

_POLL_TIMEOUT = int(os.environ.get("COMFYUI_TIMEOUT", "900"))


def _base_url() -> str:
    return os.environ.get("COMFYUI_URL", "http://host.docker.internal:8188").rstrip("/")


def inject_prompt(workflow_text: str, prompt: str) -> dict:
    """Substitui `%prompt%` no template pelo prompt (escapado) e faz o parse."""
    escaped = json.dumps(prompt)[1:-1]  # conteúdo sem as aspas externas
    return json.loads(workflow_text.replace("%prompt%", escaped))


def find_output_files(history_entry: dict) -> list[dict]:
    """Extrai os arquivos de saída (imagens/gifs/vídeos) do histórico do ComfyUI."""
    arquivos: list[dict] = []
    outputs = (history_entry or {}).get("outputs", {})
    for node in outputs.values():
        for chave in ("images", "gifs", "videos"):
            for item in node.get(chave, []) or []:
                if item.get("filename"):
                    arquivos.append(item)
    return arquivos


def _load_workflow(env_var: str, kind: str, prompt: str) -> dict:
    path = os.environ.get(env_var)
    if not path:
        raise RuntimeError(
            f"Defina {env_var} com o caminho do workflow (formato API) de {kind} "
            "do ComfyUI, contendo o marcador %prompt%."
        )
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"Workflow do ComfyUI não encontrado: {path}")
    return inject_prompt(p.read_text(encoding="utf-8"), prompt)


def _run(workflow: dict) -> list[dict]:
    base = _base_url()
    client_id = uuid.uuid4().hex
    try:
        r = requests.post(f"{base}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=30)
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"Não foi possível falar com o ComfyUI em {base}. Ele está rodando?"
        ) from exc
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI recusou o workflow ({r.status_code}): {r.text[:200]}")
    prompt_id = r.json().get("prompt_id")
    if not prompt_id:
        raise RuntimeError("ComfyUI não devolveu prompt_id.")

    # Polling do histórico até a execução concluir.
    deadline = time.time() + _POLL_TIMEOUT
    while time.time() < deadline:
        h = requests.get(f"{base}/history/{prompt_id}", timeout=30)
        if h.status_code == 200 and prompt_id in h.json():
            arquivos = find_output_files(h.json()[prompt_id])
            if arquivos:
                return arquivos
        time.sleep(2)
    raise RuntimeError("ComfyUI: tempo esgotado aguardando a saída.")


def _download(fileinfo: dict, dest: Path) -> Path:
    base = _base_url()
    params = {
        "filename": fileinfo["filename"],
        "subfolder": fileinfo.get("subfolder", ""),
        "type": fileinfo.get("type", "output"),
    }
    r = requests.get(f"{base}/view", params=params, timeout=120)
    r.raise_for_status()
    dest = Path(dest)
    origem_ext = Path(fileinfo["filename"]).suffix.lower()
    if dest.suffix.lower() == origem_ext or not origem_ext:
        dest.write_bytes(r.content)
        return dest
    # Formatos diferentes (ex.: saída .webm/.gif → queremos .mp4): converte.
    tmp = dest.with_suffix(origem_ext)
    tmp.write_bytes(r.content)
    subprocess.run(["ffmpeg", "-y", "-i", str(tmp), str(dest)], check=True, capture_output=True)
    tmp.unlink(missing_ok=True)
    return dest


def comfyui_image(visual_prompt: str, dest: Path) -> Path:
    """Gera imagem via ComfyUI (workflow de COMFYUI_IMAGE_WORKFLOW)."""
    workflow = _load_workflow("COMFYUI_IMAGE_WORKFLOW", "imagem", visual_prompt)
    arquivos = _run(workflow)
    return _download(arquivos[0], Path(dest))


def comfyui_video(visual_prompt: str, dest: Path) -> Path:
    """Gera um clipe de vídeo via ComfyUI (workflow de COMFYUI_VIDEO_WORKFLOW)."""
    workflow = _load_workflow("COMFYUI_VIDEO_WORKFLOW", "vídeo", visual_prompt)
    arquivos = _run(workflow)
    return _download(arquivos[-1], Path(dest))  # último = vídeo combinado (VHS)
