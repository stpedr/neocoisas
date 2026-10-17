"""Servidor MCP do ProjMap: deixa um agente (Claude Code, Claude Desktop…) operar o show.

O que dá para fazer pelas ferramentas:

- ver o projeto, as entradas de vídeo (câmeras/placas de captura) e de áudio;
- escolher a entrada de áudio e ler os níveis ao vivo (graves/médios/agudos/batida);
- criar superfícies, mapear em tela cheia, trocar a fonte (ex.: entrada de vídeo);
- aplicar efeitos reativos ao áudio em cima de qualquer fonte;
- blackout/dimmer/padrões e **ver a saída** (snapshot PNG do que está na parede).

Ele só fala com a API do mestre já rodando (``PROJMAP_URL``, padrão
``http://127.0.0.1:8100``; ``PROJMAP_TOKEN`` se o mestre estiver exposto na LAN).

Uso (stdio)::

    python -m projmap.mcp_server
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .. import __version__
from .client import ProjMapClient, ProjMapError

SourceKindArg = Literal["capture", "video", "image", "gif", "color", "test", "interactive", "none"]
FxTypeArg = Literal["pulse", "hue", "zoom", "rgb_split", "strobe", "shake", "invert"]
BandArg = Literal["bass", "mid", "high", "level", "beat"]
PatternArg = Literal["none", "white", "grid", "edges", "black"]

INSTRUCTIONS = """\
ProjMap = projeção mapeada. Um projeto tem nós (projetores, com resolução de saída) e superfícies
(quads mapeados na saída, cada um com uma fonte e efeitos). Fluxo típico para "vídeo ao vivo reagindo
à música em tela cheia": list_inputs → set_audio_input → create_surface(fullscreen, source_kind="capture",
device=...) → set_surface_fx([...]) → audio_levels / snapshot_output para conferir.
Efeitos: pulse (brilho), hue (gira as cores), zoom, rgb_split, strobe (flash; use band="beat"),
shake (tremor), invert. Bandas: bass, mid, high, level, beat (envelope de batida).
"""


class FxSpec(BaseModel):
    """Um efeito reativo ao áudio."""

    type: FxTypeArg
    band: BandArg = "bass"
    amount: float = Field(0.5, ge=0.0, le=1.0, description="intensidade 0..1")
    enabled: bool = True


T = TypeVar("T")


def _guard(fn: Callable[..., T]) -> Callable[..., T]:
    """Erros da API viram ``ToolError`` com a mensagem do mestre (o modelo lê e corrige)."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return fn(*args, **kwargs)
        except ProjMapError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def _summary(project: dict[str, Any]) -> dict[str, Any]:
    media = project.get("media", {})
    return {
        "name": project["name"],
        "audio": project.get("audio"),
        "nodes": [{"id": n["id"], "name": n["name"], "width": n["output"]["width"], "height": n["output"]["height"],
                   "blackout": n["output"]["blackout"], "pattern": n["output"]["pattern"]} for n in project["nodes"]],
        "surfaces": [{"id": s["id"], "label": s["label"], "node_id": s["node_id"], "visible": s["visible"],
                      "quad": s["warp"]["base"], "source": {k: v for k, v in s["source"].items() if v is not None},
                      "fx": s.get("fx", [])} for s in project["surfaces"]],
        "media": [{"sha256": m["sha256"], "filename": m["filename"], "kind": m["kind"]} for m in media.values()],
    }


