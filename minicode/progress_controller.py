"""Compatibility facade for minicode.control.progress."""

import sys as _sys
from minicode.control import progress as _implementation

_implementation.__all__ = ["ProgressAction","ProgressController","ProgressDecision","ProgressSignal"]
_sys.modules[__name__] = _implementation

from minicode.control.progress import (
    ProgressAction,
    ProgressController,
    ProgressDecision,
    ProgressSignal,
)

__all__ = [
    "ProgressAction",
    "ProgressController",
    "ProgressDecision",
    "ProgressSignal",
]
