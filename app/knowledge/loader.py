"""Carga do manual de políticas e divisão em trechos por subseção.

Fonte preferida: data/políticas_da_loja.pdf lido com pypdf. Se o PDF não puder
ser lido (arquivo ausente, corrompido ou sem texto), usa o texto já extraído em
docs/challenge/politicas_extraido.txt; a origem fica em `Manual.source`.
O texto de cada trecho é literal (só com espaços normalizados e sem o cabeçalho
e o rodapé de página).
"""
from __future__ import annotations

import bisect
import logging
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.core.exceptions import DataError

log = logging.getLogger(__name__)

PDF_PATH = PROJECT_ROOT / "data" / "políticas_da_loja.pdf"
TXT_PATH = PROJECT_ROOT / "docs" / "challenge" / "politicas_extraido.txt"
DOC_VERSION = "2.1"
DOC_DATE = "2025-06"

_HEADER = "Empório da Música Manual de Políticas e Procedimentos"
_FOOTER = re.compile(r"\s*Página \d+\s*$")
_PAGE_MARK = re.compile(r"=== PAGE (\d+) ===")
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"))

INTERNAL = "internal_procedure"
PUBLIC = "customer_facing"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    section: str
    title: str
    text: str
    page_start: int
    page_end: int
    topics: tuple[str, ...]
    aliases: tuple[str, ...]
    open_issues: tuple[str, ...]
    audience: str


@dataclass(frozen=True)
class Manual:
    chunks: tuple[Chunk, ...]
    pages: tuple[str, ...]
    source: str  # "pdf" ou "txt"

    def get(self, chunk_id: str) -> Chunk:
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                return chunk
        raise KeyError(chunk_id)


@dataclass(frozen=True)
class _Spec:
    chunk_id: str
    section: str
    title: str
    marker: str  # início literal do trecho no texto normalizado
    topics: tuple[str, ...]
    aliases: tuple[str, ...]
    issues: tuple[str, ...]
    audience: str


def _s(chunk_id, section, title, marker, topics, aliases, issues=(), audience=PUBLIC):
    return _Spec(chunk_id, section, title, marker, tuple(topics), tuple(aliases), tuple(issues), audience)


