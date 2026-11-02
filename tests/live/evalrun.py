"""Registro por execução (runs.jsonl) e agregação das métricas da avaliação com LLM real.

Cada linha de runs.jsonl é uma execução (cenário × repetição) em sessão nova, sem PII: perguntas,
respostas, falhas e ferramentas passam por `mask` (e-mails/telefones de clientes mascarados).
Se uma execução aparece mais de uma vez (reexecução após 429), vale a última linha.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tests.live.harness import Run, Scenario, invented_info, tools_ok
from tests.live.transcript import mask, visible

# Falhas do lado do provedor (cota, indisponibilidade): a execução não mede o agente.
PROVIDER_CATEGORIES = ("rate_limit", "server_error", "timeout", "connection")


def _clean(text: str, limit: int = 600) -> str:
    out = visible(mask(text)).replace("\n", " ")
    return out if len(out) <= limit else out[:limit] + f"... (+{len(out) - limit} caracteres)"


def classify(run: Run) -> tuple[str, str | None]:
    """('inconclusive', motivo) se o provedor falhou; ('ok', None) caso contrário."""
    for category in PROVIDER_CATEGORIES:
        if category in run.llm_errors:
            return "inconclusive", category
    return "ok", None


def build_record(scenario: Scenario, run: Run, number: int, failures: list[str], model: str) -> dict:
    state, reason = classify(run)
    inconclusive = state == "inconclusive"
    errors = sorted(set(run.llm_errors) | {t.reply.error_category for t in run.turns if t.reply.error_category})
    return {
        "scenario_id": scenario.id, "run": number, "group": scenario.group, "name": scenario.name,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model,
        "status": "inconclusive" if inconclusive else ("failed" if failures else "passed"),
        "inconclusive_reason": reason,
        "questions": [_clean(q, 400) for q in scenario.turns],
        "expected": scenario.expected,
        "observed": _clean(run.turns[-1].text, 1500) if run.turns else "",
        "answers": [_clean(t.text, 1500) for t in run.turns],
        "tools": [{"turn": i, "name": name, "status": result.get("status")}
                  for i, turn in enumerate(run.turns, 1) for name, _, result in turn.calls],
        "expected_tools": [list(g) for g in scenario.expected_tools], "expect_no_tools": scenario.expect_no_tools,
        "tool_ok": None if inconclusive else tools_ok(scenario, run),
        "correct": None if inconclusive else not failures,
        "failures": [_clean(f, 300) for f in failures],
        "invented": [] if inconclusive else invented_info(run),
        "latency_ms": run.latency_ms, "tokens": run.tokens,
        "llm_requests": run.llm_requests, "llm_attempts": run.llm_attempts,
        "errors": errors, "agent_failed": any(t.reply.failed for t in run.turns),
    }


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_records(path: Path) -> list[dict]:
    """Última linha de cada (cenário, repetição), na ordem em que apareceram pela 1ª vez."""
    latest: dict[tuple[str, int], dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                latest[(rec["scenario_id"], rec["run"])] = rec
    return list(latest.values())


def done_keys(path: Path) -> set[tuple[str, int]]:
    """Execuções já concluídas (as inconclusivas serão refeitas)."""
    return {(r["scenario_id"], r["run"]) for r in load_records(path) if r["status"] != "inconclusive"}


# --- agregação ---------------------------------------------------------------------------------
def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]  # nearest-rank


def _stats(records: list[dict]) -> dict:
    done = [r for r in records if r["status"] != "inconclusive"]
    correct = sum(1 for r in done if r["correct"])
    tool_rows = [r for r in done if r["tool_ok"] is not None]
    lat = [r["latency_ms"] for r in done]
    tok = [r["tokens"]["total_tokens"] for r in done if r["tokens"] and r["tokens"].get("total_tokens") is not None]
    return {
        "executions": len(records), "inconclusive": len(records) - len(done), "conclusive": len(done),
        "correct": correct, "accuracy_pct": round(100 * correct / len(done), 1) if done else None,
        "tool_applicable": len(tool_rows), "tool_ok": sum(1 for r in tool_rows if r["tool_ok"]),
        "tool_ok_pct": round(100 * sum(1 for r in tool_rows if r["tool_ok"]) / len(tool_rows), 1) if tool_rows else None,
        "invented_executions": sum(1 for r in done if r["invented"]),
        "invented_items": sum(len(r["invented"]) for r in done),
        "latency_mean_ms": round(statistics.mean(lat)) if lat else None,
        "latency_median_ms": round(statistics.median(lat)) if lat else None,
        "latency_p95_ms": percentile(lat, 95),
        "tokens_mean": round(statistics.mean(tok)) if tok else None, "tokens_samples": len(tok),
        "llm_attempts_mean": round(statistics.mean(r["llm_attempts"] for r in done), 2) if done else None,
    }


def load_adjudications(path: Path) -> dict[str, dict]:
    """Ajustes pós-execução de falsos positivos comprovados: {"ID#k": {"correct"?, "invented"?, "reason"}}.
    Os registros de runs.jsonl nunca são alterados; os números ajustados são reportados ao lado dos brutos."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def apply_adjudications(records: list[dict], adjudications: dict[str, dict]) -> list[dict]:
    out = []
    for r in records:
        adj = adjudications.get(f"{r['scenario_id']}#{r['run']}")
        if adj:
            r = {**r, **{k: v for k, v in adj.items() if k in ("correct", "invented", "status")}, "adjusted": True}
        out.append(r)
    return out


