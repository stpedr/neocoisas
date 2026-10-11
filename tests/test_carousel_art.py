"""Testes da geração de arte dos slides.

`style_prompt` é puro; a geração recebe o gerador injetado — nada de GPU, rede
ou chave de API.
"""

from pathlib import Path

from agents.slides import Slide
from brand import BrandKit
from carousel_art import ART_GUIDANCE, generate_slide_art, style_prompt


class TestStylePrompt:
    def test_sem_kit_mantem_o_prompt_e_pede_arte_limpa(self):
        assert style_prompt("a candle on a table") == f"a candle on a table, {ART_GUIDANCE}"

    def test_injeta_as_palavras_de_estilo_da_marca(self):
        kit = BrandKit(style_keywords=["warm tones", "artisanal", "soft light"])
        saida = style_prompt("a candle", kit)
        assert "a candle" in saida
        assert "warm tones, artisanal, soft light" in saida
        assert ART_GUIDANCE in saida

    def test_kit_sem_palavras_de_estilo(self):
        assert style_prompt("a candle", BrandKit()) == f"a candle, {ART_GUIDANCE}"

    def test_ignora_palavras_vazias(self):
        kit = BrandKit(style_keywords=["  ", "", "warm"])
        assert "warm" in style_prompt("x", kit)
        assert ", , " not in style_prompt("x", kit)

    def test_prompt_vazio_ainda_pede_arte_limpa(self):
        assert style_prompt("", BrandKit()) == ART_GUIDANCE
        assert style_prompt(None) == ART_GUIDANCE

    def test_a_mesma_marca_gera_o_mesmo_sufixo_em_todos_os_slides(self):
        kit = BrandKit(style_keywords=["warm tones"])
        saidas = [style_prompt(p, kit) for p in ("a candle", "a wick", "a table")]
        sufixos = [s.split(", ", 1)[1] for s in saidas]
        assert len(set(sufixos)) == 1   # é o que dá unidade visual ao carrossel


class FakeGenerator:
    """Gerador de imagem falso: cria um arquivo vazio e registra o prompt."""

    def __init__(self, falhar_em: set[int] | None = None):
        self.prompts: list[str] = []
        self.falhar_em = falhar_em or set()

    def __call__(self, prompt: str, dest: Path) -> Path:
        self.prompts.append(prompt)
        if len(self.prompts) in self.falhar_em:
            raise RuntimeError("provedor fora do ar")
        dest.write_bytes(b"")
        return dest


def slides(n: int, com_prompt: bool = True) -> list[Slide]:
    return [
        Slide(headline=f"S{i}", visual_prompt=f"scene {i}" if com_prompt else "")
        for i in range(1, n + 1)
    ]


class TestGenerateSlideArt:
    def test_preenche_image_path_de_cada_slide(self, tmp_path):
        lista = slides(3)
        resumo = generate_slide_art(lista, BrandKit(), dest_dir=tmp_path, generator=FakeGenerator())
        assert resumo["gerados"] == 3 and resumo["falhas"] == 0
        assert all(s.image_path and Path(s.image_path).exists() for s in lista)

    def test_nomeia_os_arquivos_na_ordem_dos_slides(self, tmp_path):
        lista = slides(3)
        generate_slide_art(lista, dest_dir=tmp_path, generator=FakeGenerator())
        assert [Path(s.image_path).name for s in lista] == ["01.png", "02.png", "03.png"]

    def test_condiciona_todos_os_prompts_pelo_estilo_da_marca(self, tmp_path):
        gerador = FakeGenerator()
        kit = BrandKit(style_keywords=["warm tones"])
        generate_slide_art(slides(3), kit, dest_dir=tmp_path, generator=gerador)
        assert all("warm tones" in p for p in gerador.prompts)

    def test_falha_de_um_slide_nao_derruba_o_lote(self, tmp_path):
        lista = slides(4)
        resumo = generate_slide_art(
            lista, dest_dir=tmp_path, generator=FakeGenerator(falhar_em={2})
        )
        assert resumo["gerados"] == 3 and resumo["falhas"] == 1
        assert lista[1].image_path is None          # o que falhou fica sem arte
        assert lista[0].image_path and lista[2].image_path
        falha = [d for d in resumo["detalhes"] if d["status"] == "falha"][0]
        assert falha["slide"] == 2 and "fora do ar" in falha["info"]

    def test_slide_sem_visual_prompt_e_pulado(self, tmp_path):
        lista = slides(2, com_prompt=False)
        gerador = FakeGenerator()
        resumo = generate_slide_art(lista, dest_dir=tmp_path, generator=gerador)
        assert resumo["pulados"] == 2 and resumo["gerados"] == 0
        assert gerador.prompts == []                 # não chama o provedor à toa

    def test_cria_o_diretorio_de_destino(self, tmp_path):
        destino = tmp_path / "novo" / "sub"
        generate_slide_art(slides(1), dest_dir=destino, generator=FakeGenerator())
        assert destino.exists()

    def test_lista_vazia(self, tmp_path):
        resumo = generate_slide_art([], dest_dir=tmp_path, generator=FakeGenerator())
        assert resumo["total"] == 0 and resumo["gerados"] == 0

    def test_arte_gerada_chega_ao_layout(self, tmp_path):
        """A ponta a ponta que importa: a arte preenchida é usada na composição."""
        from PIL import Image

        from render_carousel import render_carousel

        def gerador_colorido(prompt: str, dest: Path) -> Path:
            Image.new("RGB", (64, 80), (10, 200, 30)).save(dest)
            return dest

        lista = slides(2)
        generate_slide_art(lista, dest_dir=tmp_path / "arte", generator=gerador_colorido)
        caminhos = render_carousel(lista, BrandKit(), tmp_path / "post")
        with Image.open(caminhos[0]) as img:
            # O topo do slide mostra a arte (o véu escurece só o rodapé).
            r, g, b = img.getpixel((img.width // 2, 60))
            assert g > r and g > b, "a arte gerada não apareceu na composição"
