import json
import re

from salesops.config import Settings


def normalized(value: str) -> str:
    value = re.sub(r"[^a-z0-9 ]", " ", value.casefold())
    return " ".join(
        word for word in value.split()
        if word not in {"inc", "incorporated", "corp", "corporation", "ltd", "limited", "llc"}
    )


class CRM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.tables = {}
        for name, allowed in settings.values["data_fields"].items():
            records = json.loads((settings.root / "data" / f"{name}.json").read_text())
            if not isinstance(records, list):
                raise ValueError(f"Invalid CRM dataset: {name}")
            self.tables[name] = [
                {key: value for key, value in row.items() if key in allowed}
                for row in records
                if settings.allowed_accounts is None
                or row.get("account_id") in settings.allowed_accounts
            ]

    def account(self, query: str) -> dict:
        query = normalized(query)
        matches = [
            row for row in self.tables["accounts"]
            if query in {normalized(row["account_id"]), normalized(row["name"])}
        ]
        if len(matches) != 1:
            raise ValueError("Account not found in the allowed scope; use its exact name or ID")
        return matches[0]

    def context(self, query: str) -> dict:
        account = self.account(query)
        account_id = account["account_id"]
        result = {"account": account}
        for table in self.tables:
            if table != "accounts":
                result[table] = [
                    row for row in self.tables[table] if row.get("account_id") == account_id
                ]
        if not any(row["stage"] == "Closed Won" for row in result["opportunities"]):
            result["support_tickets"] = []
            result["product_usage"] = []
        return result

    def open_opportunities(self, stage: str | None = None) -> list[dict]:
        return [
            row for row in self.tables["opportunities"]
            if row["stage"] not in {"Closed Won", "Closed Lost"}
            and (stage is None or row["stage"].casefold() == stage.casefold())
        ]
