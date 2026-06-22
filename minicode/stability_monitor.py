"""Compatibility facade for minicode.control.stability."""

import sys as _sys
from minicode.control import stability as _implementation

_implementation.__all__ = ["AnomalyRecord","HealthLevel","MetricSnapshot","StabilityMonitor","StabilityReport"]
_sys.modules[__name__] = _implementation

from minicode.control.stability import (
    AnomalyRecord,
    HealthLevel,
    MetricSnapshot,
    StabilityMonitor,
    StabilityReport,
)

__all__ = [
    "AnomalyRecord",
    "HealthLevel",
    "MetricSnapshot",
    "StabilityMonitor",
    "StabilityReport",
]