def build_server(client: ProjMapClient) -> MCPServer:
    server = MCPServer(name="projmap", title="ProjMap", version=__version__, instructions=INSTRUCTIONS)

    @server.tool(description="Estado do mestre e resumo do projeto: projetores, superfícies (quad, fonte, fx), "
                             "mídias e entrada de áudio.")
    @_guard
    def status() -> dict[str, Any]:
        return {"master": client.base_url, **client.health(), "project": _summary(client.project())}

    @server.tool(description="Entradas disponíveis neste PC: câmeras/placas de captura (video), dispositivos de "
                             "áudio (audio), capturas abertas e o barramento de áudio.")
    @_guard
    def list_inputs() -> dict[str, Any]:
        return client.inputs()

    @server.tool(description="Níveis ao vivo da entrada de áudio (0..1): bass, mid, high, level, beat; "
                             "contador de batidas e as capturas de vídeo abertas (fps, erro).")
    @_guard
    def audio_levels() -> dict[str, Any]:
        return client.audio_levels()

    @server.tool(description="Escolhe a entrada de áudio dos efeitos: 'loopback' (o que toca no PC), 'mic' "
                             "(microfone padrão) ou parte do nome de um dispositivo; gain 0..8.")
    @_guard
    def set_audio_input(device: str = "loopback", gain: Optional[float] = None) -> dict[str, Any]:
        return client.set_audio(device=device, gain=gain)

    @server.tool(description="Cria uma superfície no projetor (padrão: o primeiro). fullscreen=True mapeia a saída "
                             "inteira. source_kind='capture' usa a entrada de vídeo 'device' ('auto', índice ou "
                             "parte do nome). Devolve o id criado.")
    @_guard
    def create_surface(label: str = "", node_id: Optional[str] = None, fullscreen: bool = True,
                       source_kind: SourceKindArg = "test", device: Optional[str] = None,
                       media: Optional[str] = None) -> dict[str, Any]:
        node = node_id or client.default_node()
        source: dict[str, Any] = {"kind": source_kind}
        if device is not None:
            source["device"] = device
        if media is not None:
            source["media"] = media
        sid = client.create_surface(node, label=label, fullscreen=fullscreen, source=source)
        return {"surface_id": sid, "node_id": node}

    @server.tool(description="Mapeia a superfície na saída inteira do projetor dela (tela cheia).")
    @_guard
    def map_fullscreen(surface_id: str) -> dict[str, Any]:
        surf = client.fullscreen(surface_id)
        return {"surface_id": surface_id, "quad": surf["warp"]["base"]}

    @server.tool(description="Troca a fonte da superfície. kind='capture' + device para vídeo ao vivo; "
                             "video/image/gif exigem media (sha256 de list em status); color usa rgb.")
    @_guard
    def set_surface_source(surface_id: str, kind: SourceKindArg, device: Optional[str] = None,
                           media: Optional[str] = None, rgb: Optional[list[int]] = None,
                           fit: Optional[Literal["stretch", "cover", "contain"]] = None,
                           visible: Optional[bool] = None) -> dict[str, Any]:
        source: dict[str, Any] = {"kind": kind, "device": device, "media": media}
        if rgb is not None:
            source["color"] = rgb
        if fit is not None:
            source["fit"] = fit
        surf = client.patch_surface(surface_id, source=source, visible=visible)
        return {"surface_id": surface_id, "source": surf["source"], "visible": surf["visible"]}

    @server.tool(description="Define os efeitos reativos ao áudio da superfície (substitui a lista; [] remove). "
                             "Ex.: [{type:'strobe', band:'beat', amount:0.8}, {type:'pulse', band:'bass', "
                             "amount:0.6}]. Até 8.")
    @_guard
    def set_surface_fx(surface_id: str, fx: list[FxSpec]) -> dict[str, Any]:
        surf = client.patch_surface(surface_id, fx=[f.model_dump() for f in fx])
        return {"surface_id": surface_id, "fx": surf["fx"]}

    @server.tool(description="Saída do projetor: blackout, intensity (0..1), pattern (none/white/grid/edges/black), "
                             "show_outlines.")
    @_guard
    def set_output(node_id: Optional[str] = None, blackout: Optional[bool] = None,
                   intensity: Optional[float] = None, pattern: Optional[PatternArg] = None,
                   show_outlines: Optional[bool] = None) -> dict[str, Any]:
        node = node_id or client.default_node()
        return client.patch_output(node, blackout=blackout, intensity=intensity, pattern=pattern,
                                   show_outlines=show_outlines)

    @server.tool(description="Snapshot PNG do que a janela do projetor está mostrando agora (com efeitos).")
    @_guard
    def snapshot_output(node_id: Optional[str] = None, max_width: int = 640) -> Image:
        node = node_id or client.default_node()
        return Image(data=client.snapshot(node, max_width=max(16, min(max_width, 1920))), format="png")

    return server


def main() -> None:
    import logging

    from ..config import load_projmap_env

    logging.getLogger("httpx").setLevel(logging.WARNING)  # uma linha por chamada polui o stderr do cliente MCP
    load_projmap_env()  # PROJMAP_URL / PROJMAP_TOKEN podem vir do .env
    build_server(ProjMapClient()).run()  # stdio


if __name__ == "__main__":
    main()
