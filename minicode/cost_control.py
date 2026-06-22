"""Compatibility facade for minicode.control.cost."""

import sys as _sys
from minicode.control import cost as _implementation

_implementation.__all__ = ["BudgetActuator","BudgetAdjustment","BudgetPIDController","CostControlLoop","CostRateReading","CostRateSensor","SpendingTrend"]
_sys.modules[__name__] = _implementation

from minicode.control.cost import (
    BudgetActuator,
    BudgetAdjustment,
    BudgetPIDController,
    CostControlLoop,
    CostRateReading,
    CostRateSensor,
    SpendingTrend,
)

__all__ = [
    "BudgetActuator",
    "BudgetAdjustment",
    "BudgetPIDController",
    "CostControlLoop",
    "CostRateReading",
    "CostRateSensor",
    "SpendingTrend",
]
