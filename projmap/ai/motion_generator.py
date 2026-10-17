"""Gerador de Motion Module v1 via Claude (Anthropic Messages API com streaming e prompt caching).

Regras de segurança e arquitetura (Seção C):
- A chave ANTHROPIC_API_KEY fica exclusivamente no backend (variável de ambiente ou keyring do sistema).
- Nunca expõe a chave ao frontend.
- Usa o conteúdo de ``projmap/ai/motion_system_prompt.md`` com ``cache_control: {"type": "ephemeral"}``.
- Extrai ``<motion_html>``, ``<layer_preset>`` e ``<notes>`` e valida o JSON do preset.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, Optional

from ..config import config_dir
from ..core.store import _atomic_write_bytes

log = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "motion_system_prompt.md"
DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
MAX_TOKENS = 64000
KEYRING_SERVICE = "projmap"
KEYRING_USERNAME = "anthropic_api_key"

_HTML_RE = re.compile(r"<motion_html>\s*(.*?)\s*</motion_html>", re.S)
_PRESET_RE = re.compile(r"<layer_preset>\s*(.*?)\s*</layer_preset>", re.S)
_NOTES_RE = re.compile(r"<notes>\s*(.*?)\s*</notes>", re.S)


@dataclass
class ExtractedMotionResponse:
    ok: bool
    html: str = ""
    layer_preset: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    errors: list[str] = field(default_factory=list)


def load_system_prompt(path: Path = SYSTEM_PROMPT_PATH) -> str:
    return path.read_text(encoding="utf-8")


class MotionAiConfigStore:
    """Guarda o modelo configurado em disco e a chave da API no keyring do sistema
    (com fallback em memória caso o ambiente não tenha backend de keyring)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or (config_dir() / "motion-ai.json")
        self._memory_key: Optional[str] = None

    def get_model(self) -> str:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            model = str(data.get("model", "")).strip()
            return model or DEFAULT_CLAUDE_MODEL
        except (OSError, ValueError):
            return DEFAULT_CLAUDE_MODEL

    def set_model(self, model: str) -> str:
        clean = model.strip() or DEFAULT_CLAUDE_MODEL
        payload = json.dumps({"model": clean}, ensure_ascii=False, indent=2).encode("utf-8")
        _atomic_write_bytes(self.path, payload)
        return clean

    def get_api_key(self) -> Optional[str]:
        env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if env_key:
            return env_key
        try:
            import keyring  # type: ignore[import-not-found,unused-ignore]

            kr_key = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            if kr_key and kr_key.strip():
                return kr_key.strip()
        except Exception:  # noqa: BLE001
            pass
        return self._memory_key

    def set_api_key(self, api_key: str) -> None:
        clean = api_key.strip()
        if not clean:
            self._memory_key = None
            try:
                import keyring  # type: ignore[import-not-found,unused-ignore]

                keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
            except Exception:  # noqa: BLE001
                pass
            return
        self._memory_key = clean
        try:
            import keyring  # type: ignore[import-not-found,unused-ignore]

            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, clean)
        except Exception as exc:  # noqa: BLE001
            log.warning("keyring indisponível, mantendo chave apenas na sessão atual: %s", exc)

    def public_status(self) -> dict[str, Any]:
        """Status público para o frontend — NUNCA inclui a chave da API."""
        return {
            "configured": bool(self.get_api_key()),
            "model": self.get_model(),
        }


def build_user_message(
    kind: Literal["new", "edit", "repair"],
    prompt: str = "",
    current_html: str = "",
    errors: Optional[list[str]] = None,
    images: Optional[list[dict[str, str]]] = None,
) -> list[dict[str, Any]]:
    """Monta o array ``content`` do turno do usuário conforme a seção C.3 e seção 11 do system prompt."""
    blocks: list[dict[str, Any]] = []
    for img in (images or [])[:4]:
        data = str(img.get("data", "")).strip()
        media_type = str(img.get("media_type", "image/png")).strip() or "image/png"
        if data:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    },
                }
            )

    if kind == "new":
        text = f"[NOVO] {prompt.strip()}"
    elif kind == "edit":
        text = f"[EDITAR] {prompt.strip()}\n<current_html>\n{current_html}\n</current_html>"
    elif kind == "repair":
        err_text = "\n".join(errors or [])
        text = f"[REPARAR] <errors>\n{err_text}\n</errors>\n<current_html>\n{current_html}\n</current_html>"
    else:
        raise ValueError(f"tipo de pedido inválido: {kind}")

    blocks.append({"type": "text", "text": text})
    return blocks


