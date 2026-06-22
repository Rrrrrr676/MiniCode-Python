"""Compatibility facade for minicode.safety.file_review."""

import sys as _sys
from minicode.safety import file_review as _implementation

_implementation.__all__ = ["apply_reviewed_file_change","build_unified_diff","load_existing_file"]
_sys.modules[__name__] = _implementation

from minicode.safety.file_review import (
    apply_reviewed_file_change,
    build_unified_diff,
    load_existing_file,
)

__all__ = [
    "apply_reviewed_file_change",
    "build_unified_diff",
    "load_existing_file",
]
