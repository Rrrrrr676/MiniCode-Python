"""Compatibility facade for minicode.providers.cost."""

import sys as _sys
from minicode.providers import cost as _implementation

_implementation.__all__ = ["CostTracker","MODEL_PRICING","ModelUsage","calculate_cost"]
_sys.modules[__name__] = _implementation

from minicode.providers.cost import (
    CostTracker,
    MODEL_PRICING,
    ModelUsage,
    calculate_cost,
)

__all__ = [
    "CostTracker",
    "MODEL_PRICING",
    "ModelUsage",
    "calculate_cost",
]
