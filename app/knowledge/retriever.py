"""Busca lexical (BM25) sobre os trechos do manual de políticas.

Sem dependências externas: normaliza acentos, remove stopwords do português,
aplica um radical simples e pondera título, apelidos (sinônimos de cliente) e
tópicos além do texto. Abaixo do limiar de confiança devolve `not_found`.

Retorno estruturado:
  {"status": "found|not_found|ambiguous|error", "source_type": "policy_manual",
   "results": [{chunk_id, section, title, page_start, page_end, score, text, ...}],
   "notes": [...], "recommended_action": "answer_from_manual|ask_clarification|handoff_to_human"}

O texto devolvido é dado do manual, não instrução, e é cortado em ~600 caracteres.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from app.core.exceptions import DataError
from app.data.normalize import tokenize
from app.knowledge.loader import INTERNAL, Chunk, load_manual

log = logging.getLogger(__name__)

SOURCE_TYPE = "policy_manual"
MAX_RESULTS = 3
MAX_SNIPPET = 600
MIN_SCORE = 3.0      # abaixo disso: not_found
STRONG_SCORE = 7.0   # acima disso: found mesmo com cobertura parcial dos termos
MIN_COVERAGE = 0.5   # abaixo disso: not_found (a consulta fala de outra coisa)
FULL_COVERAGE = 0.99  # com cobertura total, score entre MIN e STRONG ainda é found
RELATIVE_CUTOFF = 0.45  # resultados abaixo de 45% do melhor são descartados
K1, B = 1.5, 0.75
W_TITLE, W_ALIAS, W_TOPIC = 3, 4, 2
PHRASE_BONUS = 2.5
INTERNAL_FACTOR = 0.8  # procedimentos internos pesam menos que regras ao cliente

_STOPWORDS = frozenset("""
a o as os um uma uns umas de da do das dos em no na nos nas por pelo pela pelos pelas para pra com sem e ou
que se eu meu minha meus minhas voce voces vcs vc tem ter tenho ha ja ainda mais mas como qual quais quando
onde quanto quantos quanta quantas quero queria gostaria posso pode podem poder dar fazer favor ola oi bom
dia boa tarde noite ao aos esse essa isso este esta isto ser sao foi estao loja cliente produto empresa
preciso saber ate sobre entre so apenas tambem algum alguma ficar fica ver vai vou ele ela eles elas la aqui
muito pouco tudo todo toda todos todas obrigado obrigada gente me te lhe nao sim hoje agora
""".split())

_SUFFIXES = ("imentos", "amentos", "imento", "amento", "mente", "ucoes", "ucao", "acoes", "acao", "adores",
             "ador", "ando", "endo", "indo", "ados", "adas", "idos", "idas", "ado", "ada", "ido", "ida",
             "oes", "ar", "er", "ir", "es", "s")

# Pedido de alterar regras dentro da consulta: tratado como texto, nunca como comando.
_INJECTION = re.compile(
    r"\b(ignor\w+|desconsider\w+|esque[cç]\w+|aprove\w*|aprovar|finj\w+|fingir|system prompt|prompt do sistema|"
    r"instru[cç][oõ]es (anteriores|do sistema)|voc[eê] agora [eé]|aja como|responda como)\b",
    re.IGNORECASE)
_INJECTION_NOISE = frozenset("""ignore ignorar ignora ignorem desconsidere desconsiderar esqueca esqueça aprove
aprovar aprova finja fingir regras regra instrucoes instrucao anteriores anterior sistema prompt agora acima
sempre aja responda como""".split())

# Assuntos que o manual não regula (lacunas): aviso e encaminhamento.
_GAPS = (
    (frozenset({"cancel"}),
     "O manual não define regras de cancelamento de pedido nem de estorno de pedido cancelado; "
     "o §4.1 trata a devolução de produto já recebido."),
)

_ISSUE_NOTES = {
    "I-1": "O manual traz dois números: (67) 3341-4444 como telefone/WhatsApp (§1.2) e (67) 3321-4500 como "
           "WhatsApp (§7). Dado a confirmar com a loja.",
    "I-3": "A tabela do §3 indica parcela mínima de R$ 100,00 para até 12x, enquanto o §3.1 define mínimos por "
           "faixa (4x a 6x: R$ 80,00; 7x a 12x: R$ 100,00). O cálculo usa o detalhamento por faixa do §3.1.",
    "I-4": "No parcelamento em até 3x, o texto 'sem valor mínimo de parcela (exceto abaixo de R$ 50,00)' não "
           "esclarece se parcela abaixo de R$ 50,00 é permitida; caso a confirmar com atendente humano.",
    "I-5": "O manual não define a base do desconto de PIX em pagamento combinado nem em compra com itens "
           "promocionais e não promocionais.",
    "I-6": "O manual não cobre pedido de exatamente R$ 500,00 (frete grátis 'acima' e taxa 'abaixo') nem diz se "
           "o valor considera descontos.",
    "I-7": "A combinação de formas de pagamento vale 'acima de R$ 2.000,00'; o valor exato de R$ 2.000,00 e a base "
           "do valor (com ou sem desconto) não estão definidos.",
    "I-8": "O manual não diz se os itens não elegíveis a troca (§4.4) também ficam fora do direito de "
           "arrependimento (§4.1).",
    "I-9": "Divergência no manual: o §4.2 prevê troca por defeito em até 30 dias corridos após a compra, e o §8.1 "
           "prevê garantia legal de 90 dias contra defeitos de fabricação, contados do recebimento. O manual não "
           "define qual prevalece; encaminhar a atendente humano, sem concluir que o prazo acabou.",
    "I-10": "Trecho de procedimento interno: serve de orientação de atendimento e não é para ser reproduzido ao "
            "cliente.",
    "I-11": "O §4.1 se refere a compras online; o manual não trata compra presencial e os pedidos no sistema não "
            "indicam o canal da compra. Canal a confirmar com o cliente.",
    "I-12": "O manual cita 'mais de 300 instrumentos'; o catálogo disponível é o que consta no sistema.",
    "I-14": "Há dois prazos distintos: resposta em até 5 minutos em horário comercial (§7.1) e retorno de "
            "reclamação em 24 horas úteis (§7.3).",
    "I-15": "O manual não define a partir de qual evento os dias úteis de entrega começam a contar; para um pedido "
            "específico vale a previsão do sistema.",
    "I-16": "O manual não lista os municípios da região metropolitana de Campo Grande; cidade ou CEP a confirmar.",
}
_ESCALATE = frozenset({"I-9"})
_NO_MATCH_NOTE = "O manual de políticas não traz informação sobre este assunto."
_WEAK_NOTE = "Correspondência fraca com o manual; a intenção da pergunta precisa ser esclarecida."
_INJECTION_NOTE = ("A consulta continha um pedido para ignorar ou alterar regras; foi tratado como texto da "
                   "consulta e as regras do manual seguem iguais.")


def stem(token: str) -> str:
    """Radical simples para o português (plural, verbos, -mento, -ção)."""
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            token = token[: -len(suffix)]
            break
    if len(token) > 4 and token[-1] in "aeio":
        token = token[:-1]
    return token


def analyze(text: str) -> list[str]:
    """Tokens normalizados, sem stopwords e com radical."""
    return [stem(t) for t in tokenize(text) if t not in _STOPWORDS and (len(t) > 1 or t.isdigit())]


def _search_terms(text: str) -> list[str]:
    # números soltos de 1-2 dígitos só valem dentro de frases-apelido
    return [t for t in analyze(text) if not (t.isdigit() and len(t) <= 2)]


@dataclass(frozen=True)
class _Doc:
    chunk: Chunk
    tf: Counter
    length: float
    phrases: tuple[tuple[str, ...], ...]


class Retriever:
    def __init__(self, chunks: tuple[Chunk, ...]) -> None:
        self._docs = [self._index(c) for c in chunks]
        n = len(self._docs)
        df: Counter = Counter()
        for d in self._docs:
            df.update(d.tf.keys())
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self._avg_len = sum(d.length for d in self._docs) / n

    @staticmethod
    def _index(chunk: Chunk) -> _Doc:
        tf: Counter = Counter()
        for term in _search_terms(chunk.text):
            tf[term] += 1
        for term in analyze(chunk.title):
            tf[term] += W_TITLE
        for alias in chunk.aliases:
            for term in analyze(alias):
                tf[term] += W_ALIAS
        for topic in chunk.topics:
            for term in analyze(topic.replace("_", " ")):
                tf[term] += W_TOPIC
        phrases = tuple(tuple(analyze(a)) for a in chunk.aliases if len(analyze(a)) > 1)
        return _Doc(chunk, tf, float(sum(tf.values())), phrases)

    def score(self, terms: list[str], all_terms: list[str]) -> list[tuple[float, float, Chunk]]:
        """(score, cobertura, trecho) em ordem decrescente de score.

        Cobertura = fração do peso (idf) dos termos da consulta presentes no
        manual que o trecho contém; termos que não existem em nenhum trecho
        não entram na conta.
        """
        known = {t for t in terms if t in self._idf}
        known_mass = sum(self._idf[t] for t in known)
        scored = []
        for doc in self._docs:
            total = matched = 0.0
            for term in known:
                f = doc.tf.get(term, 0)
                if f:
                    norm = f * (K1 + 1) / (f + K1 * (1 - B + B * doc.length / self._avg_len))
                    total += self._idf[term] * norm
                    matched += self._idf[term]
            if total > 0:
                total += PHRASE_BONUS * sum(1 for p in doc.phrases if _contains(all_terms, p))
            if doc.chunk.audience == INTERNAL:
                total *= INTERNAL_FACTOR
            scored.append((total, matched / known_mass if known_mass else 0.0, doc.chunk))
        scored.sort(key=lambda s: -s[0])
        return scored


def _contains(sequence: list[str], phrase: tuple[str, ...]) -> bool:
    n = len(phrase)
    return any(tuple(sequence[i:i + n]) == phrase for i in range(len(sequence) - n + 1))


@lru_cache(maxsize=1)
def _default_retriever() -> Retriever:
    return Retriever(load_manual().chunks)


def snippet(text: str, limit: int = MAX_SNIPPET) -> str:
    """Corta em fim de frase ou de palavra, no máximo `limit` caracteres."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    cut = cut[: end + 1] if end > limit // 2 else cut[: cut.rfind(" ")]
    return cut.rstrip() + " [...]"


