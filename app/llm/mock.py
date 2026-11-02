"""MockLLM: demonstração offline, determinística e sem chave.

NÃO é um modelo de linguagem e NÃO representa o comportamento do agente com Gemini (ou outro
LLM real). É uma política de INTENÇÕES simples: normaliza o texto (minúsculas, sem acento),
divide perguntas compostas em trechos, classifica cada trecho por listas de sinônimos e regras
claras, extrai parâmetros (categoria, teto/piso de preço, número do pedido, e-mail/telefone,
valor, data) e emite `tool_calls` reais (várias na mesma rodada, se for composta). A resposta
é redigida só a partir do que as ferramentas devolveram: not_found, ambiguous, error, locked e
verification_failed são refletidos como tal; nada de preço, estoque ou prazo vem de memória.

Quando não entende, pede para reformular e lista o que sabe fazer (não chuta ferramenta).

Limitações conhecidas (sem NLP, só regras):
- Frases com sinônimos fora das listas ou muito indiretas caem em "pode reformular?".
  Ex.: "quero algo grave pra tocar no coro da igreja" (sem categoria nem palavra-chave).
- Contexto básico: só reaproveita a categoria do histórico (para teto/piso de preço) e o
  número do pedido/e-mail já ditos. "e o preço dele?" ou "esse tem estoque?" (referência a
  produto citado antes) não é resolvido.
- Em perguntas compostas, cada trecho vira no máximo uma ferramenta; "preço do X e do Y" num
  trecho só vira uma consulta única e pode voltar "não encontrei".
- Política: usa o trecho inteiro como consulta e mostra o primeiro resultado do manual; não
  sintetiza nem compara seções.
- Produto sem marca/modelo reconhecível (ex.: "aquele violão vermelho") vira listagem por
  categoria ou pedido de reformulação.
"""
from __future__ import annotations

import json
import re
import unicodedata

from app.llm.base import LLMResponse, Message, ToolCall

_CATEGORIES = {"violao": "violão", "violoes": "violão", "guitarra": "guitarra", "guitarras": "guitarra",
               "baixo": "baixo", "baixos": "baixo", "contrabaixo": "baixo", "bateria": "bateria",
               "baterias": "bateria", "teclado": "teclado", "teclados": "teclado", "piano": "piano",
               "pianos": "piano", "ukulele": "ukulele", "ukuleles": "ukulele", "saxofone": "saxofone",
               "saxofones": "saxofone", "flauta": "flauta", "flautas": "flauta", "violino": "violino",
               "violinos": "violino"}
_BRANDS = {"yamaha", "takamine", "martin", "taylor", "tagima", "giannini", "crafter", "rozini", "shelby",
           "fender", "gibson", "ibanez", "kala", "kalani", "ohana", "prs"}
_ACCESSORY = {"corda", "palheta", "cabo", "capa", "case", "pedal", "afinador", "amplificador", "suporte",
              "estojo", "correia", "banqueta", "metronomo", "microfone"}
_FILLER = set("""qual quais o a os as um uma uns umas do da dos das de em no na nos nas por pra para com sem
e ou que quanto quanta custa custam preco valor precos valores sai fica ficam sao tem tenho temos tinha
voce voces vcs vc ola oi bom boa dia tarde noite gostaria saber queria quero ver me diga dizer fala esta
estao disponivel disponiveis estoque ainda favor poderia pode podem mostre mostra mostrar lista listar
opcoes vende vendem vendo trabalha trabalham possui possuem loja existe existem ha aqui la tambem so
apenas dele dela deles desse dessa esse essa isso aquele aquela ate abaixo acima menos mais mil reais real r barato baratos""".split())
_STORE_TOPICS = ((r"horario|que horas|\babre\b|\bfecha\b|aberto|funcionamento|sabado|domingo|feriado", "hours"),
                 (r"endereco|onde fica|localizacao|como chegar|onde voces ficam", "address"),
                 (r"telefone|whatsapp|zap|contato|ligar", "contacts"))
_NOT_STORE = re.compile(r"entreg|devol|troca|garantia|pedido")
_POLICY = re.compile(
    r"devol|troca|trocar|arrepend|garantia|defeito|politica|pagamento|pagar|pix|boleto|cartao|credito|"
    r"entreg|envi|correio|sedex|jadlog|prazo|cancel|reembols|estorno|dinheiro de volta|privacidade|lgpd|"
    r"nota fiscal|retirar|retirada|quebr|estrag|danific|nao funciona|parcel|frete|desconto")
