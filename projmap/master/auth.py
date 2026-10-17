"""Token de pareamento (F6): protege a API quando o mestre fica exposto na LAN.

Regras:

- Sem token configurado (``token=None``) nada muda: é o modo só-local da F1.
- Com token, pedidos a ``/api/*`` e ``/media/*`` vindos **de fora desta
  máquina** precisam do token, no cabeçalho ``X-ProjMap-Token`` ou no parâmetro
  ``?token=`` (``<img>``/``<video>`` não mandam cabeçalho). Vale também para o
  WebSocket do sensor.
- Pedidos de loopback (o editor no próprio mestre, o celular via ``adb
  reverse``) passam direto.
- Os arquivos estáticos da UI são públicos: não contêm dados do projeto.

É um middleware ASGI puro (e não ``BaseHTTPMiddleware``) para cobrir também o
escopo ``websocket``.
"""

from __future__ import annotations

import hmac
import json
import secrets
from urllib.parse import parse_qs, urlparse

HEADER = "x-projmap-token"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "[::1]", "localhost", "testserver"}
PROTECTED_PREFIXES = ("/api/", "/media/")


def new_token() -> str:
    """Curto o bastante para digitar no celular, longo o bastante para a LAN."""
    return secrets.token_urlsafe(9)


def _header(scope, key: bytes) -> str | None:
    for name, value in scope.get("headers", []):
        if name.lower() == key:
            return value.decode("latin-1")
    return None


def _host_only(netloc: str) -> str:
    netloc = netloc.strip().lower()
    if netloc.startswith("["):
        end = netloc.find("]")
        return netloc[: end + 1] if end != -1 else netloc
    return netloc.split(":", 1)[0]


def is_loopback(scope) -> bool:
    client = scope.get("client")
    if not (bool(client) and client[0] in LOOPBACK):
        return False
    host = _header(scope, b"host")
    if host is not None and _host_only(host) not in LOOPBACK_HOSTS:
        return False
    origin = _header(scope, b"origin")
    if origin is not None:
        parsed = urlparse(origin)
        if _host_only(parsed.netloc) not in LOOPBACK_HOSTS:
            return False
    return True


def request_token(scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name.decode("latin-1").lower() == HEADER:
            return value.decode("latin-1")
    qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    vals = qs.get("token")
    return vals[0] if vals else None


def token_ok(scope, token: str) -> bool:
    given = request_token(scope)
    return given is not None and hmac.compare_digest(given.encode(), token.encode())


class PairingTokenMiddleware:
    def __init__(self, app, token: str | None):
        self.app = app
        self.token = token

    def _allowed(self, scope) -> bool:
        if not self.token or scope["type"] not in ("http", "websocket"):
            return True
        if not scope.get("path", "").startswith(PROTECTED_PREFIXES):
            return True
        return is_loopback(scope) or token_ok(scope, self.token)

    async def __call__(self, scope, receive, send):
        if self._allowed(scope):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await receive()  # websocket.connect
            await send({"type": "websocket.close", "code": 4401})
            return
        body = json.dumps({"detail": ["token de pareamento ausente ou inválido"]}).encode()
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
DEV_UI_PORT = 3100  # `npm run dev` do editor (projmap/ui/package.json)


def origin_allowed(scope) -> bool:
    """Requisição sem ``Origin`` (curl, apps) ou da mesma origem do mestre / do editor em dev.

    Bloqueia o que o CORS sozinho não bloqueia: POST "simples" (formulário,
    multipart) vindo de qualquer site aberto no navegador — ou do iframe sandbox
    de um motion, cuja origem é ``null``."""
    origin = _header(scope, b"origin")
    if origin is None:
        return True
    host = (_header(scope, b"host") or "").lower()
    parsed = urlparse(origin)
    if parsed.netloc.lower() == host and host:
        return True
    return parsed.scheme == "http" and _host_only(parsed.netloc) in LOOPBACK_HOSTS and \
        parsed.port == DEV_UI_PORT


class SameOriginWriteMiddleware:
    """Escritas em ``/api``/``/media`` e WebSockets só da própria origem (ou sem ``Origin``)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        guarded = (kind == "websocket") or (
            kind == "http" and scope.get("method", "GET").upper() in WRITE_METHODS
            and scope.get("path", "").startswith(PROTECTED_PREFIXES))
        if not guarded or origin_allowed(scope):
            await self.app(scope, receive, send)
            return
        if kind == "websocket":
            await receive()
            await send({"type": "websocket.close", "code": 4403})
            return
        body = json.dumps({"detail": ["origem não permitida"]}).encode()
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})