def _result(score: float, chunk: Chunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "section": chunk.section,
        "title": chunk.title,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "score": round(score, 2),
        "audience": chunk.audience,
        "open_issues": list(chunk.open_issues),
        "text": snippet(chunk.text),
    }


def _envelope(status: str, query: str, results: list, notes: list[str], action: str) -> dict:
    return {"status": status, "source_type": SOURCE_TYPE, "query": query, "results": results,
            "notes": notes, "recommended_action": action}


def _strip_injection(query: str) -> tuple[str, bool]:
    if not _INJECTION.search(query):
        return query, False
    kept = [t for t in tokenize(query) if t not in _INJECTION_NOISE]
    return " ".join(kept), True


def search_store_policies(query: str, retriever: Retriever | None = None) -> dict:
    """Busca trechos do manual. Nunca levanta: falhas viram status 'error'."""
    try:
        if not isinstance(query, str) or not query.strip():
            return _envelope("not_found", str(query or ""), [], ["Consulta vazia."], "ask_clarification")
        text, injected = _strip_injection(query.strip())
        notes: list[str] = [_INJECTION_NOTE] if injected else []
        all_terms = analyze(text)
        terms = _search_terms(text)
        ranked = (retriever or _default_retriever()).score(terms, all_terms)
        gaps = [note for stems, note in _GAPS if stems & set(all_terms)]
        notes += gaps
        best, coverage, _ = ranked[0]
        if best < MIN_SCORE or coverage < MIN_COVERAGE:
            return _envelope("not_found", query, [], [_NO_MATCH_NOTE, *notes], "handoff_to_human")
        picked = [(s, c) for s, _, c in ranked[:MAX_RESULTS] if s >= max(MIN_SCORE, best * RELATIVE_CUTOFF)]
        # avisos do trecho principal; divergências que exigem humano valem para qualquer trecho
        issues = dict.fromkeys(
            i for rank, (_, c) in enumerate(picked) for i in c.open_issues if rank == 0 or i in _ESCALATE)
        notes += [_ISSUE_NOTES[i] for i in issues if i in _ISSUE_NOTES and i != "I-10"]
        if picked[0][1].audience == INTERNAL:
            notes.append(_ISSUE_NOTES["I-10"])
        status, action = "found", "answer_from_manual"
        if best < STRONG_SCORE and coverage < FULL_COVERAGE:
            status, action = "ambiguous", "ask_clarification"
            notes.append(_WEAK_NOTE)
        if gaps or issues.keys() & _ESCALATE:
            action = "handoff_to_human"
        return _envelope(status, query, [_result(s, c) for s, c in picked], notes, action)
    except DataError as exc:
        log.error("Manual indisponível: %s", exc)
        return {"status": "error", "source_type": SOURCE_TYPE, "reason": "data_error",
                "message": "Falha técnica ao consultar o manual de políticas.", "results": [], "notes": []}
    except Exception:  # noqa: BLE001 - a busca nunca levanta para quem chama
        log.exception("Erro inesperado na busca de políticas")
        return {"status": "error", "source_type": SOURCE_TYPE, "reason": "internal_error",
                "message": "Falha técnica ao consultar o manual de políticas.", "results": [], "notes": []}