def summarize(records: list[dict], adjudications: dict[str, dict] | None = None) -> dict:
    adjusted = apply_adjudications(records, adjudications or {})
    by_scenario: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_scenario[r["scenario_id"]].append(r)
    per = {sid: {"name": rs[0]["name"], "group": rs[0]["group"], **_stats(rs)} for sid, rs in by_scenario.items()}
    groups = {g: _stats([r for r in records if r["group"] == g]) for g in sorted({r["group"] for r in records})}
    for sid in per:
        adj = _stats([r for r in adjusted if r["scenario_id"] == sid])
        per[sid]["accuracy_adjusted_pct"] = adj["accuracy_pct"]
        per[sid]["invented_adjusted_executions"] = adj["invented_executions"]
    return {"overall": _stats(records), "overall_adjusted": _stats(adjusted),
            "adjustments": adjudications or {}, "by_group": groups, "by_scenario": per,
            "failures": [r for r in records if r["status"] == "failed"],
            "inconclusive": [r for r in records if r["status"] == "inconclusive"]}


def render_markdown(summary: dict) -> str:
    def row(label: str, s: dict, adj: dict | None = None) -> str:
        fmt = lambda v, suf="": "-" if v is None else f"{v}{suf}"  # noqa: E731
        adj = adj or {"accuracy_pct": s["accuracy_pct"], "invented_executions": s["invented_executions"]}
        return (f"| {label} | {s['conclusive']}/{s['executions']} | {s['correct']} | {fmt(s['accuracy_pct'], '%')} | "
                f"{fmt(adj['accuracy_pct'], '%')} | {s['tool_ok']}/{s['tool_applicable']} | "
                f"{s['invented_executions']}/{adj['invented_executions']} | "
                f"{fmt(s['latency_median_ms'])} | {fmt(s['latency_p95_ms'])} | {fmt(s['tokens_mean'])} |")
    head = ("| Cenário | Conclusivas/total | Corretas | Acerto | Acerto ajustado | Ferramenta esperada "
            "| Execuções com info inventada (bruto/ajustado) | Latência mediana (ms) | Latência p95 (ms) "
            "| Tokens médios |\n|---|---|---|---|---|---|---|---|---|---|")
    lines = [head]
    lines += [row(f"{sid} {s['name']}", s, {"accuracy_pct": s["accuracy_adjusted_pct"],
                                           "invented_executions": s["invented_adjusted_executions"]})
              for sid, s in summary["by_scenario"].items()]
    lines.append(row("**Consolidado**", summary["overall"], summary["overall_adjusted"]))
    return "\n".join(lines) + "\n"
