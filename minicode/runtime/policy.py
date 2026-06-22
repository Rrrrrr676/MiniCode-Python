"""Pure turn limits and guarded compaction policy."""

from __future__ import annotations

from typing import Callable

from minicode.circuit_breaker import CompactionCircuitBreaker


def is_at_blocking_limit(
    token_count: int,
    context_window: int,
    *,
    effective_window_ratio: float = 0.90,
    min_reserve_tokens: int = 3_000,
) -> bool:
    return token_count >= compute_effective_blocking_limit(
        context_window,
        effective_window_ratio=effective_window_ratio,
        min_reserve_tokens=min_reserve_tokens,
    )


def compute_effective_blocking_limit(
    context_window: int,
    *,
    effective_window_ratio: float = 0.90,
    min_reserve_tokens: int = 3_000,
) -> int:
    effective_window = int(context_window * effective_window_ratio)
    return max(1, effective_window - min_reserve_tokens)


def try_compact_with_breaker(
    breaker: CompactionCircuitBreaker,
    compact_fn: Callable[[], tuple[list, bool]],
    current_messages: list,
    logger_fn: Callable[..., None],
) -> tuple[list, bool]:
    if not breaker.is_allowed():
        logger_fn("Compaction blocked by circuit breaker (consecutive failures)")
        return current_messages, False
    try:
        result_messages, effective = compact_fn()
        if effective:
            breaker.record_success()
        return result_messages, effective
    except Exception as exc:
        breaker.record_failure()
        state = breaker.get_state()
        logger_fn(
            "Compaction failed (breaker=%d/%d): %s",
            state.consecutive_failures,
            breaker.config.failure_threshold,
            exc,
        )
        return current_messages, False


__all__ = [
    "compute_effective_blocking_limit",
    "is_at_blocking_limit",
    "try_compact_with_breaker",
]
