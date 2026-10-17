"""Testes de geração de Motion Module v1 com Claude (Seção C.1, C.2 e C.6)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from projmap.ai.motion_generator import (
    SYSTEM_PROMPT_PATH,
    build_user_message,
    extract_motion_response,
    load_system_prompt,
)
from projmap.core.state import ProjectState
from projmap.core.store import ProjectStore
from projmap.master.app import create_app


class _FakeStreamContext:
    def __init__(self, chunks: list[str], usage: dict[str, int] | None = None) -> None:
        self._chunks = chunks
        self._usage = usage or {
            "input_tokens": 1200,
            "output_tokens": 800,
            "cache_creation_input_tokens": 1000,
            "cache_read_input_tokens": 200,
        }

    def __enter__(self) -> "_FakeStreamContext":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    @property
    def text_stream(self):
        for c in self._chunks:
            yield c

    def get_final_message(self) -> Any:
        return SimpleNamespace(usage=SimpleNamespace(**self._usage))


class _FakeAnthropicClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs: Any) -> _FakeStreamContext:
        self.calls.append(kwargs)
        text = self.responses.pop(0) if self.responses else ""
        mid = len(text) // 2
        return _FakeStreamContext([text[:mid], text[mid:]])


VALID_CLAUDE_RESPONSE = """<motion_html>
<!DOCTYPE html><html><head><script type="application/json" id="motion-manifest">
{"spec":"motion-module/1","id":"aneis-luz","name":"Anéis de Luz","version":"1.0.0","params":{}}
</script></head><body></body></html>
</motion_html>
<layer_preset>
{"motionId": "aneis-luz", "motionVersion": "1.0.0", "mode": "default", "params": {"framing": "element", "background": "transparent"}}
</layer_preset>
<notes>
Alvos: pulso (kick) e brilho (high).
</notes>"""


def test_system_prompt_salvo_e_completo():
    assert SYSTEM_PROMPT_PATH.is_file()
    text = load_system_prompt()
    assert "Motion Module v1" in text
    assert "# 6. SINAIS DE ÁUDIO" in text
    assert "# 7. REAÇÃO AO ÁUDIO" in text
    assert "<motion_html>" in text


def test_build_user_message_novo_editar_reparar():
    msg_new = build_user_message(
        "new",
        prompt="anéis de luz que explodem no kick",
        images=[{"media_type": "image/png", "data": "iVBORw0KGgo="}],
    )
    assert len(msg_new) == 2
    assert msg_new[0]["type"] == "image"
    assert msg_new[1] == {"type": "text", "text": "[NOVO] anéis de luz que explodem no kick"}

    msg_edit = build_user_message("edit", prompt="mude para azul", current_html="<html>v1</html>")
    assert msg_edit[0]["text"] == "[EDITAR] mude para azul\n<current_html>\n<html>v1</html>\n</current_html>"

    msg_rep = build_user_message("repair", errors=["spec inválido", "falta seed"], current_html="<html>bad</html>")
    assert "<errors>\nspec inválido\nfalta seed\n</errors>" in msg_rep[0]["text"]
    assert "<current_html>\n<html>bad</html>\n</current_html>" in msg_rep[0]["text"]


def test_extract_motion_response_valido_e_sem_layer_preset():
    ok_res = extract_motion_response(VALID_CLAUDE_RESPONSE)
    assert ok_res.ok is True
    assert "aneis-luz" in ok_res.html
    assert ok_res.layer_preset["params"]["background"] == "transparent"
    assert "Alvos:" in ok_res.notes

    missing_preset = extract_motion_response("<motion_html><html></html></motion_html><notes>ok</notes>")
    assert missing_preset.ok is False
    assert any("layer_preset" in e for e in missing_preset.errors)

    bad_json = extract_motion_response(
        "<motion_html><html></html></motion_html><layer_preset>{invalido}</layer_preset><notes>ok</notes>"
    )
    assert bad_json.ok is False
    assert any("JSON inválido" in e for e in bad_json.errors)


def test_api_motions_ai_config_nunca_expoe_chave_e_faz_streaming_sse(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Keyring falso em memória: o teste não pode depender (nem mexer) da chave real salva nesta máquina.
    import sys
    import types

    vault: dict[tuple[str, str], str] = {}
    fake_keyring = types.SimpleNamespace(
        get_password=lambda svc, user: vault.get((svc, user)),
        set_password=lambda svc, user, pw: vault.__setitem__((svc, user), pw),
        delete_password=lambda svc, user: vault.pop((svc, user), None),
    )
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)
    fake_client = _FakeAnthropicClient([VALID_CLAUDE_RESPONSE])
    store = ProjectStore.open_or_create(tmp_path / "show.projmap", "Show")
    app = create_app(
        ProjectState(store),
        config_dir=tmp_path / "cfg",
        ai_client_factory=lambda _key: fake_client,
    )
    client = TestClient(app)

    # Sem chave configurada -> configured=False
    r0 = client.get("/api/motions/ai/config")
    assert r0.status_code == 200
    assert r0.json() == {"configured": False, "model": "claude-opus-5-5"}

    # Configura chave e modelo -> resposta NUNCA contém api_key
    r1 = client.put("/api/motions/ai/config", json={"api_key": "sk-ant-secret-123", "model": "claude-opus-5-5"})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1 == {"configured": True, "model": "claude-opus-5-5"}
    assert "sk-ant" not in json.dumps(body1)

    # Faz pedido de geração SSE
    r_gen = client.post(
        "/api/motions/ai/generate",
        json={"kind": "new", "prompt": "anéis de luz que explodem no kick"},
    )
    assert r_gen.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in r_gen.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(e["type"] == "progress" for e in events)
    done = next(e for e in events if e["type"] == "done")
    assert done["ok"] is True
    assert done["layer_preset"]["motionId"] == "aneis-luz"
    assert done["usage"]["input_tokens"] == 1200
    assert done["usage"]["estimated_cost_usd"] > 0

    # Confere que o system prompt foi enviado com cache_control ephemeral e max_tokens=64000
    call = fake_client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["max_tokens"] == 64000
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
