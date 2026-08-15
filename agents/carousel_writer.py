"""Agente de copy de carrossel — do brief ao post pronto para renderizar.

Transforma um brief (tema + pilar + contexto da marca) no **pacote de texto** de
um carrossel: os slides com o arco narrativo, a legenda e as hashtags.

    brief -> gancho -> conteúdo x N -> resumo -> CTA  (+ legenda + hashtags)

O arco importa: o **gancho** para o scroll, o **conteúdo** entrega uma ideia por
slide, o **resumo** dá motivo para salvar e o **CTA** pede a ação. Cada slide
recebe escopo explícito no prompt para não repetir o vizinho — a mesma correção
que sistemas multi-agente usam para trabalhadores paralelos não duplicarem
trabalho.

As funções de normalização (`build_carousel`, `normalize_hashtags`,
`clean_caption`, `build_brand_block`) são **puras** e cobertas por testes; só a
geração depende do LLM.
"""

from __future__ import annotations

import json
import re

from .llm import OllamaError, get_text_client
from .slides import CTA, HOOK, MAX_SLIDES, MIN_SLIDES, SUMMARY, Slide, build_slides

__all__ = [
    "CarouselWriterAgent",
    "build_carousel",
    "build_brand_block",
    "normalize_hashtags",
    "clean_caption",
    "OllamaError",
]

MAX_HASHTAGS = 15
MAX_CAPTION_CHARS = 2200  # limite de legenda do Instagram

# Aspas que o modelo costuma pôr em volta da legenda (abertura -> fechamento).
_PARES_ASPAS = {'"': '"', "'": "'", "“": "”", "‘": "’"}

# Rótulos aceitos no bloco de marca, na ordem em que entram no prompt.
_BRAND_FIELDS = (
    ("name", "Marca"),
    ("segment", "Segmento"),
    ("audience", "Público"),
    ("tone", "Tom de voz"),
    ("products", "Produtos/serviços"),
    ("dos", "Sempre"),
    ("donts", "Nunca"),
)


