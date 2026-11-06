import re
import unicodedata


RESTRICTED = re.compile(
    r"\b(?:salary|salaries|compensation|equity[_ ]bonus|bonus|bonuses|layoffs?|"
    r"redundan(?:cy|cies)|termination|terminations|fired|getting fired|performance[_ ](?:plan|status)|"
    r"pip|internal[_ ]hr|internal[_ ]financial|confidential|acquir(?:e|ing)|acquisition|"
    r"m\s*(?:&|and|_)\s*a|executive[_ ](?:pay|equity)|restricted[_ ]internal)\b",
    re.IGNORECASE,
)
INJECTION = re.compile(
    r"(?:ignore|forget|override|bypass).{0,70}(?:instructions?|rules?|polic(?:y|ies)|approval)|"
    r"(?:reveal|show|print|dump).{0,50}(?:system prompt|hidden instructions|api[_ ]?key|"
    r"environment variables|secrets)|(?:act|treat).{0,30}(?:system|developer)|"
    r"<\s*(?:system|developer)\s*>",
    re.IGNORECASE,
)
UNSAFE_EMAIL = re.compile(
    r"\b(?:discount|guarantee|legally binding|indemnif\w*|waive|free of charge|"
    r"commit(?:ment|ments)?|promise|unlimited liability)\b",
    re.IGNORECASE,
)
SECRET = re.compile(r"sk-[A-Za-z0-9_-]{12,}|Bearer\s+\S+", re.IGNORECASE)


def canonical(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("\u200b", "")


def restricted(text: str) -> bool:
    return bool(RESTRICTED.search(canonical(text)))


def input_reason(text: str, limit: int = 4000) -> str | None:
    if not text.strip():
        return "empty_input"
    if len(text) > limit:
        return "input_too_long"
    if restricted(text):
        return "restricted_internal_data"
    if INJECTION.search(canonical(text)):
        return "prompt_injection"
    if SECRET.search(text):
        return "credential_in_input"
    return None


def output_reason(text: str) -> str | None:
    if restricted(text) or SECRET.search(text):
        return "sensitive_output"
    if UNSAFE_EMAIL.search(text):
        return "unsupported_customer_commitment"
    return None


def redact(value):
    if isinstance(value, str):
        if restricted(value) or INJECTION.search(canonical(value)) or SECRET.search(value):
            return "[REDACTED]"
        return value
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if restricted(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def blocked(reason: str, layer: str) -> dict:
    return {"status": "blocked", "reason": reason, "policy": "salesops_v1", "layer": layer}