_OFF_TOPIC = re.compile(r"\b(copa do mundo|copa|futebol|campeonato|quem ganhou|presidente|eleicao|"
                        r"receita de|previsao do tempo|clima|horoscopo|novela|filme|bitcoin|"
                        r"bolsa de valores|capital d[aeo]s?|piada|poema|programar|python|matematica)\b")
_INJECTION = re.compile(r"ignore|esqueca|instrucoes anteriores|prompt|suas regras|suas ferramentas|"
                        r"modo desenvolvedor")
_SPLIT = re.compile(r"[?;!]+|\s+e\s+(?=(?:o|a|os|as|qual|quais|que|quem|tambem|como|voces|vcs|ate|onde|quanto|horario|"
                    r"endereco|telefone|preco|valor|frete)\b)|"
                    r"\s+alem disso\s+")
_EMAIL = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
_PHONE = r"\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}"
_REFUSE_INJECTION = ("Isso eu não consigo fazer. Posso ajudar com instrumentos, preços, estoque, pedidos "
                     "ou as políticas da loja. Como posso ajudar?")
_REFUSE_OFF_TOPIC = ("Isso foge do que eu consigo ajudar por aqui: cuido de instrumentos musicais, preços, "
                     "estoque, pedidos e políticas do Empório da Música. Posso ajudar com algo da loja?")
_REPHRASE = ('Não entendi bem o pedido. Pode reformular? Eu sei: consultar preço e estoque de instrumentos '
             '(ex.: "preço da Takamine GD20"), listar por categoria e faixa de preço, promoções, status '
             'de pedido (preciso do número e do e-mail ou telefone), parcelamento, frete, prazo de '
             'arrependimento, políticas da loja, horário, endereço e contato.')
_GREETING = ("Olá! Sou o assistente do Empório da Música. Posso ajudar com instrumentos, preços, estoque, "
             "pedidos e políticas da loja. O que você precisa?")
_NOTE_OFF = "Sobre o restante da pergunta: isso foge do que eu consigo ajudar, só cuido da loja e dos instrumentos."
_ORDER_ASK = ("Consigo sim! Pra consultar o pedido preciso do número dele e do e-mail ou telefone "
              "cadastrado na compra, só pra confirmar que é você.")


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


def _bound(text: str, words: str) -> float | None:
    """Valor após uma expressão de limite ('ate mil', 'ate 2 mil', 'acima de R$ 800')."""
    if re.search(rf"(?:{words})\s+mil\b", text):
        return 1000.0
    m = re.search(rf"(?:{words})\s+(?:r\$\s*)?(\d+(?:[.,]\d+)?)\s*(mil)?", text)
    if not m:
        return None
    if m.group(2):
        return float(m.group(1).replace(",", ".")) * 1000
    return float(m.group(1).replace(".", "").replace(",", "."))


def _category_in(text: str) -> str | None:
    for word in re.findall(r"[a-z]+", text):
        if word in _CATEGORIES:
            return _CATEGORIES[word]
    return None


def _is_accessory(words: list[str], text: str) -> bool:
    if re.search(r"\d\s*cordas", text):
        return False
    return any(w in _ACCESSORY or w.rstrip("s") in _ACCESSORY for w in words)


def _tool_calls(prefix: str, calls: list[tuple[str, dict]]) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=f"{prefix}_{k}", name=name, arguments=args)
                                   for k, (name, args) in enumerate(calls)])


