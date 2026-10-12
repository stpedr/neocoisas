"""Transmissão RTSP da camada interativa (projmap/interact/stream.py).

Nenhum teste fala com a rede: o ffmpeg é substituído por um script Python que
grava no disco o que receberia pelo stdin.
"""

import sys
import time

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from projmap.interact.stream import (RtspPublisher, carregar_env,  # noqa: E402
                                     esconder_senha, publisher_from_env)

URL = "rtsp://viewer:senha-secreta@10.0.0.9:8554/cam"


def test_senha_nunca_aparece_no_log():
    assert esconder_senha(URL) == "rtsp://viewer:***@10.0.0.9:8554/cam"
    assert "senha-secreta" not in esconder_senha(URL)
    # sem credencial, a URL fica como está
    assert esconder_senha("rtsp://10.0.0.9:8554/cam") == "rtsp://10.0.0.9:8554/cam"
    assert esconder_senha("") == ""


def test_comando_do_ffmpeg_tem_tamanho_taxa_e_transporte():
    cmd = RtspPublisher(URL, (640, 360), 25, bitrate="2M", transport="udp", ffmpeg="ffmpeg").comando()
    assert "640x360" in cmd and cmd[cmd.index("-r") + 1] == "25"
    assert cmd[cmd.index("-rtsp_transport") + 1] == "udp"
    assert cmd[cmd.index("-b:v") + 1] == "2M"
    assert cmd[-1] == URL and cmd[cmd.index("-f", cmd.index("-c:v")) + 1] == "rtsp"
    assert cmd[cmd.index("-pix_fmt") + 1] == "bgr24"  # entrada crua


def test_sem_ffmpeg_avisa_e_nao_derruba_nada():
    p = RtspPublisher(URL, ffmpeg=None)
    p.ffmpeg = None
    p.start(lambda size: (0, np.zeros((size[1], size[0], 4), np.uint8)))
    assert "ffmpeg" in p.status
    p.stop()


def test_env_configura_e_sem_url_nao_transmite(tmp_path, monkeypatch):
    for k in ("PROJMAP_RTSP_URL", "PROJMAP_RTSP_SIZE", "PROJMAP_RTSP_FPS",
              "PROJMAP_RTSP_BITRATE", "PROJMAP_RTSP_TRANSPORT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("projmap.interact.stream.carregar_env", lambda *a, **k: None)
    assert publisher_from_env() is None  # nada configurado: ProjMap segue como antes

    monkeypatch.setenv("PROJMAP_RTSP_URL", URL)
    monkeypatch.setenv("PROJMAP_RTSP_SIZE", "854x480")
    monkeypatch.setenv("PROJMAP_RTSP_FPS", "24")
    p = publisher_from_env()
    assert p.url == URL and p.size == (854, 480) and p.fps == 24
    monkeypatch.setenv("PROJMAP_RTSP_SIZE", "isso-nao-e-tamanho")  # cai no padrão, sem explodir
    assert publisher_from_env().size == (1280, 720)


def test_carregar_env_le_o_arquivo_sem_sobrescrever_o_ambiente(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comentário\nPROJMAP_RTSP_URL="rtsp://a:b@h/x"\nexport PROJMAP_RTSP_FPS=15\nLIXO\n',
                   encoding="utf-8")
    monkeypatch.delenv("PROJMAP_RTSP_URL", raising=False)
    monkeypatch.setenv("PROJMAP_RTSP_FPS", "60")  # já definido: o .env não manda nele
    carregar_env(env)
    import os

    assert os.environ["PROJMAP_RTSP_URL"] == "rtsp://a:b@h/x"  # aspas removidas
    assert os.environ["PROJMAP_RTSP_FPS"] == "60"
    carregar_env(tmp_path / "nao-existe")  # arquivo ausente é silencioso


def test_publica_os_quadros_da_interacao(tmp_path):
    """O laço entrega ao ffmpeg os bytes certos: BGR24, no tamanho pedido."""
    destino = tmp_path / "saida.raw"
    falso = tmp_path / "ffmpeg_falso.py"
    falso.write_text(
        "import sys\n"
        f"open(r'{destino}', 'wb').write(sys.stdin.buffer.read())\n", encoding="utf-8")

    w, h = 64, 36
    quadro = np.zeros((h, w, 4), np.uint8)
    quadro[..., 0] = 200  # R alto, G/B baixos: dá para conferir a ordem dos canais
    quadro[..., 3] = 255

    p = RtspPublisher(URL, (w, h), fps=60, ffmpeg=sys.executable)
    p.comando = lambda: [sys.executable, str(falso)]
    p.start(lambda size: (1, quadro))
    for _ in range(100):  # espera alguns quadros
        if p.quadros >= 3:
            break
        time.sleep(0.02)
    p.stop()

    assert p.quadros >= 3
    dados = destino.read_bytes()
    assert len(dados) >= 3 * w * h * 3 and len(dados) % (w * h * 3) == 0
    bgr = np.frombuffer(dados[: w * h * 3], np.uint8).reshape(h, w, 3)
    assert bgr[0, 0].tolist() == [0, 0, 200]  # RGBA(200,0,0) -> BGR(0,0,200)


def test_reconecta_quando_o_ffmpeg_morre(tmp_path):
    """Servidor fora do ar não derruba o show: tenta de novo e informa o erro."""
    morre = tmp_path / "morre.py"
    morre.write_text("import sys; sys.stderr.write('Connection refused\\n'); sys.exit(1)\n", encoding="utf-8")

    p = RtspPublisher(URL, (32, 18), fps=60, ffmpeg=sys.executable)
    p.comando = lambda: [sys.executable, str(morre)]
    p.start(lambda size: (1, np.zeros((size[1], size[0], 4), np.uint8)))
    erro = ""
    for _ in range(150):
        if "indisponível" in p.status:
            erro = p.status
            break
        time.sleep(0.02)
    assert p._thread.is_alive(), "devia continuar tentando reconectar"
    p.stop()
    assert "indisponível" in erro and "Connection refused" in erro
    assert "senha-secreta" not in erro  # nem no erro a senha escapa
    assert p.status == "parado"
