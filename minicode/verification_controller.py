"""Compatibility facade for minicode.control.verification."""

import sys as _sys
from minicode.control import verification as _implementation

_implementation.__all__ = ["VerificationController","VerificationMode","VerificationPlan","VerificationRisk","VerificationSignal"]
_sys.modules[__name__] = _implementation

from minicode.control.verification import (
    VerificationController,
    VerificationMode,
    VerificationPlan,
    VerificationRisk,
    VerificationSignal,
)

__all__ = [
    "VerificationController",
    "VerificationMode",
    "VerificationPlan",
    "VerificationRisk",
    "VerificationSignal",
]
