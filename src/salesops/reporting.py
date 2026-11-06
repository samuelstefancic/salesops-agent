import argparse
import json
from collections import Counter
from pathlib import Path


def generate_report(log: Path, output: Path) -> dict:
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()] if log.exists() else []
    total = len(rows)
    statuses = Counter(row["status"] for row in rows)
    success = statuses["success"]
    failures = statuses["failed"]
    metrics = {
        "total_runs": total, "success_rate": success / total if total else 0,
        "failure_rate": failures / total if total else 0,
        "average_latency_ms": sum(row["latency_ms"] for row in rows) / total if total else 0,
        "total_estimated_cost_usd": sum(row["estimated_cost_usd"] for row in rows),
        "tool_calls": dict(Counter(name for row in rows for name in row["tools_called"])),
        "guardrail_blocks": sum(len(row["guardrail_interventions"]) for row in rows),
        "hitl_approvals": sum(row["hitl_decision"] == "approve" for row in rows),
        "hitl_rejections": sum(row["hitl_decision"] == "reject" for row in rows),
        "statuses": dict(statuses),
        "failure_reasons": dict(Counter(row["failure_reason"] for row in rows if row["failure_reason"])),
        "backends": dict(Counter(row["backend"] for row in rows)),
    }
    metrics["average_estimated_cost_usd"] = metrics["total_estimated_cost_usd"] / total if total else 0
    lines = [
        "# SalesOps monitoring", "",
        "Operational success means a completed answer/action. A policy block, rejection or pause "
        "is a separate outcome, and may be an expected pass in the evaluation suite. "
        "Failure rate counts technical failures only. These rates therefore need not sum to 100%.", "",
        "Offline scripted calls have zero API cost; their latency is application overhead. "
        "They must not be interpreted as live model performance.", "",
        "| Metric | Value |", "|---|---|",
    ]
    for key, value in metrics.items():
        lines.append(f"| {key} | {json.dumps(value, sort_keys=True)} |")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=Path("logs/runs.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("reports/monitoring_report.md"))
    args = parser.parse_args()
    print(json.dumps(generate_report(args.log, args.output), indent=2))
