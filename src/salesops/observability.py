import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from salesops.config import Settings, resource
from salesops.policy import redact


@dataclass
class Run:
    settings: Settings
    question: str
    task_id: str | None = None
    run_id: str = field(default_factory=lambda: uuid4().hex)
    events: list[dict] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    approval: str | None = None

    def event(self, kind: str, **fields):
        self.events.append(redact({"kind": kind, "elapsed_ms": self.elapsed, **fields}))

    @property
    def elapsed(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 3)

    def finish(self, status: str, answer: str, reason: str | None = None) -> dict:
        settings = self.settings
        cost = (
            self.input_tokens * settings.values["input_usd_per_million"]
            + self.output_tokens * settings.values["output_usd_per_million"]
        ) / 1_000_000
        summary = {
            "run_id": self.run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "user_id": settings.user_id,
            "session_id": settings.session_id,
            "thread_id": settings.thread_id,
            "user_input": redact(self.question),
            "task_id": self.task_id,
            "status": status,
            "final_output": redact(answer),
            "tools_called": [e["name"] for e in self.events if e["kind"] == "tool_call"],
            "latency_ms": self.elapsed,
            "estimated_cost_usd": round(cost, 9),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model": settings.model if settings.backend == "live" else "scripted-test-model",
            "backend": settings.backend,
            "hitl_decision": self.approval,
            "guardrail_interventions": [e for e in self.events if e["kind"] == "guardrail"],
            "failure_reason": reason,
            "versions": {
                "config": settings.values["version"],
                "prompt_sha256": hashlib.sha256(resource("system.v1.txt").encode()).hexdigest(),
            },
        }
        for directory in ("logs", "traces"):
            (settings.root / directory).mkdir(parents=True, exist_ok=True)
        trace = {**summary, "events": self.events}
        destination = settings.root / "traces" / f"{self.run_id}.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(trace, indent=2) + "\n")
        temporary.replace(destination)
        with (settings.root / "logs" / "runs.jsonl").open("a") as log:
            log.write(json.dumps(summary) + "\n")
        return summary
