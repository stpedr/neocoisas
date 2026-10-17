"""Testes de Caracterização (FASE 3 — Rede de Segurança do ProjMap Standalone).

Estes testes travam o comportamento ponta-a-ponta dos 5 fluxos operacionais mais
críticos do ProjMap antes de qualquer refatoração estrutural da Fase 4:

1. Ciclo completo de edição de show, detecção, camadas (F9) e pacote ``.pmz``.
2. Pareamento, fronteira de autenticação Loopback vs. LAN e operação de palco (Looks).
3. Camada interativa, NLP standalone (sem ``agents.llm``) e WebSocket do celular-sensor.
4. Biblioteca local de mídia, motor de sugestões por proporção e presets de cor.
5. Pipeline de renderização OpenGL (``Renderer.sync`` / ``render_offscreen``) e fallback de mídia.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from projmap.core.project import Layer, Project, SourceSpec, Surface, Warp
from projmap.core.state import ProjectState
from projmap.core.store import ProjectStore
from projmap.interact.nlp import TextClient
from projmap.interact.runtime import InteractionRuntime
from projmap.interact.scene import PRESETS
from projmap.master.app import create_app
from projmap.node.renderer import Renderer, render_offscreen


def _make_scene_photo_bytes(w: int = 640, h: int = 360) -> bytes:
    """Gera uma foto sintética com um quadro retangular claro sobre fundo escuro."""
    img = np.full((h, w, 3), 20, dtype=np.uint8)
    cv2.rectangle(img, (140, 70), (500, 290), (235, 235, 235), -1)
    cv2.rectangle(img, (140, 70), (500, 290), (255, 255, 255), 3)
    ok, enc = cv2.imencode(".jpg", img)
    assert ok
    return enc.tobytes()


def _make_png_bytes(w: int = 320, h: int = 180, bgr: tuple[int, int, int] = (40, 180, 240)) -> bytes:
    img = np.full((h, w, 3), bgr, dtype=np.uint8)
    ok, enc = cv2.imencode(".png", img)
    assert ok
    return enc.tobytes()


# ---------------------------------------------------------------------------
# Fluxo 1: Edição completa do show, foto, detect, mídia, camadas F9 e .pmz
# ---------------------------------------------------------------------------
def test_characterization_flow_1_show_editing_layers_and_pmz(tmp_path: Path) -> None:
    store = ProjectStore.create(tmp_path / "show", name="Show Teatro Amazonas")
    state = ProjectState(store)
    app = create_app(
        state,
        library_roots=[],
        save_library_config=False,
        config_dir=tmp_path / "cfg",
    )
    client = TestClient(app)

    # 1. Upload da foto da posição do projetor
    photo_bytes = _make_scene_photo_bytes()
    r_photo = client.post(
        "/api/nodes/proj-1/photo",
        files={"file": ("palco.jpg", photo_bytes, "image/jpeg")},
    )
    assert r_photo.status_code == 200
    assert r_photo.json()["project"]["nodes"][0]["photo"] is not None

    # 2. Detecção clássica de superfícies candidatas a partir da foto
    r_det = client.post(
        "/api/nodes/proj-1/detect",
        json={"detector": "classic", "sensitivity": 0.6, "max_candidates": 8},
    )
    assert r_det.status_code == 200
    det_payload = r_det.json()
    assert det_payload["detector"] == "classic"
    assert len(det_payload["candidates"]) >= 1
    first_quad_norm = det_payload["candidates"][0]["quad"]
    assert len(first_quad_norm) == 4
    first_quad = [[pt[0] * 1920.0, pt[1] * 1080.0] for pt in first_quad_norm]

    # 3. Upload de duas mídias para o projeto
    png_bg = _make_png_bytes(320, 180, (20, 120, 220))
    png_fg = _make_png_bytes(160, 160, (220, 40, 180))
    r_m1 = client.post("/api/media", files={"file": ("fundo.png", png_bg, "image/png")})
    r_m2 = client.post("/api/media", files={"file": ("logo.png", png_fg, "image/png")})
    assert r_m1.status_code == 200
    assert r_m2.status_code == 200
    sha_bg = r_m1.json()["item"]["sha256"]
    sha_fg = r_m2.json()["item"]["sha256"]

    # 4. Atualização do documento completo com superfície + 2 camadas (F9)
    proj = client.get("/api/project").json()["project"]
    proj["surfaces"] = [
        {
            "id": "painel-central",
            "label": "Painel Central",
            "node_id": "proj-1",
            "z": 10,
            "visible": True,
            "opacity": 0.9,
            "blend_mode": "normal",
            "feather": 0.05,
            "polygon_src": first_quad_norm,
            "warp": {"type": "homography", "base": first_quad},
            "source": {"kind": "image", "media": sha_bg, "fit": "cover"},
            "layers": [
                {
                    "id": "camada-logo",
                    "label": "Logo Topo",
                    "visible": True,
                    "opacity": 0.85,
                    "rect": [0.1, 0.1, 0.4, 0.4],
                    "source": {"kind": "image", "media": sha_fg, "fit": "contain"},
                },
                {
                    "id": "camada-oculta",
                    "label": "Texto Reserva",
                    "visible": False,
                    "opacity": 1.0,
                    "rect": [0.0, 0.7, 1.0, 0.3],
                    "source": {"kind": "color", "color": [255, 255, 255]},
                },
            ],
        }
    ]
    r_put = client.put("/api/project", json={"project": proj})
    assert r_put.status_code == 200

    # Verifica que project.json foi persistido em disco com as camadas intactas
    saved_disk = json.loads((store.root / "project.json").read_text(encoding="utf-8"))
    assert saved_disk["surfaces"][0]["id"] == "painel-central"
    assert [ly["id"] for ly in saved_disk["surfaces"][0]["layers"]] == ["camada-logo", "camada-oculta"]

    # 5. Exportação .pmz e reimportação limpa em outro diretório
    r_exp = client.get("/api/project/export")
    assert r_exp.status_code == 200
    pmz_file = tmp_path / "exportado.pmz"
    pmz_file.write_bytes(r_exp.content)
    assert zipfile.is_zipfile(pmz_file)

    restored_store = ProjectStore.import_pmz(pmz_file, tmp_path / "restored")
    restored_proj = restored_store.load()
    assert restored_proj.name == "Show Teatro Amazonas"
    assert set(restored_proj.media.keys()) == {sha_bg, sha_fg}
    assert len(restored_proj.surfaces) == 1
    assert len(restored_proj.surfaces[0].layers) == 2


# ---------------------------------------------------------------------------
# Fluxo 2: Pareamento, fronteira Loopback vs. LAN e Operação de Palco (Looks)
# ---------------------------------------------------------------------------
def test_characterization_flow_2_pairing_lan_auth_and_stage_looks(tmp_path: Path) -> None:
    store = ProjectStore.create(tmp_path / "stage", name="Show Palco")
    state = ProjectState(store)
    state.update(
        lambda p: p.model_copy(
            update={
                "surfaces": [
                    Surface(
                        id="ciclorama",
                        label="Ciclorama",
                        node_id="proj-1",
                        visible=True,
                        opacity=1.0,
                        warp=Warp(base=[(0.0, 0.0), (1920.0, 0.0), (1920.0, 1080.0), (0.0, 1080.0)]),
                        source=SourceSpec(kind="color", color=(20, 80, 200)),
                    )
                ]
            }
        )
    )
    secret_token = "tok-ensaio-2026"
    app = create_app(
        state,
        token=secret_token,
        host="0.0.0.0",
        port=8100,
        library_roots=[],
        save_library_config=False,
        config_dir=tmp_path / "cfg",
    )

    local_client = TestClient(app, client=("127.0.0.1", 51000))
    lan_unauth = TestClient(app, client=("192.168.15.42", 52000))
    lan_auth = TestClient(
        app,
        client=("192.168.15.42", 52001),
        headers={"X-ProjMap-Token": secret_token},
    )

    # 1. Operador local obtém dados de pareamento (QR SVG + URLs com token)
    r_pair = local_client.get("/api/remote/pair")
    assert r_pair.status_code == 200
    pair_data = r_pair.json()
    assert pair_data["token"] == secret_token
    assert "<svg" in pair_data["qr_svg"]
    assert f"#t={secret_token}" in pair_data["url"]

    # 2. Cliente na LAN sem token recebe 401 em /api/* (mas a raiz estática / é pública)
    assert lan_unauth.get("/").status_code == 200
    assert lan_unauth.get("/api/project").status_code == 401
    assert lan_unauth.patch("/api/nodes/proj-1/output", json={"blackout": True}).status_code == 401
    # E nunca pode ler /api/remote/pair da LAN
    assert lan_auth.get("/api/remote/pair").status_code == 403

    # 3. Celular pareado na LAN salva Look 1 ("Abertura"), muda palco para intervalo e dá recall
    r_look1 = lan_auth.post("/api/looks", json={"name": "Abertura"})
    assert r_look1.status_code == 200
    look_abertura_id = r_look1.json()["project"]["looks"][-1]["id"]

    # Operador no celular baixa dimmer para 0.25, ativa blackout e esconde superfície
    assert lan_auth.patch("/api/nodes/proj-1/output", json={"intensity": 0.25, "blackout": True}).status_code == 200
    assert lan_auth.patch("/api/surfaces/ciclorama", json={"visible": False, "opacity": 0.4}).status_code == 200

    snap_mid = lan_auth.get("/api/project").json()["project"]
    assert snap_mid["nodes"][0]["output"]["blackout"] is True
    assert snap_mid["nodes"][0]["output"]["intensity"] == 0.25
    assert snap_mid["surfaces"][0]["visible"] is False

    # Recall do Look "Abertura" restaura estado das superfícies da cena salva
    r_recall = lan_auth.post(f"/api/looks/{look_abertura_id}/recall")
    assert r_recall.status_code == 200
    restored = r_recall.json()["project"]
    assert restored["surfaces"][0]["visible"] is True
    assert restored["surfaces"][0]["opacity"] == 1.0


# ---------------------------------------------------------------------------
# Fluxo 3: Camada Interativa, NLP Standalone e WebSocket do Celular-Sensor
# ---------------------------------------------------------------------------
class _StubStandaloneLLM(TextClient):
    """Stub determinístico que valida o protocolo TextClient standalone."""

    def generate(self, prompt: str, system: str = "", temperature: float = 0.2, max_tokens: int = 1200) -> str:
        return json.dumps(
            {
                "title": "Vagalumes da Floresta",
                "description": "Cena gerada via stub standalone",
                "background": [5, 12, 22],
                "groups": [
                    {
                        "name": "vagalumes",
                        "sprite": "firefly",
                        "count": 14,
                        "color": [180, 255, 90],
                        "size": 0.03,
                        "spawn": "random",
                        "behaviors": [
                            {"type": "wander", "speed": 0.12, "turn": 2.0},
                            {"type": "seek_gaze", "speed": 0.25},
                        ],
                    }
                ],
            }
        )


def test_characterization_flow_3_interactive_nlp_and_phone_websocket(tmp_path: Path) -> None:
    store = ProjectStore.create(tmp_path / "interact", name="Show Interativo")
    state = ProjectState(store)
    runtime = InteractionRuntime()
    app = create_app(
        state,
        runtime=runtime,
        nlp_client_factory=lambda: _StubStandaloneLLM(),
        library_roots=[],
        save_library_config=False,
        config_dir=tmp_path / "cfg",
    )
    client = TestClient(app)

    # 1. Estado inicial e troca de preset
    r_state = client.get("/api/interact/state")
    assert r_state.status_code == 200
    assert r_state.json()["sensor"] == "sim"

    r_preset = client.post("/api/interact/presets/vaga-lumes")
    assert r_preset.status_code == 200
    assert r_preset.json()["spec"]["title"] == PRESETS["vaga-lumes"].title

    # 2. Geração NLP sem LLM (heurística local) e com LLM standalone
    r_heur = client.post("/api/interact/generate", json={"text": "peixes azuis nadando", "use_llm": False})
    assert r_heur.status_code == 200
    assert r_heur.json()["source"] == "fallback"

    r_llm = client.post("/api/interact/generate", json={"text": "vagalumes na floresta", "use_llm": True})
    assert r_llm.status_code == 200
    assert r_llm.json()["source"] == "llm"
    assert r_llm.json()["spec"]["title"] == "Vagalumes da Floresta"

    # 3. Controle do jogador simulado
    r_player = client.post("/api/interact/player", json={"x": 0.3, "distance": 2.0, "yaw_deg": 0.0, "tracked": True})
    assert r_player.status_code == 200
    assert r_player.json()["players"][0]["watching"] is True

    # 4. Conexão WebSocket do celular-sensor (/api/interact/phone)
    with client.websocket_connect("/api/interact/phone") as ws:
        # Ao conectar, o sensor ativo muda automaticamente para 'phone'
        assert client.get("/api/interact/state").json()["sensor"] == "phone"
        reply = None
        for _ in range(5):
            ws.send_text(
                json.dumps(
                    {
                        "faces": [
                            {
                                "nose": [0.5, 0.5],
                                "left_eye": [0.44, 0.48],
                                "right_eye": [0.56, 0.48],
                            }
                        ]
                    }
                )
            )
        reply = json.loads(ws.receive_text())
        assert reply["tracked"] is True
        assert reply["watching"] is True
        assert reply["scene"] == "Vagalumes da Floresta"


# ---------------------------------------------------------------------------
# Fluxo 4: Biblioteca Local, Sugestões de Encaixe e Presets de Cor
# ---------------------------------------------------------------------------
def test_characterization_flow_4_library_suggestions_and_color_presets(tmp_path: Path) -> None:
    lib_dir = tmp_path / "minhas_midias"
    lib_dir.mkdir()
    (lib_dir / "horizontal_16_9.png").write_bytes(_make_png_bytes(320, 180, (30, 200, 100)))
    (lib_dir / "vertical_9_16.png").write_bytes(_make_png_bytes(180, 320, (200, 100, 30)))

    store = ProjectStore.create(tmp_path / "show_lib", name="Show Galeria")
    state = ProjectState(store)
    state.update(
        lambda p: p.model_copy(
            update={
                "surfaces": [
                    Surface(
                        id="tela-wide",
                        label="Tela Wide",
                        node_id="proj-1",
                        warp=Warp(base=[(100.0, 100.0), (1700.0, 100.0), (1700.0, 1000.0), (100.0, 1000.0)]),
                    )
                ]
            }
        )
    )
    app = create_app(
        state,
        library_roots=[str(lib_dir)],
        save_library_config=False,
        config_dir=tmp_path / "cfg",
    )
    client = TestClient(app)

    # 1. Listagem e miniatura da biblioteca
    r_lib = client.get("/api/library?rescan=true")
    assert r_lib.status_code == 200
    items = r_lib.json()["items"]
    assert len(items) == 2

    wide_item = next(it for it in items if it["name"] == "horizontal_16_9.png")
    r_thumb = client.get(f"/api/library/{wide_item['id']}/thumb")
    assert r_thumb.status_code == 200
    assert r_thumb.headers["content-type"] == "image/jpeg"

    # 2. Importação idempotente para o projeto
    r_imp1 = client.post(f"/api/library/{wide_item['id']}/import")
    r_imp2 = client.post(f"/api/library/{wide_item['id']}/import")
    assert r_imp1.status_code == 200
    assert r_imp2.status_code == 200
    assert r_imp1.json()["item"]["sha256"] == r_imp2.json()["item"]["sha256"]

    # 3. Sugestão de encaixe sem duplicar mídia já importada
    r_sug = client.post("/api/suggest", json={"sources": ["project", "library"]})
    assert r_sug.status_code == 200
    sug_data = r_sug.json()
    assert sug_data["media_count"] == 2
    assert "tela-wide" in sug_data["suggestions"]
    assert sug_data["suggestions"]["tela-wide"]["pick"]["name"] == "horizontal_16_9.png"

    # 4. CRUD de presets de cor
    r_cp = client.post(
        "/api/color-presets",
        json={
            "name": "Quente Teatro",
            "color": {
                "brightness": 1.05,
                "contrast": 1.1,
                "saturation": 1.15,
                "gamma": 1.0,
                "temperature": 0.25,
            },
        },
    )
    assert r_cp.status_code == 200
    preset_id = r_cp.json()["preset"]["id"]
    assert len(client.get("/api/color-presets").json()["presets"]) == 1
    assert client.delete(f"/api/color-presets/{preset_id}").status_code == 200
    assert len(client.get("/api/color-presets").json()["presets"]) == 0


# ---------------------------------------------------------------------------
# Fluxo 5: Pipeline de Renderização OpenGL e Resiliência a Falha de Mídia
# ---------------------------------------------------------------------------
def test_characterization_flow_5_renderer_sync_layers_and_media_fallback(
    gl_ctx, tmp_path: Path
) -> None:
    from projmap.core.project import MediaItem, Node, Output

    store = ProjectStore.create(tmp_path / "render_show", name="Show Render")
    missing_sha = "a" * 64
    proj = Project(
        name="Show Render",
        nodes=[Node(id="proj-1", output=Output(width=320, height=180))],
        media={
            missing_sha: MediaItem(
                sha256=missing_sha,
                filename="missing.png",
                ext=".png",
                kind="image",
            )
        },
        surfaces=[
            Surface(
                id="s-base",
                label="Base",
                node_id="proj-1",
                warp=Warp(base=[(0.0, 0.0), (320.0, 0.0), (320.0, 180.0), (0.0, 180.0)]),
                source=SourceSpec(kind="color", color=(0, 200, 0)),
                layers=[
                    Layer(
                        id="l-top",
                        label="Topo Azul",
                        visible=True,
                        opacity=1.0,
                        rect=(0.25, 0.25, 0.5, 0.5),
                        source=SourceSpec(kind="color", color=(0, 0, 255)),
                    )
                ],
            )
        ],
    )

    # 1. Render offscreen compõe superfície verde (fundo) + camada azul (centro)
    rgb = render_offscreen(
        proj,
        "proj-1",
        store.media_path,
        store.resolve,
        t=0.0,
        ctx=gl_ctx,
        size=(320, 180),
    )
    assert rgb.shape == (180, 320, 3)
    # Canto superior esquerdo deve ser verde (fundo da superfície)
    assert int(rgb[10, 10, 1]) > 150 and int(rgb[10, 10, 2]) < 30
    # Centro deve ser azul (camada F9 sobreposta)
    assert int(rgb[90, 160, 2]) > 200 and int(rgb[90, 160, 1]) < 30

    # 2. Re-sync ao mover apenas o quad preserva a mesma instância de FrameSource
    fbo = gl_ctx.simple_framebuffer((320, 180), components=4)
    renderer = Renderer(gl_ctx, store.media_path, store.resolve)
    try:
        renderer.sync(proj, "proj-1")
        src_before = renderer._items[0].source
        proj.surfaces[0].warp.base = [(10.0, 10.0), (310.0, 0.0), (320.0, 180.0), (0.0, 170.0)]
        renderer.sync(proj, "proj-1")
        assert renderer._items[0].source is src_before

        # 3. Fonte com mídia ausente em disco não derruba o sync: cai no fallback magenta (255, 0, 255)
        proj.surfaces[0].layers = []
        proj.surfaces[0].source = SourceSpec(kind="image", media=missing_sha)
        renderer.sync(proj, "proj-1")
        renderer.render(fbo, 0.0)
        data = np.flipud(
            np.frombuffer(fbo.read(components=3, alignment=1), dtype=np.uint8).reshape(180, 320, 3)
        )
        assert int(data[90, 160, 0]) > 200
        assert int(data[90, 160, 1]) < 30
        assert int(data[90, 160, 2]) > 200
    finally:
        renderer.release()
        fbo.release()
