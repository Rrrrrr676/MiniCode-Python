"""Compatibility facade for minicode.control.feedback."""

import sys as _sys
from minicode.control import feedback as _implementation

_implementation.__all__ = ["ControlSignal","FeedbackController","FeedbackMode","PIDController","SystemState"]
_sys.modules[__name__] = _implementation

from minicode.control.feedback import (
    ControlSignal,
    FeedbackController,
    FeedbackMode,
    PIDController,
    SystemState,
)

__all__ = [
    "ControlSignal",
    "FeedbackController",
    "FeedbackMode",
    "PIDController",
    "SystemState",
]
