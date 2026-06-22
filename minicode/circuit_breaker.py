"""Compatibility facade for minicode.context.compaction.circuit_breaker."""

import sys as _sys
from minicode.context.compaction import circuit_breaker as _implementation

_implementation.__all__ = ["CircuitBreakerConfig","CircuitBreakerState","CompactionCircuitBreaker","get_compaction_circuit_breaker"]
_sys.modules[__name__] = _implementation

from minicode.context.compaction.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerState,
    CompactionCircuitBreaker,
    get_compaction_circuit_breaker,
)

__all__ = [
    "CircuitBreakerConfig",
    "CircuitBreakerState",
    "CompactionCircuitBreaker",
    "get_compaction_circuit_breaker",
]
