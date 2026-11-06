import math
from collections import defaultdict

from salesops.schemas import AnalysisRequest

NUMERIC = {
    "opportunities": {"amount_usd", "probability"},
    "accounts": {"health_score", "arr_usd"},
    "product_usage": {"active_users", "monthly_logins", "feature_adoption_score"},
    "support_tickets": set(),
}
GROUPS = {
    "opportunities": {"stage", "type", "account_id"},
    "accounts": {"account_status", "region", "segment"},
    "product_usage": {"period", "usage_trend", "account_id"},
    "support_tickets": {"severity", "status", "category", "account_id"},
}


def analyze(tables: dict, request: AnalysisRequest) -> dict:
    if request.dataset not in NUMERIC:
        raise ValueError("Dataset is outside the CRM analysis allowlist")
    rows = tables[request.dataset]
    if request.dataset == "opportunities":
        rows = [row for row in rows if row["stage"] not in {"Closed Won", "Closed Lost"}]
    if len(rows) > 2000:
        raise ValueError("Analysis row limit exceeded")
    if request.operation in {"sum", "average", "group_sum"}:
        if request.field not in NUMERIC[request.dataset]:
            raise ValueError("Numeric field is outside the analysis allowlist")
    if request.operation.startswith("group_"):
        if request.group_by not in GROUPS[request.dataset]:
            raise ValueError("Grouping field is outside the analysis allowlist")
    if request.operation in {"count", "group_count"} and request.field is not None:
        raise ValueError("Counting does not accept a numeric field")
    values = [float(row.get(request.field) or 0) for row in rows] if request.field else []
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Analysis data contains non-finite values")
    if request.operation == "count":
        result = len(rows)
    elif request.operation == "sum":
        result = sum(values)
    elif request.operation == "average":
        result = sum(values) / len(values) if values else None
    else:
        result = defaultdict(float)
        for row in rows:
            key = str(row.get(request.group_by, "unknown"))[:80]
            result[key] += float(row.get(request.field) or 0) if request.field else 1
        result = dict(sorted(result.items()))
    return {
        "status": "success",
        "dataset": request.dataset,
        "operation": request.operation,
        "rows": len(rows),
        "result": result,
    }
