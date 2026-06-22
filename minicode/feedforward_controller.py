"""Compatibility facade for minicode.control.feedforward."""

import sys as _sys
from minicode.control import feedforward as _implementation

_implementation.__all__ = ["FeedforwardController","PreemptionLevel","PreemptiveConfig","RiskAssessment"]
_sys.modules[__name__] = _implementation

from minicode.control.feedforward import (
    FeedforwardController,
    PreemptionLevel,
    PreemptiveConfig,
    RiskAssessment,
)

__all__ = [
    "FeedforwardController",
    "PreemptionLevel",
    "PreemptiveConfig",
    "RiskAssessment",
]
