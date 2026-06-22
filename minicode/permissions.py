"""Compatibility facade for minicode.safety.permissions."""

import sys as _sys
from minicode.safety import permissions as _implementation

_implementation.__all__ = ["PermissionGate","PermissionManager"]
_sys.modules[__name__] = _implementation

from minicode.safety.permissions import (
    _classify_dangerous_command,
    _is_within_directory,
    PermissionGate,
    PermissionManager,
)

__all__ = [
    "PermissionGate",
    "PermissionManager",
]