def extract_motion_response(raw_text: str) -> ExtractedMotionResponse:
    """Extrai ``<motion_html>``, ``<layer_preset>`` e ``<notes>`` da resposta do Claude (C.2)."""
    errors: list[str] = []
    m_html = _HTML_RE.search(raw_text or "")
    m_preset = _PRESET_RE.search(raw_text or "")
    m_notes = _NOTES_RE.search(raw_text or "")

    if not m_html or not m_html.group(1).strip():
        errors.append("Marcação <motion_html>...</motion_html> ausente ou vazia na resposta.")
    if not m_preset or not m_preset.group(1).strip():
        errors.append("Marcação <layer_preset>...</layer_preset> ausente ou vazia na resposta.")
    if not m_notes or not m_notes.group(1).strip():
        errors.append("Marcação <notes>...</notes> ausente ou vazia na resposta.")

    preset_obj: dict[str, Any] = {}
    if m_preset and m_preset.group(1).strip():
        try:
            parsed = json.loads(m_preset.group(1).strip())
            if not isinstance(parsed, dict):
                errors.append("<layer_preset> deve conter um objeto JSON.")
            else:
                preset_obj = parsed
        except ValueError as exc:
            errors.append(f"JSON inválido em <layer_preset>: {exc}")

    if errors:
        return ExtractedMotionResponse(
            ok=False,
            html=m_html.group(1).strip() if m_html else "",
            layer_preset=preset_obj,
            notes=m_notes.group(1).strip() if m_notes else "",
            errors=errors,
        )

    assert m_html is not None and m_notes is not None
    return ExtractedMotionResponse(
        ok=True,
        html=m_html.group(1).strip(),
        layer_preset=preset_obj,
        notes=m_notes.group(1).strip(),
        errors=[],
    )


def detect_current_section(accumulated_text: str) -> str:
    """Identifica se o streaming está atualmente gerando o HTML, o preset ou as notas."""
    if "<notes>" in accumulated_text and "</notes>" not in accumulated_text:
        return "notes"
    if "<layer_preset>" in accumulated_text and "</layer_preset>" not in accumulated_text:
        return "preset"
    if "<motion_html>" in accumulated_text and "</motion_html>" not in accumulated_text:
        return "html"
    return "waiting"


def estimate_cost_usd(usage: dict[str, int]) -> float:
    """Custo estimado em USD (referência Opus: $15/M input, $75/M output, $18.75/M cache write, $1.50/M cache read)."""
    inp = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    cw = int(usage.get("cache_creation_input_tokens", 0) or 0)
    cr = int(usage.get("cache_read_input_tokens", 0) or 0)
    cost = (inp * 15.0 + out * 75.0 + cw * 18.75 + cr * 1.50) / 1_000_000.0
    return round(cost, 4)


def default_anthropic_client_factory(api_key: str) -> Any:
    import anthropic  # type: ignore[import-not-found,unused-ignore]

    return anthropic.Anthropic(api_key=api_key)


def stream_motion_generation(
    *,
    kind: Literal["new", "edit", "repair"],
    prompt: str = "",
    current_html: str = "",
    errors: Optional[list[str]] = None,
    images: Optional[list[dict[str, str]]] = None,
    model: str = DEFAULT_CLAUDE_MODEL,
    api_key: str,
    client_factory: Optional[Callable[[str], Any]] = None,
) -> Iterator[dict[str, Any]]:
    """Executa a chamada em streaming à Messages API da Anthropic e emite eventos de progresso e resultado."""
    factory = client_factory or default_anthropic_client_factory
    client = factory(api_key)
    sys_prompt = load_system_prompt()
    user_content = build_user_message(kind, prompt=prompt, current_html=current_html, errors=errors, images=images)

    t0 = time.monotonic()
    chunks: list[str] = []
    approx_tokens = 0
    usage_dict: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "estimated_cost_usd": 0.0,
    }

    with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": sys_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        for text_chunk in stream.text_stream:
            if not text_chunk:
                continue
            chunks.append(text_chunk)
            approx_tokens += max(1, len(text_chunk) // 4)
            full_so_far = "".join(chunks)
            yield {
                "type": "progress",
                "elapsed_s": round(time.monotonic() - t0, 2),
                "tokens_received": approx_tokens,
                "section": detect_current_section(full_so_far),
            }

        try:
            final_msg = stream.get_final_message()
            u = getattr(final_msg, "usage", None)
            if u is not None:
                usage_dict["input_tokens"] = int(getattr(u, "input_tokens", 0) or 0)
                usage_dict["output_tokens"] = int(getattr(u, "output_tokens", approx_tokens) or approx_tokens)
                usage_dict["cache_creation_input_tokens"] = int(
                    getattr(u, "cache_creation_input_tokens", 0) or 0
                )
                usage_dict["cache_read_input_tokens"] = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        except Exception:  # noqa: BLE001
            usage_dict["output_tokens"] = approx_tokens

    usage_dict["estimated_cost_usd"] = estimate_cost_usd(usage_dict)
    full_text = "".join(chunks)
    extracted = extract_motion_response(full_text)

    yield {
        "type": "done",
        "ok": extracted.ok,
        "html": extracted.html,
        "layer_preset": extracted.layer_preset,
        "notes": extracted.notes,
        "errors": extracted.errors,
        "usage": usage_dict,
        "elapsed_s": round(time.monotonic() - t0, 2),
    }