def _as_text(value) -> str:
    """Achata str/list/tuple num texto curto; ignora vazios."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def build_brand_block(context: dict | None) -> str:
    """Monta o bloco de contexto da marca para o prompt.

    Só inclui os campos presentes — uma marca com pouca informação gera um bloco
    curto, em vez de linhas vazias que confundem o modelo. Sem contexto, devolve
    string vazia.
    """
    if not context:
        return ""
    linhas = []
    for chave, rotulo in _BRAND_FIELDS:
        texto = _as_text(context.get(chave))
        if texto:
            linhas.append(f"- {rotulo}: {texto}")
    if not linhas:
        return ""
    return "Contexto da marca (respeite em todos os slides):\n" + "\n".join(linhas)


def normalize_hashtags(raw, limit: int = MAX_HASHTAGS) -> list[str]:
    """Normaliza hashtags: com `#`, sem espaços, sem duplicatas, na ordem original.

    Aceita lista ou string única separada por espaço/vírgula. Itens que não
    sobram nada depois da limpeza são descartados.
    """
    if isinstance(raw, str):
        # String solta: o modelo enfileirou tudo numa linha — fatiar.
        itens = re.split(r"[\s,;]+", raw)
    elif isinstance(raw, (list, tuple)):
        # Lista: cada elemento é UMA tag, mesmo com espaço no meio
        # ("Velas Artesanais" -> #velasartesanais). Só separa quando o próprio
        # elemento traz mais de uma tag (vírgula ou '#' fora do início).
        itens = []
        for item in raw:
            texto = str(item).strip()
            if re.search(r"[,;]", texto) or "#" in texto[1:]:
                itens.extend(re.split(r"[,;]+|(?=#)", texto))
            else:
                itens.append(texto)
    else:
        return []

    vistas: set[str] = set()
    tags: list[str] = []
    for item in itens:
        # Mantém letras (com acento), números e underscore; o resto sai.
        limpo = re.sub(r"[^0-9A-Za-zÀ-ÿ_]", "", item.strip()).lower()
        if not limpo or limpo in vistas:
            continue
        vistas.add(limpo)
        tags.append(f"#{limpo}")
        if len(tags) >= limit:
            break
    return tags


def clean_caption(text, max_chars: int = MAX_CAPTION_CHARS) -> str:
    """Limpa a legenda: sem aspas envolventes, sem espaços sobrando, dentro do limite."""
    if not isinstance(text, str):
        return ""
    caption = text.strip()
    # O modelo às vezes devolve a legenda inteira entre aspas. As tipográficas
    # abrem e fecham com caracteres diferentes, então comparar por par.
    if len(caption) >= 2 and _PARES_ASPAS.get(caption[0]) == caption[-1]:
        caption = caption[1:-1].strip()
    caption = re.sub(r"[ \t]+", " ", caption)
    caption = re.sub(r"\n{3,}", "\n\n", caption)
    if len(caption) > max_chars:
        caption = caption[:max_chars].rstrip()
    return caption


def _first(data: dict, *keys: str):
    for key in keys:
        if data.get(key):
            return data[key]
    return None


def build_carousel(data, max_slides: int = MAX_SLIDES) -> dict:
    """Normaliza a resposta do modelo em `{slides, caption, hashtags}`.

    Tolera a lista de slides vinda solta (sem o objeto em volta) e nomes de
    campo alternativos em português e inglês.
    """
    if isinstance(data, list):
        data = {"slides": data}
    if not isinstance(data, dict):
        return {"slides": [], "caption": "", "hashtags": []}

    brutos = _first(data, "slides", "carrossel", "cards", "telas") or []
    if not isinstance(brutos, list):
        brutos = []

    return {
        "slides": build_slides(brutos, max_slides=max_slides),
        "caption": clean_caption(_first(data, "caption", "legenda", "texto") or ""),
        "hashtags": normalize_hashtags(_first(data, "hashtags", "tags") or []),
    }


class CarouselWriterAgent:
    """Escreve o pacote de texto de um carrossel usando o LLM local."""

    def __init__(self, config_path: str = "config.json"):
        self.client = get_text_client(config_path, agent="carousel")
        self.config = self.client.config

    @staticmethod
    def _build_prompt(brief: str, num_slides: int, brand_block: str, pillar: str) -> str:
        conteudo = num_slides - 3  # gancho + resumo + CTA são fixos
        pilar = f"\nPilar de conteúdo: {pillar}." if pillar else ""
        marca = f"\n{brand_block}\n" if brand_block else "\n"
        return f"""
        Você é redator de social media especializado em carrosséis de Instagram
        que param o scroll e são salvos.

        Tema do post: '{brief}'.{pilar}{marca}
        Escreva um carrossel de exatamente {num_slides} slides, nesta estrutura:
          - slide 1: papel "hook" — o gancho. Uma promessa ou tensão que faz
            parar o scroll. Curto e específico, sem clickbait vazio.
          - slides 2 a {num_slides - 2}: papel "content" — {conteudo} slides, cada um com
            UMA ideia distinta. Nenhum slide pode repetir o assunto de outro:
            se um fala de X, os demais não voltam a X.
          - slide {num_slides - 1}: papel "summary" — recapitula em uma linha, para dar
            motivo de salvar o post.
          - slide {num_slides}: papel "cta" — chama para a ação, coerente com a marca.

        Retorne APENAS um JSON válido, um objeto com:
          - "slides": LISTA de objetos, cada um com
              "role": um de "hook", "content", "summary", "cta";
              "headline": o título grande do slide (máx. 8 palavras, em português);
              "body": uma frase curta de apoio (pode ser vazia no hook e no cta);
              "visual_prompt": descrição da arte do slide, em inglês, para um
                gerador de imagens;
              "alt_text": descrição da imagem em português, para acessibilidade;
          - "caption": a legenda do post (2 a 4 frases, em português, terminando
            com um convite a comentar ou salvar);
          - "hashtags": LISTA de 5 a 10 hashtags relevantes, sem repetição.

        Não inclua texto fora do JSON.
        """

    def write(
        self,
        brief: str,
        num_slides: int = 8,
        brand: dict | None = None,
        pillar: str = "",
    ) -> dict:
        """Gera o carrossel para o brief. Devolve `{slides, caption, hashtags}`.

        `num_slides` é limitado à faixa suportada pela plataforma (3 a 10).
        Levanta `OllamaError` se o servidor falhar e `ValueError` se o modelo não
        devolver slides aproveitáveis.
        """
        num_slides = max(MIN_SLIDES, min(MAX_SLIDES, int(num_slides)))
        print(
            f"[OLLAMA/GPU] Escrevendo carrossel de {num_slides} slides para "
            f"'{brief}' com o modelo local {self.client.model}..."
        )
        prompt = self._build_prompt(brief, num_slides, build_brand_block(brand), pillar)
        raw = self.client.generate(prompt)
        try:
            data = self.client.extract_json(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "O modelo não retornou um JSON de carrossel válido.\n"
                f"Saída bruta:\n{raw}"
            ) from exc

        resultado = build_carousel(data)
        if not resultado["slides"]:
            raise ValueError("Nenhum slide aproveitável foi gerado pelo modelo.")
        return resultado

    def write_idea(self, idea, brand: dict | None = None, num_slides: int = 8):
        """Preenche uma `Idea` com o carrossel gerado e a devolve.

        Usa `idea.title` como brief (caindo em `idea.prompt`) e marca o formato
        como carrossel.
        """
        brief = (idea.title or idea.prompt or "").strip()
        if not brief:
            raise ValueError("A ideia não tem título nem prompt para servir de brief.")
        pacote = self.write(
            brief, num_slides=num_slides, brand=brand, pillar=getattr(idea, "pillar", "")
        )
        idea.slides = pacote["slides"]
        idea.caption = pacote["caption"]
        idea.hashtags = pacote["hashtags"]
        idea.post_format = "carousel"
        return idea


if __name__ == "__main__":
    agent = CarouselWriterAgent()
    pacote = agent.write(
        agent.config.get("active_niche", "dicas de organização"),
        brand={"name": "Exemplo", "tone": "acolhedor"},
    )
    for i, slide in enumerate(pacote["slides"], 1):
        print(f"[{i}/{len(pacote['slides'])}] ({slide.role}) {slide.headline}")
        if slide.body:
            print(f"      {slide.body}")
    print(f"\nLegenda: {pacote['caption']}")
    print(f"Hashtags: {' '.join(pacote['hashtags'])}")
