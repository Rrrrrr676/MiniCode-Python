"""Pure, configuration-independent token estimation."""

from __future__ import annotations

import json
import re
from typing import Any


CHARS_PER_TOKEN = 4.0
_CJK_PATTERN = re.compile(r"[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF]")
_token_cache: dict[str | int, int] = {}
_TOKEN_CACHE_MAX = 1024


def estimate_tokens(text: str) -> int:
    """Estimate tokens for English/code, CJK, and mixed text."""
    if not text:
        return 0

    cache_key: str | int = text if len(text) < 256 else hash(text)
    cached = _token_cache.get(cache_key)
    if cached is not None:
        return cached

    cjk_count = len(_CJK_PATTERN.findall(text))
    ascii_chars = len(text) - cjk_count
    result = max(1, int(cjk_count / 1.5 + ascii_chars / CHARS_PER_TOKEN))
    if len(_token_cache) < _TOKEN_CACHE_MAX:
        _token_cache[cache_key] = result
    return result


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """Estimate tokens for one internal chat message."""
    content = message.get("content", "")
    has_input = bool(message.get("input"))
    content_str = content if isinstance(content, str) else ""
    if not content_str and not has_input:
        return 0

    role_overhead = {
        "system": 3,
        "user": 4,
        "assistant": 3,
        "assistant_tool_call": 7,
        "tool_result": 6,
        "assistant_progress": 3,
    }
    tokens = role_overhead.get(message.get("role", ""), 0)
    if isinstance(content, str):
        tokens += estimate_tokens(content)
    if "input" in message:
        input_value = message["input"]
        input_str = json.dumps(input_value) if isinstance(input_value, dict) else str(input_value)
        tokens += estimate_tokens(input_str)
    return tokens


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total tokens for internal chat messages."""
    return sum(estimate_message_tokens(message) for message in messages)


__all__ = [
    "CHARS_PER_TOKEN",
    "estimate_message_tokens",
    "estimate_messages_tokens",
    "estimate_tokens",
]
