"""Compatibility facade for minicode.control.recovery."""

import sys as _sys
from minicode.control import recovery as _implementation

_implementation.__all__ = ["FaultRecord","FaultSeverity","FaultType","HealingAction","HealingStatus","HealingStrategy","SelfHealingEngine"]
_sys.modules[__name__] = _implementation

from minicode.control.recovery import (
    FaultRecord,
    FaultSeverity,
    FaultType,
    HealingAction,
    HealingStatus,
    HealingStrategy,
    SelfHealingEngine,
)

__all__ = [
    "FaultRecord",
    "FaultSeverity",
    "FaultType",
    "HealingAction",
    "HealingStatus",
    "HealingStrategy",
    "SelfHealingEngine",
]
