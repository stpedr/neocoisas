"""Testes do agente de copy de carrossel.

Os núcleos de normalização são puros; a geração é testada com um cliente de
texto falso — nada depende do Ollama.
"""

import json

import pytest

from agents.carousel_writer import (
    MAX_CAPTION_CHARS,
    CarouselWriterAgent,
    build_brand_block,
    build_carousel,
    clean_caption,
    normalize_hashtags,
)
from agents.slides import CONTENT, CTA, HOOK, SUMMARY


class TestNormalizeHashtags:
    def test_adiciona_cerquilha_e_minusculiza(self):
        assert normalize_hashtags(["Velas", "#Aroma"]) == ["#velas", "#aroma"]

    def test_remove_duplicatas_preservando_ordem(self):
        assert normalize_hashtags(["#a", "A", "b", "#A"]) == ["#a", "#b"]

    def test_aceita_string_unica(self):
        assert normalize_hashtags("#um #dois, tres") == ["#um", "#dois", "#tres"]

    def test_item_de_lista_com_espaco_e_uma_tag_so(self):
        # "Velas Artesanais" é um conceito, não duas tags.
        assert normalize_hashtags(["Velas Artesanais"]) == ["#velasartesanais"]

    def test_item_de_lista_separa_quando_traz_varias_tags(self):
        assert normalize_hashtags(["#um #dois"]) == ["#um", "#dois"]
        assert normalize_hashtags(["um, dois"]) == ["#um", "#dois"]

    def test_preserva_acentos_e_remove_pontuacao(self):
        assert normalize_hashtags(["decoração!", "casa-nova"]) == ["#decoração", "#casanova"]

    def test_descarta_itens_vazios(self):
        assert normalize_hashtags(["#", "  ", "!!!", "ok"]) == ["#ok"]

    def test_respeita_o_limite(self):
        assert len(normalize_hashtags([f"tag{i}" for i in range(40)], limit=5)) == 5

    def test_tipos_invalidos(self):
        assert normalize_hashtags(None) == []
        assert normalize_hashtags(42) == []
        assert normalize_hashtags([]) == []


class TestCleanCaption:
    def test_remove_aspas_envolventes(self):
        assert clean_caption('"Uma legenda"') == "Uma legenda"
        assert clean_caption("“Outra”") == "Outra"

    def test_colapsa_espacos_e_linhas(self):
        assert clean_caption("a    b") == "a b"
        assert clean_caption("a\n\n\n\nb") == "a\n\nb"

    def test_respeita_o_limite_do_instagram(self):
        assert len(clean_caption("x" * (MAX_CAPTION_CHARS + 500))) == MAX_CAPTION_CHARS

    def test_tipos_invalidos(self):
        assert clean_caption(None) == ""
        assert clean_caption(123) == ""

    def test_nao_estraga_aspas_internas(self):
        assert clean_caption('ele disse "oi" e saiu') == 'ele disse "oi" e saiu'


class TestBuildBrandBlock:
    def test_sem_contexto(self):
        assert build_brand_block(None) == ""
        assert build_brand_block({}) == ""

    def test_so_inclui_campos_presentes(self):
        bloco = build_brand_block({"name": "Doce Aroma", "tone": "acolhedor"})
        assert "Doce Aroma" in bloco and "acolhedor" in bloco
        assert "Público" not in bloco

    def test_achata_listas(self):
        bloco = build_brand_block({"products": ["velas", "difusores"]})
        assert "velas, difusores" in bloco

    def test_ignora_campos_desconhecidos_e_vazios(self):
        assert build_brand_block({"invento": "x", "tone": "  "}) == ""


class TestBuildCarousel:
    def test_pacote_completo(self):
        pacote = build_carousel({
            "slides": [
                {"role": "hook", "headline": "Gancho"},
                {"role": "content", "headline": "Dica"},
                {"role": "cta", "headline": "Compre"},
            ],
            "caption": "  Uma legenda  ",
            "hashtags": ["Velas", "velas", "aroma"],
        })
        assert [s.role for s in pacote["slides"]] == [HOOK, CONTENT, CTA]
        assert pacote["caption"] == "Uma legenda"
        assert pacote["hashtags"] == ["#velas", "#aroma"]

    def test_aceita_lista_solta_de_slides(self):
        pacote = build_carousel([{"headline": "A"}, {"headline": "B"}, {"headline": "C"}])
        assert len(pacote["slides"]) == 3
        assert pacote["caption"] == "" and pacote["hashtags"] == []

    def test_campos_alternativos_em_portugues(self):
        pacote = build_carousel({
            "carrossel": [{"titulo": "Oi"}],
            "legenda": "leg",
            "tags": ["x"],
        })
        assert pacote["slides"][0].headline == "Oi"
        assert pacote["caption"] == "leg"
        assert pacote["hashtags"] == ["#x"]

    def test_tipos_invalidos_nao_quebram(self):
        vazio = {"slides": [], "caption": "", "hashtags": []}
        assert build_carousel(None) == vazio
        assert build_carousel("texto") == vazio
        assert build_carousel({"slides": "não é lista"}) == vazio

    def test_respeita_o_teto_de_slides(self):
        pacote = build_carousel({"slides": [{"headline": f"S{i}"} for i in range(20)]})
        assert len(pacote["slides"]) == 10


