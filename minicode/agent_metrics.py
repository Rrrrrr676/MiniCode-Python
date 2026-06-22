"""Compatibility facade for minicode.observability.metrics."""

import sys as _sys
from minicode.observability import metrics as _implementation

_implementation.__all__ = ["AgentMetricsCollector","AgentTurnMetrics","ErrorCategory","ToolExecutionRecord","ToolHistoricalStats"]
_sys.modules[__name__] = _implementation

from minicode.observability.metrics import (
    AgentMetricsCollector,
    AgentTurnMetrics,
    ErrorCategory,
    ToolExecutionRecord,
    ToolHistoricalStats,
)

__all__ = [
    "AgentMetricsCollector",
    "AgentTurnMetrics",
    "ErrorCategory",
    "ToolExecutionRecord",
    "ToolHistoricalStats",
]
