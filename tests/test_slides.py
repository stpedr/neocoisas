"""Testes do modelo de slide e da normalização vinda do LLM (tudo offline)."""

from agents.slides import CONTENT, CTA, HOOK, SUMMARY, Slide, build_slides, normalize_role


class TestNormalizeRole:
    def test_aceita_sinonimos_pt_e_en(self):
        assert normalize_role("gancho") == HOOK
        assert normalize_role("Hook") == HOOK
        assert normalize_role("call to action") == CTA
        assert normalize_role("RESUMO") == SUMMARY

    def test_desconhecido_vira_conteudo(self):
        assert normalize_role("qualquer coisa") == CONTENT
        assert normalize_role("") == CONTENT


class TestBuildSlides:
    def test_normaliza_campos_alternativos(self):
        slides = build_slides([
            {"titulo": "Gancho forte", "corpo": "apoio", "papel": "gancho"},
            {"headline": "Dica 1", "body": "detalhe"},
            {"title": "Compre agora", "role": "cta"},
        ])
        assert [s.headline for s in slides] == ["Gancho forte", "Dica 1", "Compre agora"]
        assert slides[0].role == HOOK
        assert slides[1].role == CONTENT
        assert slides[2].role == CTA
        assert slides[0].body == "apoio"

    def test_aceita_strings_puras(self):
        slides = build_slides(["Primeiro", "Segundo", "Terceiro"])
        assert len(slides) == 3
        assert slides[1].headline == "Segundo"

    def test_descarta_sem_manchete(self):
        slides = build_slides([{"body": "só apoio"}, {"headline": "  "}, {"headline": "Vale"}])
        assert [s.headline for s in slides] == ["Vale"]

    def test_ignora_itens_de_tipo_invalido(self):
        slides = build_slides([42, None, {"headline": "Vale"}])
        assert len(slides) == 1

    def test_infere_arco_quando_modelo_nao_marca_papel(self):
        slides = build_slides(["Gancho", "Meio", "Fim"])
        assert slides[0].role == HOOK
        assert slides[1].role == CONTENT
        assert slides[-1].role == CTA

    def test_nao_infere_arco_com_papeis_explicitos(self):
        slides = build_slides([
            {"headline": "A", "role": "content"},
            {"headline": "B"},
            {"headline": "C"},
        ])
        assert slides[0].role == CONTENT
        assert slides[-1].role == CONTENT

    def test_nao_infere_arco_com_poucos_slides(self):
        slides = build_slides(["Um", "Dois"])
        assert [s.role for s in slides] == [CONTENT, CONTENT]

    def test_respeita_o_teto_da_plataforma(self):
        slides = build_slides([f"Slide {i}" for i in range(20)])
        assert len(slides) == 10

    def test_lista_vazia(self):
        assert build_slides([]) == []


class TestSlideSerial:
    def test_ida_e_volta(self):
        original = Slide(
            headline="Título", body="corpo", role=HOOK,
            visual_prompt="vela acesa", alt_text="uma vela",
        )
        recriado = Slide.from_dict(original.to_dict())
        assert recriado == original

    def test_from_dict_normaliza_papel(self):
        assert Slide.from_dict({"headline": "x", "role": "gancho"}).role == HOOK