class MockLLM:
    """Política de intenção por regras; ver docstring do módulo."""

    def __init__(self) -> None:
        self.calls = 0
        self._note = ""

    def chat(self, messages: list[Message], tools: list[dict]) -> LLMResponse:
        self.calls += 1
        last_user = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=-1)
        results = [m for m in messages[last_user + 1:] if m["role"] == "tool"]
        if results:
            text = self._compose(results)
            note, self._note = self._note, ""
            return LLMResponse(text=f"{text}\n\n{note}" if note else text)
        return self._route(messages)

    # --- decisão -----------------------------------------------------------
    def _route(self, messages: list[Message]) -> LLMResponse:
        texts = _user_texts(messages)
        raw = texts[-1] if texts else ""
        text = _norm(raw)
        history = [_norm(t) for t in texts[:-1]]
        self._note = ""
        if _INJECTION.search(text):
            return LLMResponse(text=_REFUSE_INJECTION)
        order = self._order_call(text, history, self.calls)
        if order is not None:
            return order
        calls: list[tuple[str, dict]] = []
        off_topic = False
        for seg in (s.strip() for s in _SPLIT.split(text) if s and s.strip()):
            if _OFF_TOPIC.search(seg):
                off_topic = True
                continue
            call = self._segment_call(seg, history)
            if call and call not in calls:
                calls.append(call)
        if calls:
            self._note = _NOTE_OFF if off_topic else ""
            return _tool_calls(f"mock_{self.calls}", calls)
        if off_topic:
            return LLMResponse(text=_REFUSE_OFF_TOPIC)
        if re.fullmatch(r"\W*(oi+|ola|bom dia|boa tarde|boa noite|obrigad[oa]|valeu|tchau)\W*", text):
            return LLMResponse(text=_GREETING)
        return LLMResponse(text=_REPHRASE)

    @staticmethod
    def _order_call(text: str, history: list[str], n: int) -> LLMResponse | None:
        """Pedido: só chama a ferramenta com número E verificação digitados pelo cliente."""
        context = " ".join(history + [text])
        if "pedido" not in context or not re.search(r"pedido|#\d|@|\d{8,}", text):
            return None
        oid = re.findall(r"(?:pedido|compra|numero|#)\s*(?:n[o°º]\s*)?#?(\d{1,9})", context)
        email = re.findall(_EMAIL, context)
        phone = re.findall(_PHONE, context)
        if oid and (email or phone):
            return _tool_calls(f"mock_{n}", [("get_order_status",
                                              {"order_id": int(oid[-1]), "verification": (email or phone)[-1]})])
        return LLMResponse(text=_ORDER_ASK)

    def _segment_call(self, text: str, history: list[str]) -> tuple[str, dict] | None:
        words = re.findall(r"[a-z0-9]+", text)
        if _is_accessory(words, text):
            return "search_products", {"query": text}
        if not _NOT_STORE.search(text):
            for pattern, topic in _STORE_TOPICS:
                if re.search(pattern, text):
                    return "get_store_info", {"topic": topic}
        if re.search(r"promo|oferta|liquidacao", text) or ("desconto" in text and "pix" not in text):
            return "get_promotions", {}
        money = _money(text)
        if money and re.search(r"parcel|vezes|\d+x\b", text):
            return "check_installments", {"amount": money}
        if money and "frete" in text:
            args: dict = {"order_total": money}
            if "campo grande" in text:
                args["in_metropolitan_region"] = True
            return "check_shipping", args
        received = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if received and re.search(r"receb|chegou|entreg", text):
            return "check_return_eligibility", {"received_date": received.group(1)}
        if _POLICY.search(text):
            return "search_store_policies", {"query": text}
        return self._product_call(text, words, history)

    @staticmethod
    def _product_call(text: str, words: list[str], history: list[str]) -> tuple[str, dict] | None:
        category = _category_in(text)
        cap = _bound(text, "ate|menos de|abaixo de|no maximo|por ate|de ate")
        floor = _bound(text, "acima de|a partir de|mais de|no minimo")
        has_price_bound = cap is not None or floor is not None
        if category is None and has_price_bound:
            category = next((c for c in map(_category_in, reversed(history)) if c), None)
        stripped = re.sub(r"(?:ate|menos de|abaixo de|no maximo|por ate|de ate|acima de|a partir de|mais de|"
                          r"no minimo)\s+(?:r\$\s*)?\d[\d.,]*\s*(?:mil)?", " ", text)
        tokens = [w for w in re.findall(r"[a-z0-9]+", stripped) if w not in _FILLER and w not in _CATEGORIES]
        asks = re.search(r"preco|valor|custa|quanto|sai|fica|estoque|disponivel|tem|vende|trabalha", text)
        named = bool(tokens) and (asks or any(w in _BRANDS or re.search(r"[a-z]\d|\d[a-z]", w) for w in tokens))
        args: dict = {}
        if named:
            args["query"] = " ".join(tokens)
        elif category:
            args.update({"available_only": True, "limit": 6,
                         "sort": "price_desc" if "mais caro" in text else "price_asc"})
        else:
            return None
        if category:
            args["category"] = category
        if cap is not None:
            args["price_max"] = cap
        if floor is not None:
            args["price_min"] = floor
        return "search_products", args

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
        if status == "locked":
            return ("Muitas tentativas de verificação sem sucesso. Para consultar pedidos, fale com a loja "
                    "pelo (67) 3341-4444.")
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
        if d.get("status") not in ("found", "ambiguous") or not d.get("results"):
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
        days = d.get("window_days")
        labels = {"within_deadline": f"Está dentro do prazo de arrependimento (até {d.get('deadline_date')}).",
                  "borderline": "Está no limite do prazo; um atendente precisa confirmar.",
                  "outside_deadline": f"Passou do prazo de arrependimento de {days} dias.",
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
