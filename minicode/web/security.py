"""Serialization boundary that keeps credentials out of browser payloads."""

from __future__ import annotations

import re
from typing import Any


_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|auth(?:orization)?|token|secret|password|credential)",
    re.IGNORECASE,
)
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|auth[_-]?token|access[_-]?token|password|secret)\s*[:=]\s*)"
        r"[^\s,;]+"
    ),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{12,}\b"),
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_TEXT_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def sanitize_for_web(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            result[key_text] = "[REDACTED]" if _SECRET_KEY.search(key_text) else sanitize_for_web(item)
        return result
    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_web(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(str(value))
