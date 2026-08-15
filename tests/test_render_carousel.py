"""Testes do motor de slides.

Os núcleos de medida recebem `measure` **injetado** — testáveis sem carregar
fonte. A renderização de verdade usa Pillow, mas nada de GPU ou rede.
"""

import pytest

from agents.slides import CONTENT, CTA, HOOK, SUMMARY, Slide
from brand import BrandKit, hex_to_rgb, readable_on
from render_carousel import (
    DEFAULT_LAYOUT,
    CarouselLayout,
    fit_size,
    render_carousel,
    render_slide,
    slide_palette,
    wrap_lines,
)

# Medidor falso: cada caractere ocupa `size * 0.5` de largura e `size` de altura.
def fake_measure(texto: str, size: int) -> tuple[int, int]:
    return (int(len(texto) * size * 0.5), size)


def largura_em(size: int):
    return lambda t: fake_measure(t, size)[0]


class TestHexToRgb:
    def test_formato_longo_e_curto(self):
        assert hex_to_rgb("#C4632F") == (196, 99, 47)
        assert hex_to_rgb("#fff") == (255, 255, 255)
        assert hex_to_rgb("C4632F") == (196, 99, 47)

    def test_invalido_cai_no_fallback(self):
        assert hex_to_rgb("nada", (1, 2, 3)) == (1, 2, 3)
        assert hex_to_rgb("", (1, 2, 3)) == (1, 2, 3)
        assert hex_to_rgb("#GGGGGG", (1, 2, 3)) == (1, 2, 3)


class TestReadableOn:
    def test_escolhe_por_contraste(self):
        assert readable_on((255, 255, 255)) == (17, 17, 17)
        assert readable_on((0, 0, 0)) == (255, 255, 255)


class TestWrapLines:
    def test_quebra_no_limite(self):
        linhas = wrap_lines("uma frase que precisa quebrar", 100, largura_em(20))
        assert len(linhas) > 1
        assert " ".join(linhas) == "uma frase que precisa quebrar"

    def test_cabe_em_uma_linha(self):
        assert wrap_lines("curto", 10_000, largura_em(20)) == ["curto"]

    def test_texto_vazio(self):
        assert wrap_lines("", 100, largura_em(20)) == []
        assert wrap_lines("   ", 100, largura_em(20)) == []

    def test_palavra_maior_que_a_linha_fica_sozinha(self):
        linhas = wrap_lines("supercalifragilistico ok", 30, largura_em(20))
        assert linhas[0] == "supercalifragilistico"

    def test_nenhuma_linha_estoura_quando_da(self):
        medida = largura_em(20)
        for linha in wrap_lines("palavras curtas cabem bem aqui", 200, medida):
            assert medida(linha) <= 200


class TestFitSize:
    def test_texto_curto_usa_o_maior_corpo(self):
        size, linhas = fit_size("Oi", 1000, 1000, fake_measure, (100, 50, 20))
        assert size == 100
        assert linhas == ["Oi"]

    def test_texto_longo_diminui_a_fonte(self):
        grande, _ = fit_size("Oi", 400, 200, fake_measure, (100, 50, 20))
        pequeno, _ = fit_size("uma manchete bem mais longa " * 3, 400, 200, fake_measure, (100, 50, 20))
        assert pequeno < grande

    def test_preserva_o_texto_mesmo_sem_caber(self):
        texto = "palavra " * 60
        _, linhas = fit_size(texto, 100, 50, fake_measure, (100, 50, 20))
        assert " ".join(linhas).split() == texto.split()

    def test_texto_vazio_nao_quebra(self):
        size, linhas = fit_size("", 500, 500, fake_measure, (100, 50, 20))
        assert linhas == []
        assert size == 20

    def test_resultado_cabe_na_caixa(self):
        size, linhas = fit_size("manchete de tamanho médio aqui", 400, 300, fake_measure)
        assert max(fake_measure(l, size)[0] for l in linhas) <= 400


class TestAreaSegura:
    """Invariante do formato: nenhuma linha pode invadir a margem lateral.

    Usa o medidor **real** (fonte de verdade), não o falso — é aqui que uma
    troca de fonte ou de escala tipográfica quebraria o layout sem barulho.
    """

    MANCHETES = [
        "5 erros que fazem sua vela durar menos",
        "Primeira queima curta",
        "Salve para consultar depois",
        "Deixar no sol",
        "Um título absurdamente longo que jamais caberia em uma única linha do slide",
        "Antidisestablishmentarianismo",   # palavra única maior que a linha
    ]

    def test_manchetes_cabem_na_largura_util(self):
        from render_carousel import _HEADLINE_SIZES, _measurer

        measure, _ = _measurer(BrandKit())
        for manchete in self.MANCHETES:
            size, linhas = fit_size(
                manchete, DEFAULT_LAYOUT.content_width, DEFAULT_LAYOUT.content_height,
                measure, _HEADLINE_SIZES,
            )
            for linha in linhas:
                if " " not in linha:
                    continue          # palavra única: não há onde quebrar
                largura = measure(linha, size)[0]
                assert largura <= DEFAULT_LAYOUT.content_width, (
                    f"'{linha}' ({largura}px) estoura a área segura "
                    f"({DEFAULT_LAYOUT.content_width}px) no corpo {size}"
                )