# Ordem do documento. Os marcadores são literais do manual.
SPECS: tuple[_Spec, ...] = (
    _s("capa", "capa", "Capa e contato principal", "EMPÓRIO DA MÚSICA Sua música",
       ["contato"], ["telefone da loja", "email", "e-mail", "contato", "ligar"],
       ["I-1", "I-2", "I-10"], INTERNAL),
    _s("s1", "1", "Sobre a Empório da Música", "1. Sobre a Empório da Música",
       ["escopo"], ["acessórios", "cordas", "palhetas", "cabos", "cases", "pedais", "amplificador",
                    "vendem", "só instrumentos", "catálogo", "fundação"], ["I-12"]),
    _s("s1.1", "1.1", "Missão", "1.1 Missão", [], ["missão", "propósito"]),
    _s("s1.2", "1.2", "Dados da Empresa", "1.2 Dados da Empresa",
       ["contato"], ["endereço", "onde fica", "localização", "cnpj", "razão social", "telefone",
                     "whatsapp", "email", "e-mail", "contato", "cep"], ["I-1", "I-2"]),
    _s("s2", "2", "Horário de Funcionamento", "2. Horário de Funcionamento",
       ["horario"], ["horário", "abre", "fecha", "funcionamento", "sábado", "domingo", "feriado",
                     "aberto", "expediente", "black friday", "natal"]),
    _s("s3", "3", "Formas de Pagamento", "3. Formas de Pagamento",
       ["pagamento", "pix", "parcelamento"],
       ["pagar", "pix", "desconto no pix", "boleto", "débito", "crédito", "cartão", "parcelar",
        "forma de pagamento", "à vista"], ["I-3", "I-5"]),
    _s("s3.1", "3.1", "Regras de Parcelamento", "3.1 Regras de Parcelamento",
       ["parcelamento", "pagamento"],
       ["parcelar", "parcela", "parcelas", "parcelamento", "12x", "sem juros", "juros", "parcela mínima",
        "dividir", "combinar pagamento", "pix mais cartão", "dois cartões"], ["I-3", "I-4", "I-7"]),
    _s("s4", "4", "Política de Trocas e Devoluções (introdução)", "4. Política de Trocas e Devoluções",
       ["troca", "arrependimento"],
       ["código de defesa do consumidor", "cdc"]),
    _s("s4.1", "4.1", "Direito de Arrependimento (Compras Online)", "4.1 Direito de Arrependimento",
       ["arrependimento", "troca"],
       ["devolver", "devolução", "devolvo", "arrependi", "arrependimento", "desistir", "desistência",
        "não gostei", "7 dias", "compra online", "comprei pelo site", "reembolso", "estorno",
        "dinheiro de volta", "fora do prazo", "prazo de devolução", "prazo para devolver"], ["I-8", "I-11"]),
    _s("s4.2", "4.2", "Trocas por Defeito", "4.2 Trocas por Defeito",
       ["defeito", "troca", "garantia"],
       ["defeito", "defeituoso", "estragou", "quebrou", "não funciona", "problema", "defeito de fábrica",
        "trocar", "30 dias", "fabricante", "mau uso"], ["I-9"]),
    _s("s4.3", "4.3", "Trocas por Preferência", "4.3 Trocas por Preferência",
       ["troca"], ["trocar", "troca por preferência", "outra cor", "outro modelo", "tamanho",
                   "mudar de ideia", "diferença de valor"], ["I-8"]),
    _s("s4.4", "4.4", "Itens Não Elegíveis para Troca", "4.4 Itens Não Elegíveis para Troca",
       ["troca"], ["não pode trocar", "boquilha", "sopro", "liquidação", "venda final", "personalizado",
                   "setup", "regulagem", "higiene", "devolver"], ["I-8", "I-17"]),
    _s("s5.1", "5.1", "Entregas na Região Metropolitana de Campo Grande",
       "5. Política de Frete e Entregas 5.1",
       ["frete", "prazo_entrega"],
       ["frete", "entrega", "entregar", "taxa de entrega", "frete grátis", "motoboy", "campo grande",
        "região metropolitana", "R$ 35", "R$ 500", "quanto custa o frete"], ["I-6", "I-15", "I-16"]),
    _s("s5.2", "5.2", "Entregas para Outras Cidades", "5.2 Entregas para Outras Cidades",
       ["frete", "prazo_entrega", "rastreamento"],
       ["correios", "pac", "sedex", "jadlog", "outra cidade", "outro estado", "frete por cep", "seguro",
        "avaria", "chegou quebrado", "prazo de entrega", "frete especial", "bateria", "grande porte"],
       ["I-15", "I-16"]),
    _s("s5.3", "5.3", "Código de Rastreamento", "5.3 Código de Rastreamento",
       ["rastreamento"], ["rastreio", "rastrear", "código de rastreio", "acompanhar pedido",
                          "onde está meu pedido", "correios", "jadlog", "formato do código"]),
    _s("s6.1", "6.1", "Tipos de Promoção", "6. Promoções e Descontos 6.1",
       ["promocao"], ["promoção", "promoções", "black friday", "aniversário da loja", "volta às aulas",
                      "queima de estoque", "semana do músico", "campanha", "desconto"]),
    _s("s6.2", "6.2", "Regras de Promoções", "6.2 Regras de Promoções",
       ["promocao", "pix"], ["promoção", "desconto", "pix", "cumulativa", "acumular", "cupom", "rain check",
                             "esgotou", "preço promocional", "desconto de 5%"], ["I-5"]),
    _s("s7", "7", "Atendimento via WhatsApp", "7. Atendimento via WhatsApp",
       ["contato"], ["whatsapp", "zap", "atendimento", "canal de atendimento", "falar com atendente",
                     "assistente virtual", "número do whatsapp"], ["I-1", "I-10"], INTERNAL),
    _s("s7.1", "7.1", "Diretrizes de Atendimento", "7.1 Diretrizes de Atendimento",
       ["escopo", "atendimento"], ["tempo de resposta", "acessórios", "cordas", "palhetas", "cabos", "pedais",
                                   "amplificador", "lojas parceiras", "tom de voz"],
       ["I-10", "I-13", "I-14"], INTERNAL),
    _s("s7.2", "7.2", "Fluxo de Atendimento Padrão", "7.2 Fluxo de Atendimento Padrão",
       ["atendimento"], ["fluxo de atendimento", "saudação"], ["I-10"], INTERNAL),
    _s("s7.3-estoque", "7.3", "Situações Especiais: produto fora de estoque", "7.3 Situações Especiais",
       ["atendimento", "estoque"], ["fora de estoque", "sem estoque", "esgotado", "indisponível"],
       ["I-10"], INTERNAL),
    _s("s7.3-descontinuado", "7.3", "Situações Especiais: produto descontinuado", "Produto descontinuado:",
       ["atendimento", "estoque"], ["descontinuado", "saiu de linha", "não vende mais", "sucessor"],
       ["I-10"], INTERNAL),
    _s("s7.3-promocao", "7.3", "Situações Especiais: promoção expirada", "Promoção expirada:",
       ["atendimento", "promocao"], ["promoção expirada", "promoção vencida", "acabou a promoção"],
       ["I-10"], INTERNAL),
    _s("s7.3-reclamacao", "7.3", "Situações Especiais: reclamação", "Reclamação:",
       ["reclamacao", "atendimento"], ["reclamar", "reclamação", "insatisfeito", "atendimento ruim",
                                       "ouvidoria", "retorno em 24 horas"], ["I-10", "I-14"], INTERNAL),
    _s("s8.1", "8.1", "Garantia Legal", "8. Garantia 8.1 Garantia Legal",
       ["garantia", "defeito"], ["garantia", "garantia legal", "90 dias", "defeito de fabricação",
                                 "defeito", "cdc"], ["I-9"]),
    _s("s8.2", "8.2", "Garantia do Fabricante", "8.2 Garantia do Fabricante",
       ["garantia"], ["garantia", "garantia do fabricante", "certificado de garantia", "fabricante"]),
    _s("s8.3", "8.3", "O que Não Cobre a Garantia", "8.3 O que Não Cobre a Garantia",
       ["garantia", "defeito"], ["não cobre", "mau uso", "queda", "desgaste", "traste", "cordas gastas",
                                 "reparo de terceiros", "dano estético", "arranhão"], ["I-17"]),
    _s("s9", "9", "Privacidade e Proteção de Dados", "9. Privacidade e Proteção de Dados",
       ["lgpd"], ["lgpd", "privacidade", "meus dados", "excluir dados", "exclusão de dados", "apagar dados",
                  "dados pessoais", "marketing", "consentimento"]),
    _s("s10", "10", "Disposições Finais", "10. Disposições Finais",
       ["escalonamento"], ["gerência", "dúvida sobre política", "atualização do manual", "documento interno"],
       ["I-10"], INTERNAL),
)


