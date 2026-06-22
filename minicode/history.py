"""Compatibility facade for minicode.persistence.history."""

import sys as _sys
from minicode.persistence import history as _implementation

_implementation.__all__ = ["load_history_entries","save_history_entries"]
_sys.modules[__name__] = _implementation

from minicode.persistence.history import (
    load_history_entries,
    save_history_entries,
)

__all__ = [
    "load_history_entries",
    "save_history_entries",
]
