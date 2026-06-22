"""Compatibility facade for :mod:`minicode.context.manager`."""

from minicode.context import manager as _manager
from minicode.context.manager import (
    AUTOCOMPACT_THRESHOLD,
    DEFAULT_CONTEXT_WINDOWS,
    MIN_MESSAGES_TO_KEEP,
    SYSTEM_PROMPT_RESERVED,
    ContextManager,
    ContextStats,
    ModelContextWindow,
    compute_context_stats,
    get_model_context_window,
    token_count_with_estimation,
)
from minicode.context.tokens import (
    CHARS_PER_TOKEN,
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
)


MINI_CODE_DIR = _manager.MINI_CODE_DIR


def save_context_state(manager: ContextManager) -> None:
    _manager.MINI_CODE_DIR = MINI_CODE_DIR
    _manager.save_context_state(manager)


def load_context_state() -> ContextManager | None:
    _manager.MINI_CODE_DIR = MINI_CODE_DIR
    return _manager.load_context_state()


def clear_context_state() -> None:
    _manager.MINI_CODE_DIR = MINI_CODE_DIR
    _manager.clear_context_state()


__all__ = [
    "AUTOCOMPACT_THRESHOLD",
    "CHARS_PER_TOKEN",
    "ContextManager",
    "ContextStats",
    "DEFAULT_CONTEXT_WINDOWS",
    "MINI_CODE_DIR",
    "MIN_MESSAGES_TO_KEEP",
    "ModelContextWindow",
    "SYSTEM_PROMPT_RESERVED",
    "clear_context_state",
    "compute_context_stats",
    "estimate_message_tokens",
    "estimate_messages_tokens",
    "estimate_tokens",
    "get_model_context_window",
    "load_context_state",
    "save_context_state",
    "token_count_with_estimation",
]
