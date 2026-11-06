import argparse
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from salesops.agent import ScriptedModel, ask, call_step
from salesops.config import Settings, resource
from salesops.reporting import generate_report
from salesops.state import StateStore


def run_suite(root: Path, live: bool = False) -> dict:
    tasks = json.loads(resource("tasks.v1.json"))
    results = []
    for task in tasks:
        backend = "live" if live else "offline"
        model = None
        if "probe" in task:
            probe = task["probe"]
            model = ScriptedModel(
                steps=[call_step(probe["tool"], probe["arguments"]), {"content": "$last_tool"}]
            )
        elif "output_probe" in task:
            model = ScriptedModel(steps=[{"content": task["output_probe"]}])
        if model is not None:
            backend = "offline"
        settings = Settings(
            root=root, backend=backend, session_id="evaluation", thread_id=task["id"]
        )
        store = StateStore(root)
        outbox_before = len(store.outbox(settings.scope))
        result = ask(task["question"], settings, task.get("approval"), task["id"], model)
        errors = []
        if result["status"] != task["expected_status"]:
            errors.append(f"Expected {task['expected_status']}, received {result['status']}")
        if task.get("reason") and result["failure_reason"] != task["reason"]:
            errors.append("Unexpected policy reason")
        if task.get("tool") and task["tool"] not in result["tools_called"]:
            errors.append("Expected tool was not called")
        text = result["final_output"].casefold().replace(",", "")
        for fact in task.get("facts", []):
            if fact.casefold() not in text:
                errors.append(f"Missing expected evidence: {fact}")
        if task.get("email_status"):
            try:
                payload = json.loads(result["final_output"])
                if payload.get("email_status") != task["email_status"]:
                    errors.append("Incorrect email action status")
            except json.JSONDecodeError:
                errors.append("Email result is not structured")
            expected_delta = 1 if task["email_status"] == "sent" else 0
            if len(store.outbox(settings.scope)) - outbox_before != expected_delta:
                errors.append("Outbox mutation does not match the approval decision")
        results.append(
            {
                "task_id": task["id"],
                "passed": not errors,
                "status": result["status"],
                "backend": backend,
                "latency_ms": result["latency_ms"],
                "estimated_cost_usd": result["estimated_cost_usd"],
                "failure_reason": "; ".join(errors) or None,
                "run_failure_reason": result["failure_reason"],
                "run_id": result["run_id"],
            }
        )
    passed = sum(row["passed"] for row in results)
    return {
        "suite_version": "1.0",
        "mode": "mixed-live-and-policy-probes" if live else "offline-scripted",
        "passed": passed,
        "failed": len(results) - passed,
        "tasks": results,
        "scope": "Offline results verify application controls and CRM plumbing. "
        "They do not measure live model reasoning, provider connectivity or generation quality.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--live", action="store_true", help="Use the configured API for functional tasks"
    )
    args = parser.parse_args()
    root = args.root.resolve()
    Settings(root=root)
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="salesops-evaluation-") as temporary:
        evaluation_root = Path(temporary)
        shutil.copytree(root / "data", evaluation_root / "data")
        report = run_suite(evaluation_root, args.live)
        evidence = reports / "evidence"
        evidence.mkdir(exist_ok=True)
        log = evaluation_root / "logs" / "runs.jsonl"
        shutil.copyfile(log, evidence / "runs.jsonl")
        for task in report["tasks"]:
            run_id = task["run_id"]
            shutil.copyfile(
                evaluation_root / "traces" / f"{run_id}.json", evidence / f"{run_id}.json"
            )
        generate_report(log, reports / "monitoring_report.md")
    (reports / "evaluation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# SalesOps evaluation",
        "",
        f"Mode: `{report['mode']}`",
        "",
        report["scope"],
        "",
        f"Passed: {report['passed']}; failed: {report['failed']}.",
        "",
        "| Task | Pass | Run status | Backend | Latency ms | Estimated USD | Failure reason |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in report["tasks"]:
        lines.append(
            f"| {row['task_id']} | {row['passed']} | {row['status']} | {row['backend']} | "
            f"{row['latency_ms']:.3f} | {row['estimated_cost_usd']:.9f} | {row['failure_reason'] or ''} |"
        )
    (reports / "evaluation_report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(bool(report["failed"]))
