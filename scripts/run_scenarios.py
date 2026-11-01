"""Executa a matriz de cenários contra o LLM configurado (.env) e grava transcrições.

Uso: python scripts/run_scenarios.py [--group core|adv|all] [--only S01,S05] [--sleep 4]
Para ao primeiro 429 (rate_limit) e registra o cenário como inconclusivo. A chave nunca é lida
aqui: o cliente é criado pelo próprio app. Saída: docs/quality/transcripts/<ID>.md e um resumo.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import load_env_file, load_llm_settings  # noqa: E402
from app.llm.factory import create_client  # noqa: E402
from tests.live.harness import evaluate, run_scenario  # noqa: E402
from tests.live.scenarios import SCENARIOS  # noqa: E402
from tests.live.transcript import render  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group", choices=("core", "adv", "all"), default="core")
    ap.add_argument("--only", default="", help="IDs separados por vírgula (ex.: S01,S05)")
    ap.add_argument("--sleep", type=float, default=4.0, help="segundos entre cenários")
    ap.add_argument("--out", default=str(ROOT / "docs" / "quality" / "transcripts"))
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    load_env_file()
    settings = load_llm_settings()
    if not settings.api_key and settings.provider != "ollama":
        print("LLM_API_KEY não definida: nada a executar.", file=sys.stderr)
        return 2
    llm = create_client(settings)
    wanted = {x.strip() for x in args.only.split(",") if x.strip()}
    chosen = [s for s in SCENARIOS if (s.id in wanted if wanted else args.group in ("all", s.group))]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Modelo: {settings.model}. Cenários: {', '.join(s.id for s in chosen)}")
    summary: list[tuple[str, str]] = []
    for i, scenario in enumerate(chosen):
        if i:
            time.sleep(args.sleep)
        run = run_scenario(scenario, llm)
        if run.rate_limited:
            verdict, failures = "INCONCLUSIVO (rate_limit)", []
        else:
            failures = evaluate(scenario, run)
            verdict = "FALHOU" if failures else "PASSOU"
        (out / f"{scenario.id}.md").write_text(render(scenario, run, failures, verdict), encoding="utf-8")
        summary.append((scenario.id, verdict))
        print(f"{scenario.id} {scenario.name}: {verdict}" + "".join(f"\n    - {f}" for f in failures))
        if run.rate_limited:
            print("429 recebido: execução interrompida. Aguarde a cota e rode de novo com --only.")
            break
    passed = sum(1 for _, v in summary if v == "PASSOU")
    print(f"\n{passed}/{len(summary)} passaram.")
    return 0 if all(v == "PASSOU" for _, v in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
