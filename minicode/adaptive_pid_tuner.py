"""Compatibility facade for minicode.control.adaptive_pid."""

import sys as _sys
from minicode.control import adaptive_pid as _implementation

_implementation.__all__ = ["AdaptivePIDTuner","GradientBasedTuner","PIDParameters","RelayFeedbackTuner","TuningMethod","TuningResult","ZieglerNicholsTuner"]
_sys.modules[__name__] = _implementation

from minicode.control.adaptive_pid import (
    AdaptivePIDTuner,
    GradientBasedTuner,
    PIDParameters,
    RelayFeedbackTuner,
    TuningMethod,
    TuningResult,
    ZieglerNicholsTuner,
)

__all__ = [
    "AdaptivePIDTuner",
    "GradientBasedTuner",
    "PIDParameters",
    "RelayFeedbackTuner",
    "TuningMethod",
    "TuningResult",
    "ZieglerNicholsTuner",
]
