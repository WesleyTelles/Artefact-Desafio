"""Executa a matriz de cenários contra o LLM configurado (.env) e grava transcrições e métricas.

Uso: python scripts/run_scenarios.py [--group core|adv|rev|all] [--only S01,S05] [--sleep 4]
                                     [--repeat N] [--resume] [--out DIR] [--summarize]

Sem --repeat/--out o comportamento antigo é mantido (1 execução, transcrições em
docs/quality/transcripts). Com --repeat N (ou --out), cada repetição usa Agent/sessão NOVA e grava:
  <out>/runs.jsonl                    uma linha por execução (sem PII)
  <out>/transcripts/<ID>_run<k>.md    transcrição mascarada
As repetições são feitas em rodadas (todas as execuções 1, depois todas as 2, ...), para que uma
interrupção por cota deixe a cobertura equilibrada. Ao 429 persistente (o cliente já fez retry com
backoff) a execução é marcada INCONCLUSIVA (não conta como erro do agente) e o runner para com
código 3; --resume pula o que já foi concluído e refaz as inconclusivas.
A chave nunca é lida aqui: o cliente é criado pelo próprio app.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import load_env_file, load_llm_settings  # noqa: E402
from app.llm.factory import create_client  # noqa: E402
from tests.live.evalrun import (  # noqa: E402
    append_record, build_record, done_keys, load_adjudications, load_records, render_markdown, summarize)
from tests.live.harness import evaluate, run_scenario  # noqa: E402
from tests.live.scenarios import SCENARIOS  # noqa: E402
from tests.live.transcript import render  # noqa: E402

EVAL_DIR = ROOT / "docs" / "evaluation"
LEGACY_DIR = ROOT / "docs" / "quality" / "transcripts"
EXIT_RATE_LIMITED = 3


def _summarize(out: Path) -> int:
    records = load_records(out / "runs.jsonl")
    if not records:
        print("Nenhuma execução registrada em", out / "runs.jsonl", file=sys.stderr)
        return 2
    summary = summarize(records, load_adjudications(out / "adjudication.json"))
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "summary.md").write_text(render_markdown(summary), encoding="utf-8")
    o, a = summary["overall"], summary["overall_adjusted"]
    print(f"{o['correct']}/{o['conclusive']} corretas ({o['accuracy_pct']}%; ajustado {a['accuracy_pct']}%), "
          f"{o['inconclusive']} inconclusivas, {o['invented_executions']} execuções com informação inventada "
          f"(ajustado {a['invented_executions']}). Resumo em {out / 'summary.md'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--group", choices=("core", "adv", "rev", "all"), default="core")
    ap.add_argument("--only", default="", help="IDs separados por vírgula (ex.: S01,S05)")
    ap.add_argument("--sleep", type=float, default=4.0, help="segundos entre execuções")
    ap.add_argument("--repeat", type=int, default=None, help="repetições por cenário (sessões novas)")
    ap.add_argument("--resume", action="store_true", help="pula execuções já concluídas em runs.jsonl")
    ap.add_argument("--summarize", action="store_true", help="só agrega runs.jsonl (summary.json/summary.md)")
    ap.add_argument("--out", default=None, help="diretório de saída (padrão: docs/evaluation com --repeat)")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    evaluation = args.repeat is not None or args.out is not None or args.resume
    out = Path(args.out) if args.out else (EVAL_DIR if evaluation else LEGACY_DIR)
    if args.summarize:
        return _summarize(out)
    repeat = args.repeat or 1
    if repeat < 1:
        print("--repeat deve ser >= 1", file=sys.stderr)
        return 2
    load_env_file()
    settings = load_llm_settings()
    if not settings.api_key and settings.provider != "ollama":
        print("LLM_API_KEY não definida: nada a executar.", file=sys.stderr)
        return 2
    llm = create_client(settings)
    wanted = {x.strip() for x in args.only.split(",") if x.strip()}
    chosen = [s for s in SCENARIOS if (s.id in wanted if wanted else args.group in ("all", s.group))]
    transcripts = out / ("transcripts" if evaluation else "")
    transcripts.mkdir(parents=True, exist_ok=True)
    runs_path = out / "runs.jsonl"
    skip = done_keys(runs_path) if args.resume else set()
    print(f"Modelo: {settings.model}. Cenários: {len(chosen)}; repetições: {repeat}; "
          f"já concluídas (puladas): {len(skip)}")
    results: list[tuple[str, str]] = []
    executed = 0
    for k in range(1, repeat + 1):
        for scenario in chosen:
            if (scenario.id, k) in skip:
                continue
            if executed:
                time.sleep(args.sleep)
            executed += 1
            run = run_scenario(scenario, llm)
            failures = evaluate(scenario, run)
            if evaluation:
                record = build_record(scenario, run, k, failures, settings.model)
                append_record(runs_path, record)
                verdict = {"passed": "PASSOU", "failed": "FALHOU",
                           "inconclusive": f"INCONCLUSIVO ({record['inconclusive_reason']})"}[record["status"]]
                text = render(scenario, run, failures if record["status"] == "failed" else [], verdict,
                              run_number=k, record=record)
                (transcripts / f"{scenario.id}_run{k}.md").write_text(text, encoding="utf-8")
                inconclusive = record["status"] == "inconclusive"
                extra = f" ({record['latency_ms']} ms)"
            else:
                inconclusive = run.rate_limited
                verdict = "INCONCLUSIVO (rate_limit)" if inconclusive else ("FALHOU" if failures else "PASSOU")
                (transcripts / f"{scenario.id}.md").write_text(
                    render(scenario, run, [] if inconclusive else failures, verdict), encoding="utf-8")
                extra = ""
            results.append((f"{scenario.id}#{k}", verdict))
            shown = [] if inconclusive else failures
            print(f"{scenario.id}#{k} {scenario.name}: {verdict}{extra}" + "".join(f"\n    - {f}" for f in shown),
                  flush=True)
            if run.rate_limited:
                print("429 persistente: execução interrompida. Aguarde a cota e rode de novo com --resume.")
                _report(results, evaluation, out)
                return EXIT_RATE_LIMITED
    _report(results, evaluation, out)
    return 0 if all(v == "PASSOU" for _, v in results) else 1


def _report(results: list[tuple[str, str]], evaluation: bool, out: Path) -> None:
    passed = sum(1 for _, v in results if v == "PASSOU")
    inconclusive = sum(1 for _, v in results if v.startswith("INCONCLUSIVO"))
    print(f"\n{passed}/{len(results)} passaram nesta sessão ({inconclusive} inconclusivas).")
    if evaluation:
        _summarize(out)


if __name__ == "__main__":
    sys.exit(main())
