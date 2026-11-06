import json
import os
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from dotenv import load_dotenv


def resource(name: str) -> str:
    return files("salesops").joinpath("resources", name).read_text(encoding="utf-8")


@dataclass
class Settings:
    root: Path = field(default_factory=Path.cwd)
    backend: str = "live"
    user_id: str = "local-analyst"
    session_id: str = "local-session"
    thread_id: str = "default"
    allowed_accounts: frozenset[str] | None = None
    values: dict = field(default_factory=lambda: json.loads(resource("config.v1.json")))

    def __post_init__(self):
        self.root = self.root.resolve()
        load_dotenv(self.root / ".env", override=False)

    @property
    def model(self) -> str:
        return os.getenv("SALESOPS_MODEL", self.values["model"])

    @property
    def scope(self) -> str:
        return json.dumps([self.user_id, self.session_id, self.thread_id])

    @property
    def prompt(self) -> str:
        return resource("system.v1.txt") + "\nReference date: " + self.values["reference_date"]
