import argparse
import json
from pathlib import Path

from salesops.agent import ask
from salesops.config import Settings
from salesops.observability import Run
from salesops.tools import ToolSurface


def main():
    parser = argparse.ArgumentParser(description="UdaCenture local SalesOps agent")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--offline", action="store_true", help="Use the scripted test model, without API calls"
    )
    parser.add_argument("--user-id", default="local-analyst")
    parser.add_argument("--session-id", default="local-session")
    parser.add_argument("--thread-id", default="default")
    commands = parser.add_subparsers(dest="command", required=True)
    question = commands.add_parser("ask")
    question.add_argument("question")
    question.add_argument("--approval", choices=["approve", "reject"])
    resume = commands.add_parser("resume")
    resume.add_argument("draft_id")
    resume.add_argument("--approval", choices=["approve", "reject"], required=True)
    replay = commands.add_parser("inspect")
    replay.add_argument("run_id")
    args = parser.parse_args()
    settings = Settings(
        root=args.root,
        backend="offline" if args.offline else "live",
        user_id=args.user_id,
        session_id=args.session_id,
        thread_id=args.thread_id,
    )
    if args.command == "ask":
        result = ask(args.question, settings, args.approval)
    elif args.command == "resume":
        run = Run(settings, "Resume a stored email draft")
        try:
            surface = ToolSurface(run, args.approval)
            outcome = surface.invoke("send_email", {"draft_id": args.draft_id})
            status = "success" if outcome["status"] == "sent" else outcome["status"]
            result = run.finish(status, json.dumps(outcome), outcome.get("reason"))
        except Exception as error:
            result = run.finish("failed", "Resume failed.", type(error).__name__)
    else:
        if len(args.run_id) != 32 or any(char not in "0123456789abcdef" for char in args.run_id):
            parser.error("Use the hexadecimal run ID from a previous response")
        trace = settings.root / "traces" / f"{args.run_id}.json"
        result = json.loads(trace.read_text())
        if (result["user_id"], result["session_id"], result["thread_id"]) != (
            settings.user_id,
            settings.session_id,
            settings.thread_id,
        ):
            parser.error("Trace is outside the current user/session/thread scope")
    print(json.dumps(result, indent=2))
    if result.get("status") == "failed":
        raise SystemExit(1)
