"""Interface de linha de comando: loop de chat no terminal."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Callable

from app.agent.orchestrator import Agent
from app.core.config import load_env_file, load_llm_settings
from app.core.exceptions import DataError
from app.data.loader import get_store
from app.llm.base import LLMError
from app.llm.factory import create_client

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


def format_trace(trace: list[dict]) -> list[str]:
    lines = []
    for item in trace:
        args = json.dumps(item["arguments"], ensure_ascii=False)
        suffix = " (repetida, resultado reaproveitado)" if item.get("cached") else ""
        lines.append(f"  [ferramenta] {item['name']}({args}) -> {item['status']}{suffix}")
    return lines


def run_chat(agent: Agent, *, read: Callable[[str], str] = input, write: Callable[[str], None] = print,
             debug: bool = False, banner: str = "") -> None:
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
            agent.reset()
            write("Conversa limpa.")
            continue
        if not command:
            continue
        reply = agent.reply(line)
        if debug:
            for row in format_trace(reply.trace):
                write(row)
        write(f"\nAtendente: {reply.text}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="Atendimento do Empório da Música (terminal).")
    parser.add_argument("--mock", action="store_true",
                        help="demonstração offline por palavras-chave, sem LLM nem chave (não é um LLM)")
    parser.add_argument("--debug", action="store_true", help="mostra as ferramentas chamadas e os argumentos")
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
