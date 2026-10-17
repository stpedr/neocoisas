"""Cliente HTTP fino da API do mestre, usado pelas ferramentas do MCP.

Só fala HTTP com o mestre que já está rodando (``python -m projmap.master``):
o MCP não abre câmera, áudio nem janela por conta própria, então pode ser
ligado/desligado à vontade sem mexer no show. Toda validação continua no
mestre (pydantic); aqui só traduzimos erros em mensagens legíveis.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

DEFAULT_URL = "http://127.0.0.1:8100"


class ProjMapError(RuntimeError):
    """Erro da API do mestre (status + mensagens de validação)."""


def _detail(resp: httpx.Response) -> str:
    try:
        detail = resp.json().get("detail")
    except ValueError:
        return resp.text[:300] or resp.reason_phrase
    if isinstance(detail, list):
        return "; ".join(str(d) for d in detail)
    return str(detail)


class ProjMapClient:
    def __init__(self, url: Optional[str] = None, token: Optional[str] = None,
                 http: Optional[httpx.Client] = None, timeout: float = 15.0):
        """``url``/``token``: padrão ``PROJMAP_URL`` / ``PROJMAP_TOKEN`` do ambiente
        (o token nunca vem por linha de comando). ``http``: cliente pronto (testes)."""
        base = (url or os.environ.get("PROJMAP_URL") or DEFAULT_URL).rstrip("/")
        token = token if token is not None else os.environ.get("PROJMAP_TOKEN")
        headers = {"X-ProjMap-Token": token} if token else {}
        self._http = http or httpx.Client(base_url=base, headers=headers, timeout=timeout)
        self.base_url = base

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------- baixo nível
    def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            resp = self._http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise ProjMapError(f"mestre do ProjMap inacessível em {self.base_url} ({exc}). "
                               "Ele está rodando? python -m projmap.master --project <show>") from exc
        if resp.status_code >= 400:
            raise ProjMapError(f"{method} {path}: HTTP {resp.status_code}: {_detail(resp)}")
        return resp

    def _json(self, method: str, path: str, **kw: Any) -> Any:
        return self._request(method, path, **kw).json()

    # ------------------------------------------------------------------ leitura
    def health(self) -> dict[str, Any]:
        return self._json("GET", "/api/health")

    def project(self) -> dict[str, Any]:
        return self._json("GET", "/api/project")["project"]

    def inputs(self) -> dict[str, Any]:
        return self._json("GET", "/api/inputs")

    def audio_levels(self) -> dict[str, Any]:
        return self._json("GET", "/api/inputs/audio")

    def snapshot(self, node_id: str, max_width: int = 640) -> bytes:
        return self._request("GET", f"/api/nodes/{node_id}/snapshot", params={"max_width": max_width}).content

    def default_node(self) -> str:
        nodes = self.project()["nodes"]
        if not nodes:
            raise ProjMapError("o projeto não tem nenhum projetor (nó)")
        return nodes[0]["id"]

    def motion_host(self) -> dict[str, Any]:
        return self._json("GET", "/api/motions/host")

    # ------------------------------------------------------------------ escrita
    def upload_media(self, path: str) -> dict[str, Any]:
        """Envia um arquivo local (vídeo, GIF, imagem ou motion .html) para o projeto."""
        from pathlib import Path

        f = Path(path).expanduser()
        if not f.is_file():
            raise ProjMapError(f"arquivo não encontrado: {f}")
        with f.open("rb") as fh:
            return self._json("POST", "/api/media", files={"file": (f.name, fh)})["item"]

    def set_audio(self, device: Optional[str] = None, gain: Optional[float] = None) -> dict[str, Any]:
        body = {k: v for k, v in {"device": device, "gain": gain}.items() if v is not None}
        return self._json("PATCH", "/api/audio", json=body)["project"]["audio"]

    def create_surface(self, node_id: str, label: str = "", fullscreen: bool = True,
                       source: Optional[dict[str, Any]] = None) -> str:
        body: dict[str, Any] = {"node_id": node_id, "label": label, "fullscreen": fullscreen}
        if source is not None:
            body["source"] = source
        return self._json("POST", "/api/surfaces", json=body)["surface_id"]

    def fullscreen(self, surface_id: str) -> dict[str, Any]:
        return self._surface_of(self._json("POST", f"/api/surfaces/{surface_id}/fullscreen"), surface_id)

    def patch_surface(self, surface_id: str, **changes: Any) -> dict[str, Any]:
        body = {k: v for k, v in changes.items() if v is not None}
        return self._surface_of(self._json("PATCH", f"/api/surfaces/{surface_id}", json=body), surface_id)

    def patch_output(self, node_id: str, **changes: Any) -> dict[str, Any]:
        body = {k: v for k, v in changes.items() if v is not None}
        payload = self._json("PATCH", f"/api/nodes/{node_id}/output", json=body)
        return next(n["output"] for n in payload["project"]["nodes"] if n["id"] == node_id)

    @staticmethod
    def _surface_of(payload: dict[str, Any], surface_id: str) -> dict[str, Any]:
        return next(s for s in payload["project"]["surfaces"] if s["id"] == surface_id)
