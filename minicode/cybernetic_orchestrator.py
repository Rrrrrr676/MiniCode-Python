"""Compatibility facade for minicode.control.orchestrator."""

import sys as _sys
from minicode.control import orchestrator as _implementation

_implementation.__all__ = ["CyberneticOrchestrator"]
_sys.modules[__name__] = _implementation

from minicode.control.orchestrator import (
    CyberneticOrchestrator,
)

__all__ = [
    "CyberneticOrchestrator",
]
