"""Compatibility facade for minicode.cli.shortcuts."""

import sys as _sys
from minicode.cli import shortcuts as _implementation

_implementation.__all__ = ["parse_local_tool_shortcut"]
_sys.modules[__name__] = _implementation

from minicode.cli.shortcuts import (
    parse_local_tool_shortcut,
)

__all__ = [
    "parse_local_tool_shortcut",
]
