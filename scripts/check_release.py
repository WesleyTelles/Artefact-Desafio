"""Verificador de publicação (somente leitura). Uso, a partir da raiz do repositório:

    python scripts/check_release.py              # checagens básicas (segredos, .env, claude)
    python scripts/check_release.py --history    # inclui caminhos de TODAS as revisões
    python scripts/check_release.py --public     # + falha se arquivos RESTRITOS estiverem rastreados
    python scripts/check_release.py --public --allow-csv   # idem, aceitando os CSVs de data/

Sai com código 1 se encontrar problema; 0 se estiver tudo certo. Não altera nada, não imprime
valores de segredos (só contagens e caminhos) e lê o .env apenas em memória.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Arquivos que NÃO devem ir ao repositório público sem autorização da Artefact (ver docs/PUBLICACAO.md).
RESTRICTED = {
    # manual marcado "Documento interno — Uso restrito"
    "data/políticas_da_loja.pdf": "manual interno (uso restrito)",
    "docs/challenge/politicas_extraido.txt": "texto extraído do manual interno",
    # enunciado do desafio
    "docs/challenge/desafio_tecnico_ai_eng_artefact.pdf": "enunciado do desafio",
}
# Base de dados fornecida (fictícia); redistribuição depende de autorização. Aceitável com --allow-csv.
RESTRICTED_CSV_PREFIX = "data/desafio_tecnico_ai_eng - "

SECRET_PATTERNS = {
    "chave Google (AIza...)": re.compile(rb"AIza[0-9A-Za-z_\-]{20,}"),
    "chave sk-...": re.compile(rb"sk-[A-Za-z0-9_\-]{20,}"),
    "chave Groq (gsk_...)": re.compile(rb"gsk_[A-Za-z0-9]{20,}"),
    "Bearer token": re.compile(rb"Bearer [A-Za-z0-9._\-]{20,}"),
    "token GitHub": re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    "chave privada": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def git(*args: str, root: Path) -> bytes:
    out = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=root, capture_output=True)
    if out.returncode != 0:
        sys.exit(f"erro ao executar git {' '.join(args)}: {out.stderr.decode(errors='replace').strip()}")
    return out.stdout


def tracked_files(root: Path) -> list[str]:
    return [p.decode("utf-8") for p in git("ls-files", "-z", root=root).split(b"\0") if p]


def is_env_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (name == ".env" or name.startswith(".env.")) and name != ".env.example"


def env_secret_values(root: Path) -> list[bytes]:
    """Valores de chaves do .env local (só em memória, nunca impressos)."""
    env = root / ".env"
    if not env.is_file():
        return []
    values = []
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("\"'")
        if len(value) >= 8 and re.search(r"KEY|TOKEN|SECRET|PASS", key, re.I):
            values.append(value.encode())
    return values


def check(root: Path, public: bool, allow_csv: bool, history: bool) -> list[str]:
    problems: list[str] = []
    files = tracked_files(root)

    for path in files:
        if is_env_file(path):
            problems.append(f"arquivo de ambiente rastreado: {path}")
        if "claude" in path.lower():
            problems.append(f"caminho com 'claude' rastreado: {path}")

    secrets = env_secret_values(root)
    for path in files:
        file = root / path
        if not file.is_file():
            continue
        data = file.read_bytes()
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                problems.append(f"padrão de segredo ({label}) em {path}")
        if any(value in data for value in secrets):
            problems.append(f"valor do .env presente em {path}")

    if history:
        names = {p.decode("utf-8") for p in git("log", "--all", "--name-only", "--format=", root=root).split(b"\n") if p}
        for path in sorted(names):
            if is_env_file(path) or "claude" in path.lower():
                problems.append(f"no histórico: {path}")
        revs = git("rev-list", "--all", root=root).split()
        for value in secrets:
            hits = subprocess.run(["git", "log", "--all", "-S" + value.decode(), "--format=%h"],
                                  cwd=root, capture_output=True).stdout.split()
            if hits:
                problems.append(f"valor do .env aparece no histórico ({len(hits)} commit(s) de {len(revs)})")

    if public:
        for path in files:
            if path in RESTRICTED:
                problems.append(f"arquivo restrito rastreado: {path} ({RESTRICTED[path]})")
            elif path.startswith(RESTRICTED_CSV_PREFIX) and not allow_csv:
                problems.append(f"CSV da base fornecida rastreado: {path} (use --allow-csv se autorizado)")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Verificador de publicação (somente leitura).")
    parser.add_argument("--public", action="store_true", help="falha se arquivos RESTRITOS estiverem rastreados")
    parser.add_argument("--allow-csv", action="store_true", help="com --public, aceita os CSVs de data/")
    parser.add_argument("--history", action="store_true", help="também verifica caminhos/valores em todo o histórico")
    parser.add_argument("--root", default=".", help="raiz do repositório (padrão: diretório atual)")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(args.root).resolve()
    problems = check(root, args.public, args.allow_csv, args.history)
    if problems:
        print(f"FALHOU: {len(problems)} problema(s)")
        for item in problems:
            print(f" - {item}")
        return 1
    print("OK: nenhuma pendência encontrada" + (" (modo público)" if args.public else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