# --------------------------------------------------------------- integração ---
class FakeClient:
    """Cliente de texto falso — devolve uma resposta fixa."""

    model = "fake"
    config: dict = {}

    def __init__(self, resposta: str):
        self.resposta = resposta
        self.prompt_recebido = ""

    def generate(self, prompt: str) -> str:
        self.prompt_recebido = prompt
        return self.resposta

    def extract_json(self, raw: str):
        return json.loads(raw)


def agente_com(resposta: str) -> tuple[CarouselWriterAgent, FakeClient]:
    """Monta o agente sem tocar no factory (que exigiria config/Ollama)."""
    agente = CarouselWriterAgent.__new__(CarouselWriterAgent)
    cliente = FakeClient(resposta)
    agente.client = cliente
    agente.config = {}
    return agente, cliente


RESPOSTA_OK = json.dumps({
    "slides": [
        {"role": "hook", "headline": "5 erros com velas", "body": "O 3º é comum."},
        {"role": "content", "headline": "Apagar soprando", "body": "Espalha fuligem."},
        {"role": "content", "headline": "Pavio comprido", "body": "Queima rápido."},
        {"role": "summary", "headline": "Salve para depois", "body": "Resumo."},
        {"role": "cta", "headline": "Ver a coleção", "body": ""},
    ],
    "caption": '"Sua vela acaba rápido? Veja os erros."',
    "hashtags": ["velas", "Velas", "aroma"],
})


class TestWrite:
    def test_gera_pacote_normalizado(self):
        agente, _ = agente_com(RESPOSTA_OK)
        pacote = agente.write("erros com velas", num_slides=5)
        assert len(pacote["slides"]) == 5
        assert [s.role for s in pacote["slides"]] == [HOOK, CONTENT, CONTENT, SUMMARY, CTA]
        assert pacote["caption"] == "Sua vela acaba rápido? Veja os erros."
        assert pacote["hashtags"] == ["#velas", "#aroma"]

    def test_prompt_leva_contexto_da_marca_e_pilar(self):
        agente, cliente = agente_com(RESPOSTA_OK)
        agente.write("tema", num_slides=5, brand={"name": "Doce Aroma"}, pillar="educativo")
        assert "Doce Aroma" in cliente.prompt_recebido
        assert "educativo" in cliente.prompt_recebido

    def test_prompt_pede_ideias_distintas_por_slide(self):
        agente, cliente = agente_com(RESPOSTA_OK)
        agente.write("tema", num_slides=5)
        assert "pode repetir o assunto" in cliente.prompt_recebido

    def test_num_slides_e_limitado_a_faixa_da_plataforma(self):
        agente, cliente = agente_com(RESPOSTA_OK)
        agente.write("tema", num_slides=50)
        assert "exatamente 10 slides" in cliente.prompt_recebido
        agente.write("tema", num_slides=1)
        assert "exatamente 3 slides" in cliente.prompt_recebido

    def test_json_invalido_vira_value_error(self):
        agente, _ = agente_com("isto não é json")
        with pytest.raises(ValueError, match="JSON de carrossel"):
            agente.write("tema")

    def test_sem_slides_aproveitaveis_vira_value_error(self):
        agente, _ = agente_com(json.dumps({"slides": [{"body": "sem manchete"}]}))
        with pytest.raises(ValueError, match="Nenhum slide"):
            agente.write("tema")


class TestWriteIdea:
    def _idea(self, **kwargs):
        from review.models import Idea

        return Idea(prompt=kwargs.pop("prompt", ""), title=kwargs.pop("title", ""), **kwargs)

    def test_preenche_a_ideia(self):
        agente, _ = agente_com(RESPOSTA_OK)
        idea = agente.write_idea(self._idea(title="erros com velas"), num_slides=5)
        assert idea.post_format == "carousel"
        assert len(idea.slides) == 5
        assert idea.caption.startswith("Sua vela")
        assert idea.hashtags == ["#velas", "#aroma"]

    def test_usa_o_prompt_quando_nao_ha_titulo(self):
        agente, cliente = agente_com(RESPOSTA_OK)
        agente.write_idea(self._idea(prompt="tema do prompt"), num_slides=5)
        assert "tema do prompt" in cliente.prompt_recebido

    def test_ideia_sem_brief_e_erro(self):
        agente, _ = agente_com(RESPOSTA_OK)
        with pytest.raises(ValueError, match="brief"):
            agente.write_idea(self._idea())

    def test_ideia_preenchida_sobrevive_ao_ida_e_volta(self):
        from review.models import Idea

        agente, _ = agente_com(RESPOSTA_OK)
        idea = agente.write_idea(self._idea(title="tema"), num_slides=5)
        recriada = Idea.from_dict(idea.to_dict())
        assert recriada.post_format == "carousel"
        assert [s.headline for s in recriada.slides] == [s.headline for s in idea.slides]
        assert recriada.hashtags == idea.hashtags
