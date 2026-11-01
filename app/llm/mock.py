"""MockLLM: demonstração offline, determinística e sem chave.

NÃO é um modelo de linguagem. É uma política de palavras-chave que escolhe a
ferramenta, emite `tool_calls` de verdade e redige a resposta a partir do que a
ferramenta devolveu (nunca de memória). Serve para testar o fluxo e demonstrar o
atendimento sem rede; a qualidade de conversa de um LLM real não é representada.
"""
from __future__ import annotations

import json
import re
import unicodedata

from app.llm.base import LLMResponse, Message, ToolCall

_CATEGORIES = {"violao": "violão", "violoes": "violão", "guitarra": "guitarra", "guitarras": "guitarra",
               "baixo": "baixo", "baixos": "baixo", "bateria": "bateria", "baterias": "bateria",
               "teclado": "teclado", "teclados": "teclado", "piano": "piano", "ukulele": "ukulele",
               "ukuleles": "ukulele", "saxofone": "saxofone", "flauta": "flauta"}
_ACCESSORY = ("corda", "palheta", "cabo", "capa", "case", "pedal", "pedais", "afinador", "amplificador",
              "suporte")
_STORE_TOPICS = (("horario", "hours"), ("funcionamento", "hours"), ("que horas", "hours"), ("abre", "hours"), ("endereco", "address"),
                 ("onde fica", "address"), ("localizacao", "address"), ("telefone", "contacts"),
                 ("whatsapp", "contacts"), ("contato", "contacts"), ("email", "contacts"))
_POLICY_WORDS = ("devol", "troca", "trocar", "arrepend", "garantia", "defeito", "politica", "pagamento",
                 "pix", "boleto", "entrega", "prazo", "cancel", "reembolso", "estorno", "privacidade")
_FILLER = {"qual", "o", "a", "os", "as", "preco", "valor", "do", "da", "de", "quanto", "custa", "voces",
           "tem", "no", "na", "um", "uma", "gostaria", "saber", "queria", "me", "diga", "esta", "estao",
           "disponivel", "estoque", "ainda", "e", "por", "favor", "pra", "para", "ver", "quero", "sobre",
           "vcs", "ola", "oi", "bom", "dia", "tarde", "noite", "preco", "e"}
_PHONE = r"\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}"
_EMAIL = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _user_texts(messages: list[Message]) -> list[str]:
    return [m["content"] for m in messages if m["role"] == "user"]


def _money(text: str) -> float | None:
    m = re.search(r"r\$\s*([\d.]+(?:,\d{1,2})?)", text)
    if m:
        return float(m.group(1).replace(".", "").replace(",", "."))
    m = re.search(r"\b(\d{1,3}(?:\.\d{3})+|\d{3,6})\b", text)
    return float(m.group(1).replace(".", "")) if m else None


def _price_cap(text: str) -> float | None:
    """'até mil reais', 'até 1500', 'até R$ 800', 'até 2 mil'."""
    if re.search(r"(?:ate|menos de)\s+mil\b", text):
        return 1000.0
    m = re.search(r"(?:ate|menos de|no maximo)\s+(?:r\$\s*)?(\d+(?:[.,]\d+)?)\s*(mil)?", text)
    if not m:
        return None
    value = float(m.group(1).replace(".", "").replace(",", ".")) if not m.group(2) \
        else float(m.group(1).replace(",", ".")) * 1000
    return value


def _category_in(text: str) -> str | None:
    for word in re.findall(r"[a-z]+", text):
        if word in _CATEGORIES:
            return _CATEGORIES[word]
    return None


def _call(i: int, name: str, args: dict) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=f"mock_{i}", name=name, arguments=args)])


