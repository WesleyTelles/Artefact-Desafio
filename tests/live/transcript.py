"""Gera transcrições em Markdown dos cenários, com e-mails e telefones de clientes mascarados."""
from __future__ import annotations

import json
import re
import unicodedata

from app.agent.orchestrator import _EMAIL_RE, _PHONE_RE, _digits, _store_contacts
from app.tools.orders import mask_email, mask_phone
from tests.live.harness import Run, Scenario


def mask(text: str) -> str:
    """Mascara e-mail/telefone que não sejam os contatos da loja."""
    phones, emails = _store_contacts()

    def _email(m: re.Match) -> str:
        return m.group(0) if m.group(0).lower() in emails else mask_email(m.group(0))

    def _phone(m: re.Match) -> str:
        d = _digits(m.group(0))
        if d in phones:
            return m.group(0)
        return mask_phone(m.group(0)) if len(d) >= 10 else "****-" + d[-4:]

    return _PHONE_RE.sub(_phone, _EMAIL_RE.sub(_email, text))


def visible(text: str) -> str:
    """Troca caracteres de controle e invisíveis por escapes (\\uXXXX) para o Markdown ficar legível."""
    return "".join(f"\\u{ord(c):04x}" if c != "\n" and unicodedata.category(c) in ("Cc", "Cf") else c
                   for c in text)


def summarize(name: str, result: dict) -> str:
    status = result.get("status")
    rows = result.get("products") or result.get("candidates")
    if rows:
        shown = "; ".join(f"{r['product_id']} {r['name'].split(' -- ')[0]} {r['price_display']} "
                          f"({r['availability']})" for r in rows[:6])
        more = f" (+{len(rows) - 6})" if len(rows) > 6 else ""
        return f"{status}: {shown}{more}"
    if name == "get_order_status" and status == "found":
        return (f"found: pedido {result['order_id']} {result['order_status']} total {result['total_display']} "
                f"itens {[i['name'] for i in result['items']]}")
    if "reason" in result or "message" in result:
        return f"{status}: {result.get('reason', '')} {str(result.get('message', ''))[:120]}".strip()
    return f"{status}: " + json.dumps(result, ensure_ascii=False, default=str)[:200]


def render(scenario: Scenario, run: Run, failures: list[str], verdict: str, *,
           run_number: int | None = None, record: dict | None = None) -> str:
    title = f"{scenario.id} - {scenario.name}" + (f" (execução {run_number})" if run_number else "")
    lines = [f"# {title}", "",
             f"- Resultado: **{verdict}**",
             f"- Requisições ao LLM: {run.llm_requests}",
             "- Dados: apenas a base fictícia da loja; e-mails e telefones de clientes mascarados."]
    if record is not None:
        lines += [f"- Esperado: {scenario.expected}",
                  f"- Ferramenta esperada acionada: {record['tool_ok']}",
                  f"- Informação inventada (preço/prazo/número fora dos dados): {record['invented'] or 'nenhuma'}",
                  f"- Latência total: {record['latency_ms']} ms; tentativas ao provedor: {record['llm_attempts']}; "
                  f"tokens: {record['tokens']}"]
    if scenario.fail_tool:
        lines.append(f"- Falha injetada na ferramenta `{scenario.fail_tool}`.")
    if scenario.inject:
        lines.append("- Texto malicioso injetado no resultado da ferramenta de busca.")
    if run.llm_errors:
        lines.append(f"- Erros do LLM: {', '.join(run.llm_errors)}")
    if failures:
        lines += ["- Falhas das asserções:"] + [f"  - {mask(f)}" for f in failures]
    for i, turn in enumerate(run.turns, 1):
        question = visible(mask(turn.question)).replace("\n", " ")
        lines += ["", f"## Turno {i}", "", "**Cliente:**", "", "> " + question[:400]]
        if len(question) > 400:
            lines.append(f"> (mensagem com {len(turn.question)} caracteres, truncada aqui)")
        lines += ["", "**Ferramentas:**", ""]
        if not turn.calls:
            lines.append("- nenhuma")
        for name, args, result in turn.calls:
            lines.append(f"- `{name}({mask(json.dumps(args, ensure_ascii=False))})` -> "
                         f"{mask(summarize(name, result))}")
        lines += ["", "**Resposta final:**", ""] + ["> " + ln for ln in mask(turn.text).splitlines()]
    return "\n".join(lines) + "\n"
