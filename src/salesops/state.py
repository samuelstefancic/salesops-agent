import json
import sqlite3
from pathlib import Path
from uuid import uuid4


class StateStore:
    def __init__(self, root: Path):
        (root / "logs").mkdir(parents=True, exist_ok=True)
        self.path = root / "logs" / "state.sqlite3"
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS drafts "
                "(id TEXT PRIMARY KEY, scope TEXT NOT NULL, body TEXT NOT NULL, "
                "status TEXT NOT NULL, run_id TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS outbox "
                "(draft_id TEXT PRIMARY KEY, scope TEXT NOT NULL, body TEXT NOT NULL)"
            )

    def draft(self, scope: str, body: dict, run_id: str) -> dict:
        draft_id = uuid4().hex
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO drafts VALUES (?, ?, ?, 'drafted', ?)",
                (draft_id, scope, json.dumps(body), run_id),
            )
        return {"status": "drafted", "draft_id": draft_id, **body}

    def decide(self, scope: str, draft_id: str, decision: str | None) -> dict:
        with sqlite3.connect(self.path, isolation_level="IMMEDIATE") as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT body, status FROM drafts WHERE id=? AND scope=?", (draft_id, scope)
            ).fetchone()
            if row is None:
                raise ValueError("Draft not found in the current user/session/thread scope")
            body, status = row
            if status in {"rejected", "sent"}:
                return {"status": status, "draft_id": draft_id, "simulated": True}
            if decision is None:
                status = "awaiting_approval"
            elif decision == "reject":
                status = "rejected"
            elif decision == "approve":
                status = "sent"
                db.execute("INSERT OR IGNORE INTO outbox VALUES (?, ?, ?)", (draft_id, scope, body))
            else:
                raise ValueError("Approval must be approve or reject")
            db.execute("UPDATE drafts SET status=? WHERE id=? AND scope=?", (status, draft_id, scope))
        return {"status": status, "draft_id": draft_id, "simulated": True}

    def outbox(self, scope: str) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute(
                "SELECT draft_id, body FROM outbox WHERE scope=? ORDER BY rowid", (scope,)
            ).fetchall()
        return [{"draft_id": draft_id, **json.loads(body)} for draft_id, body in rows]
