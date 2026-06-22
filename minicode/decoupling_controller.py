"""Compatibility facade for minicode.control.decoupling."""

import sys as _sys
from minicode.control import decoupling as _implementation

_implementation.__all__ = ["CouplingAnalyzer","CouplingMatrix","DecoupledCommand","DecouplingController"]
_sys.modules[__name__] = _implementation

from minicode.control.decoupling import (
    CouplingAnalyzer,
    CouplingMatrix,
    DecoupledCommand,
    DecouplingController,
)

__all__ = [
    "CouplingAnalyzer",
    "CouplingMatrix",
    "DecoupledCommand",
    "DecouplingController",
]
