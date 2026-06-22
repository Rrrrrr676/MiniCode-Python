"""Compatibility facade for minicode.cli.management."""

import sys as _sys
from minicode.cli import management as _implementation

_implementation.__all__ = ["maybe_handle_management_command"]
_sys.modules[__name__] = _implementation

from minicode.cli.management import (
    maybe_handle_management_command,
)

__all__ = [
    "maybe_handle_management_command",
]