class TestSlidePalette:
    def setup_method(self):
        self.kit = BrandKit(surface="#FFFFFF", ink="#111111", accent="#C4632F", deep="#2A1710")

    def test_gancho_usa_o_tom_profundo(self):
        fundo, texto, _ = slide_palette(HOOK, self.kit)
        assert fundo == self.kit.rgb_deep
        assert texto == (255, 255, 255)   # contraste sobre fundo escuro

    def test_cta_usa_o_realce(self):
        fundo, _, _ = slide_palette(CTA, self.kit)
        assert fundo == self.kit.rgb_accent

    def test_conteudo_e_resumo_usam_a_superficie(self):
        assert slide_palette(CONTENT, self.kit)[0] == self.kit.rgb_surface
        assert slide_palette(SUMMARY, self.kit)[0] == self.kit.rgb_surface

    def test_todos_os_papeis_tem_texto_legivel(self):
        for papel in (HOOK, CONTENT, SUMMARY, CTA):
            fundo, texto, _ = slide_palette(papel, self.kit)
            assert texto != fundo


class TestBrandKit:
    def test_from_palette_parcial_mantem_padrao(self):
        kit = BrandKit.from_palette(["#000000"])
        assert kit.surface == "#000000"
        assert kit.accent == BrandKit().accent

    def test_from_dict_aceita_paleta_ou_campos(self):
        assert BrandKit.from_dict({"palette": ["#111111"]}).surface == "#111111"
        assert BrandKit.from_dict({"accent": "#ABCDEF"}).accent == "#ABCDEF"

    def test_from_dict_ignora_chaves_desconhecidas(self):
        kit = BrandKit.from_dict({"accent": "#ABCDEF", "invento": 1})
        assert kit.accent == "#ABCDEF"

    def test_ida_e_volta(self):
        original = BrandKit(name="Doce Aroma", handle="@doce", accent="#C4632F")
        assert BrandKit.from_dict(original.to_dict()) == original


class TestRenderSlide:
    def setup_method(self):
        self.kit = BrandKit(name="Doce Aroma", handle="@docearoma")

    def test_gera_png_no_tamanho_do_formato(self, tmp_path):
        from PIL import Image

        destino = render_slide(
            Slide(headline="5 erros que fazem sua vela durar menos", role=HOOK),
            self.kit, 1, 8, tmp_path / "01.png",
        )
        assert destino.exists()
        with Image.open(destino) as img:
            assert img.size == (DEFAULT_LAYOUT.width, DEFAULT_LAYOUT.height)
            assert img.format == "PNG"

    def test_respeita_layout_customizado(self, tmp_path):
        from PIL import Image

        layout = CarouselLayout(width=400, height=500)
        render_slide(Slide(headline="Oi"), self.kit, 1, 1, tmp_path / "a.png", layout)
        with Image.open(tmp_path / "a.png") as img:
            assert img.size == (400, 500)

    def test_papeis_diferentes_geram_fundos_diferentes(self, tmp_path):
        from PIL import Image

        cores = []
        for papel in (HOOK, CONTENT, CTA):
            caminho = render_slide(Slide(headline="X", role=papel), self.kit, 1, 3, tmp_path / f"{papel}.png")
            with Image.open(caminho) as img:
                cores.append(img.getpixel((10, img.height - 10)))
        assert len(set(cores)) == 3

    def test_texto_longo_nao_quebra_a_renderizacao(self, tmp_path):
        destino = render_slide(
            Slide(headline="palavra " * 40, body="apoio " * 60),
            self.kit, 2, 8, tmp_path / "longo.png",
        )
        assert destino.exists()

    def test_arte_ilegivel_nao_derruba_o_slide(self, tmp_path):
        quebrada = tmp_path / "quebrada.png"
        quebrada.write_bytes(b"isto nao e uma imagem")
        destino = render_slide(
            Slide(headline="Com arte", image_path=str(quebrada)),
            self.kit, 1, 1, tmp_path / "arte.png",
        )
        assert destino.exists()

    def test_cria_o_diretorio_de_destino(self, tmp_path):
        destino = render_slide(
            Slide(headline="Oi"), self.kit, 1, 1, tmp_path / "novo" / "sub" / "01.png"
        )
        assert destino.exists()


class TestRenderCarousel:
    def test_gera_um_png_por_slide_em_ordem(self, tmp_path):
        slides = [
            Slide(headline="Gancho", role=HOOK),
            Slide(headline="Dica 1", body="detalhe"),
            Slide(headline="Compre", role=CTA),
        ]
        caminhos = render_carousel(slides, BrandKit(handle="@x"), tmp_path)
        assert [p.name for p in caminhos] == ["01.png", "02.png", "03.png"]
        assert all(p.exists() for p in caminhos)

    def test_sem_slides_e_erro(self, tmp_path):
        with pytest.raises(ValueError, match="Nenhum slide"):
            render_carousel([], BrandKit(), tmp_path)

    def test_mesma_marca_gera_a_mesma_faixa_em_todos(self, tmp_path):
        from PIL import Image

        kit = BrandKit(accent="#C4632F")
        caminhos = render_carousel(
            [Slide(headline=f"S{i}", role=CONTENT) for i in range(3)], kit, tmp_path
        )
        faixas = []
        for caminho in caminhos:
            with Image.open(caminho) as img:
                faixas.append(img.getpixel((img.width // 2, 4)))
        assert len(set(faixas)) == 1              # a assinatura é idêntica
        assert faixas[0] == kit.rgb_accent        # e vem do Brand Kit