class MockLLM:
    """Política de intenção por palavras-chave; ver docstring do módulo."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: list[Message], tools: list[dict]) -> LLMResponse:
        self.calls += 1
        last_user = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=-1)
        results = [m for m in messages[last_user + 1:] if m["role"] == "tool"]
        if results:
            return LLMResponse(text=self._compose(results))
        return self._route(messages)

    # --- decisão -----------------------------------------------------------
    def _route(self, messages: list[Message]) -> LLMResponse:
        texts = _user_texts(messages)
        raw = texts[-1] if texts else ""
        text = _norm(raw)
        history = [_norm(t) for t in texts[:-1]]
        n = self.calls

        if re.search(r"ignore|esqueca|instrucoes anteriores|prompt|suas regras|suas ferramentas", text):
            return LLMResponse(text="Isso eu não consigo fazer. Posso ajudar com instrumentos, preços, "
                                    "estoque, pedidos ou as políticas da loja. Como posso ajudar?")
        order = self._order_call(text, history, n)
        if order:
            return order
        words = set(re.findall(r"[a-z]+", text))
        if any(w.startswith(a) for a in _ACCESSORY for w in words) and not re.search(r"\d\s*cordas", text):
            return _call(n, "search_products", {"query": raw})
        if any(w in text for w in _POLICY_WORDS):
            return _call(n, "search_store_policies", {"query": raw})
        for key, topic in _STORE_TOPICS:
            if re.search(r"\b" + key, text):
                return _call(n, "get_store_info", {"topic": topic})
        if "promo" in text or "desconto" in text or "oferta" in text:
            return _call(n, "get_promotions", {})
        if "parcel" in text and _money(text):
            return _call(n, "check_installments", {"amount": _money(text)})
        if "frete" in text and _money(text):
            return _call(n, "check_shipping", {"order_total": _money(text)})
        received = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if received and ("receb" in text or "chegou" in text):
            return _call(n, "check_return_eligibility", {"received_date": received.group(1)})
        if "parcel" in text or "frete" in text:
            return _call(n, "search_store_policies", {"query": raw})
        product = self._product_call(text, history, n)
        if product:
            return product
        return LLMResponse(text="Sou o assistente virtual do Empório da Música e cuido de instrumentos "
                                "musicais: catálogo, preços, estoque, pedidos e políticas da loja. "
                                "Em que posso ajudar?")

    @staticmethod
    def _order_call(text: str, history: list[str], n: int) -> LLMResponse | None:
        context = " ".join(history + [text])
        if "pedido" not in context or not re.search(r"pedido|#\d|@|\d{8,}", text):
            return None
        oid = re.findall(r"(?:pedido|numero|#)\s*(?:n[o°º]\s*)?#?(\d{1,9})", context)
        email = re.findall(_EMAIL, context)
        phone = re.findall(_PHONE, context)
        if oid and (email or phone):
            return _call(n, "get_order_status",
                         {"order_id": int(oid[-1]), "verification": (email or phone)[-1]})
        return LLMResponse(text="Consigo sim! Pra consultar o pedido preciso do número dele e do e-mail "
                                "ou telefone cadastrado na compra, só pra confirmar que é você.")

    @staticmethod
    def _product_call(text: str, history: list[str], n: int) -> LLMResponse | None:
        category = _category_in(text)
        cap = _price_cap(text)
        if category is None and cap is not None:
            category = next((c for c in map(_category_in, reversed(history)) if c), None)
        listing = re.search(r"\b(quais|opcoes|mostre|lista|tem)\b", text)
        if cap is not None or (category and listing):
            args: dict = {"available_only": True, "sort": "price_asc", "limit": 6}
            if category:
                args["category"] = category
            if cap is not None:
                args["price_max"] = cap
            return _call(n, "search_products", args)
        asks_product = re.search(r"preco|valor|quanto|custa|estoque|disponivel|\btem\b", text) \
            or re.search(r"[a-z]+\s*[a-z]*\d+", text)
        if asks_product:
            words = [w for w in re.findall(r"[a-z0-9-]+", text) if w not in _FILLER]
            if words:
                return _call(n, "search_products", {"query": " ".join(words)})
        return None

    # --- redação a partir dos resultados --------------------------------------
    def _compose(self, results: list[Message]) -> str:
        parts = []
        for msg in results:
            try:
                payload = json.loads(msg["content"])
            except (ValueError, TypeError):
                payload = {}
            payload = payload if isinstance(payload, dict) else {}
            data = payload.get("data", {})
            parts.append(self._compose_one(payload.get("tool", ""), data if isinstance(data, dict) else {}))
        return "\n\n".join(p for p in parts if p)

    def _compose_one(self, tool: str, d: dict) -> str:
        if d.get("status") == "error":
            return ("Não consegui consultar isso agora. Tente de novo em instantes ou fale com a loja "
                    "pelo (67) 3341-4444.")
        handlers = {"search_products": self._products, "check_product_availability": self._products,
                    "get_promotions": self._promotions, "get_order_status": self._order,
                    "search_store_policies": self._policies, "check_installments": self._installments,
                    "check_shipping": self._shipping, "check_return_eligibility": self._return,
                    "get_store_info": self._store}
        handler = handlers.get(tool)
        return handler(d) if handler else "Não consegui interpretar o resultado da consulta."

    @staticmethod
    def _line(p: dict) -> str:
        promo = p.get("promotion")
        price = p["price_display"]
        if promo:
            price = (f"de {promo['original_price_display']} por {promo['promotional_price_display']} "
                     f"({promo['discount_percent']}% off)")
        return f"{p['name']}: {price} ({p['availability_label'].lower()})"

    def _products(self, d: dict) -> str:
        status = d.get("status")
        if status == "not_found":
            if d.get("reason") == "out_of_scope_accessory":
                return ("A gente vende só instrumentos musicais, sem acessórios como cordas, palhetas "
                        "ou cabos. Posso te ajudar com algum instrumento?")
            return "Não encontrei esse produto no catálogo. Quer tentar outro nome ou ver uma categoria?"
        if "product" in d:
            return f"Encontrei: {self._line(d['product'])}."
        items = d.get("products") or d.get("candidates") or []
        if not items:
            return "Não encontrei opções com esses critérios."
        if len(items) == 1 and status == "found":
            return f"Encontrei: {self._line(items[0])}."
        head = "Encontrei mais de uma opção, qual delas você quer?" if status == "ambiguous" \
            else "Olha o que tenho:"
        shown = items[:6]
        more = (f"\n(Mostrando {len(shown)} de {d['total_matches']}.)"
                if d.get("total_matches", 0) > len(shown) else "")
        return head + "\n" + "\n".join(f"- {self._line(p)}" for p in shown) + more

    @staticmethod
    def _promotions(d: dict) -> str:
        promos = d.get("promotions") or []
        if not promos:
            return "No momento não há promoções ativas."
        lines = [f"- {p['name']}: de {p['original_price_display']} por {p['promotional_price_display']} "
                 f"({p['discount_percent']}% off)" for p in promos]
        return "Promoções ativas:\n" + "\n".join(lines) + "\nO desconto do PIX não soma com preço promocional."

    @staticmethod
    def _order(d: dict) -> str:
        status = d.get("status")
        if status == "verification_required":
            return "Preciso do e-mail ou telefone cadastrado no pedido pra consultar."
        if status != "found":
            return ("Não consegui confirmar esses dados para o pedido. Confere o número e o e-mail ou "
                    "telefone e tenta de novo?")
        items = ", ".join(f"{i['quantity']}x {i['name']}" for i in d["items"])
        out = (f"Pedido {d['order_id']}: {d['order_status_label'].lower()}. Itens: {items}. "
               f"Total registrado: {d['total_display']} ({d['payment_method_label']}).")
        if d.get("tracking_code"):
            out += f" Rastreio: {d['tracking_code']}."
        if d.get("estimated_delivery"):
            out += f" Previsão: {d['estimated_delivery']}."
        if d.get("notes"):
            out += f" Observação do pedido: {d['notes']}"
        return out

    @staticmethod
    def _policies(d: dict) -> str:
        if d.get("status") != "found" or not d.get("results"):
            return ("Isso eu não encontrei nas políticas da loja. Melhor falar com um atendente pelo "
                    "(67) 3341-4444.")
        text = d["results"][0]["text"]
        out = re.sub(r"^\d+(?:\.\d+)*\.?\s+(?=[A-ZÀ-Ú])", "", text).strip()
        if d.get("recommended_action") == "handoff_to_human" or d.get("notes"):
            out += "\nHá pontos que o material da loja não deixa claros; um atendente confirma pra você."
        return out

    @staticmethod
    def _installments(d: dict) -> str:
        if d.get("status") != "ok":
            return "Não consegui calcular o parcelamento. Vale confirmar com a loja."
        return (f"Dá pra parcelar em até {d['max_installments']}x sem juros "
                f"(parcelas de R$ {d['installment_value_brl'].replace('.', ',')}).")

    @staticmethod
    def _shipping(d: dict) -> str:
        fee = d.get("shipping_fee_brl")
        if d.get("status") == "region_required":
            return "O frete depende da cidade. Você está em Campo Grande ou região metropolitana?"
        if fee is None:
            return "Não consegui calcular o frete; um atendente confirma pra você."
        return "Frete grátis!" if float(fee) == 0 else f"O frete fica R$ {fee.replace('.', ',')}."

    @staticmethod
    def _return(d: dict) -> str:
        labels = {"within_deadline": f"Está dentro do prazo de arrependimento (até {d.get('deadline_date')}).",
                  "borderline": "Está no limite do prazo; um atendente precisa confirmar.",
                  "outside_deadline": "Passou do prazo de arrependimento de 7 dias.",
                  "not_received_yet": "O prazo só começa a contar depois do recebimento."}
        return labels.get(d.get("status"), "Não consegui verificar o prazo; fale com um atendente.")

    @staticmethod
    def _store(d: dict) -> str:
        info = d.get("info", {})
        out = []
        if "address" in info:
            out.append(f"Endereço: {info['address']['value']}.")
        if "hours" in info:
            h = info["hours"]["value"]
            out.append(f"Horário: seg a sex {h['seg_a_sex']}, sábado {h['sabado']}, "
                       "domingo e feriados fechado.")
        if "contacts" in info:
            c = info["contacts"]
            out.append(f"Contato: {c['phone']['value']} e WhatsApp {c['whatsapp']['value']} "
                       "(o material da loja traz dois números; vale confirmar), "
                       f"e-mail {c['email']['value']}.")
        return " ".join(out) or "Não tenho essa informação."