def clean_text(text: str) -> str:
    """NFC, sem caracteres de largura zero, espaços colapsados."""
    text = unicodedata.normalize("NFC", text).translate(_ZERO_WIDTH)
    return re.sub(r"\s+", " ", text).strip()


def _clean_page(raw: str) -> str:
    text = clean_text(raw)
    if text.startswith(_HEADER):
        text = text[len(_HEADER):].strip()
    return _FOOTER.sub("", text).strip()


def _pages_from_pdf(path: Path) -> list[str]:
    from pypdf import PdfReader  # import tardio: o fallback não depende do pypdf

    reader = PdfReader(str(path))
    return [_clean_page(page.extract_text() or "") for page in reader.pages]


def _pages_from_txt(path: Path) -> list[str]:
    parts = _PAGE_MARK.split(path.read_text(encoding="utf-8"))
    return [_clean_page(body) for body in parts[2::2]]


def _read_pages(pdf_path: Path, txt_path: Path) -> tuple[list[str], str]:
    try:
        pages = _pages_from_pdf(pdf_path)
        if pages and all(pages):
            return pages, "pdf"
        log.warning("PDF sem texto em alguma página; usando o texto extraído")
    except Exception as exc:  # noqa: BLE001 - qualquer falha de leitura aciona o fallback
        log.warning("Falha ao ler o PDF (%s); usando o texto extraído", exc)
    try:
        pages = _pages_from_txt(txt_path)
    except OSError as exc:
        raise DataError(f"Manual de políticas indisponível: {exc}") from exc
    if not pages or not all(pages):
        raise DataError("Texto extraído do manual está vazio ou incompleto")
    return pages, "txt"


def build_chunks(pages: list[str]) -> tuple[Chunk, ...]:
    """Divide o texto das páginas nos trechos de SPECS, preservando a ordem."""
    full = " ".join(pages)
    starts = [0]
    for page in pages[:-1]:
        starts.append(starts[-1] + len(page) + 1)
    positions: list[int] = []
    cursor = 0
    for spec in SPECS:
        pos = full.find(spec.marker, cursor)
        if pos < 0:
            raise DataError(f"Seção {spec.section} ({spec.chunk_id}) não encontrada no manual")
        positions.append(pos)
        cursor = pos + len(spec.marker)
    positions[0] = 0
    chunks = []
    for i, spec in enumerate(SPECS):
        end = positions[i + 1] if i + 1 < len(SPECS) else len(full)
        text = full[positions[i]:end].strip()
        first = bisect.bisect_right(starts, positions[i])
        last = bisect.bisect_right(starts, positions[i] + len(text) - 1)
        chunks.append(Chunk(spec.chunk_id, spec.section, spec.title, text, first, last,
                            spec.topics, spec.aliases, spec.issues, spec.audience))
    return tuple(chunks)


@lru_cache(maxsize=1)
def load_manual() -> Manual:
    pages, source = _read_pages(PDF_PATH, TXT_PATH)
    return Manual(build_chunks(pages), tuple(pages), source)


def load_manual_from(pdf_path: Path, txt_path: Path) -> Manual:
    """Versão sem cache, para testes do fallback."""
    pages, source = _read_pages(pdf_path, txt_path)
    return Manual(build_chunks(pages), tuple(pages), source)
