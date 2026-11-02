"""Interface de linha de comando: loop de chat no terminal."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from app.agent.orchestrator import _EMAIL_RE, _PHONE_RE, Agent, AgentReply
from app.core.config import load_env_file, load_llm_settings
from app.core.exceptions import DataError
from app.data.loader import get_store
from app.llm.base import LLMError
from app.llm.factory import create_client
from app.tools.orders import mask_email, mask_phone

GREETING = ("Olá! Sou o assistente virtual do Empório da Música. Posso ajudar com instrumentos, preços, "
            "estoque, pedidos e políticas da loja.")
HELP = "Comandos: /sair encerra, /limpar apaga a conversa."
EXIT_COMMANDS = {"/sair", "/exit", "/quit"}


def _setup_encoding() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _mask_text(text: str) -> str:
    text = _EMAIL_RE.sub(lambda m: mask_email(m.group(0)), text)
    return _PHONE_RE.sub(lambda m: mask_phone(m.group(0)), text)


def mask_arguments(value: Any, key: str = "") -> Any:
    """Cópia dos argumentos com e-mails e telefones mascarados (nomes de campos e tipos ficam)."""
    if isinstance(value, dict):
        return {k: mask_arguments(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_arguments(v, key) for v in value]
    if isinstance(value, str):
        if key == "verification":  # campo de identificação: mascara inteiro, mesmo sem formato reconhecível
            return mask_email(value) if "@" in value else mask_phone(value)
        return _mask_text(value)
    return value


def format_trace(trace: list[dict]) -> list[str]:
    lines = []
    for item in trace:
        args = json.dumps(mask_arguments(item["arguments"]), ensure_ascii=False)
        suffix = " (repetida, resultado reaproveitado)" if item.get("cached") else ""
        lines.append(f"  [ferramenta] {item['name']}({args}) -> {item['status']}{suffix}")
    return lines


def _write_stderr(line: str) -> None:
    print(line, file=sys.stderr)


def operator_lines(reply: AgentReply, debug: bool) -> list[str]:
    """Diagnóstico para o operador (stderr), nunca para o cliente.

    A dica de configuração (auth, modelo/URL, config) aparece sempre que houver; a categoria
    técnica de qualquer falha aparece com --debug.
    """
    lines = []
    if reply.operator_hint:
        lines.append(f"[operador] {reply.error_category}: {reply.operator_hint}")
    elif debug and reply.error_category:
        lines.append(f"[operador] falha técnica: {reply.error_category}")
    return lines


def run_chat(agent: Agent, *, read: Callable[[str], str] = input, write: Callable[[str], None] = print,
             debug: bool = False, banner: str = "",
             write_err: Callable[[str], None] = _write_stderr) -> None:
    if banner:
        write(banner)
    write(GREETING)
    write(HELP)
    while True:
        try:
            line = read("\nVocê: ")
        except (EOFError, KeyboardInterrupt):
            write("\nAté mais!")
            return
        command = line.strip().lower()
        if command in EXIT_COMMANDS:
            write("Até mais!")
            return
        if command == "/limpar":
            agent.reset()  # memória e contador da sessão; bloqueio por pedido persiste (ver Agent.reset)
            write("Conversa limpa.")
            continue
        if not command:
            continue
        reply = agent.reply(line)
        for row in operator_lines(reply, debug):
            write_err(row)
        if debug:
            for row in format_trace(reply.trace):
                write(row)
        write(f"\nAtendente: {reply.text}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="Atendimento do Empório da Música (terminal).")
    parser.add_argument("--mock", action="store_true",
                        help="demonstração offline por palavras-chave, sem LLM nem chave (não é um LLM)")
    parser.add_argument("--debug", action="store_true", help="mostra as ferramentas chamadas (e-mails/telefones mascarados) e a categoria de falhas")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_encoding()
    load_env_file()
    try:
        get_store()  # falha cedo se os dados estiverem inválidos
    except DataError as exc:
        print(f"Erro ao carregar os dados da loja: {exc}", file=sys.stderr)
        return 2
    try:
        settings = load_llm_settings("mock" if args.mock else None)
        client = create_client(settings)
    except LLMError as exc:
        print(f"Erro de configuração: {exc}. Veja .env.example ou use --mock para a demonstração.",
              file=sys.stderr)
        return 2
    banner = ("[modo demonstração: respostas por palavras-chave, sem LLM]" if settings.provider == "mock"
              else f"[provedor: {settings.provider}, modelo: {settings.model}]")
    run_chat(Agent(client), debug=args.debug, banner=banner)
    return 0
