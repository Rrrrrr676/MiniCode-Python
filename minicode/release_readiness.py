"""Compatibility facade for minicode.runtime.release_readiness."""

import sys as _sys
from minicode.runtime import release_readiness as _implementation

_implementation.__all__ = ["ReleaseCheck","classify_provider_outcome","release_readiness_as_dict","release_readiness_as_markdown","summarize_release_status"]
_sys.modules[__name__] = _implementation

from minicode.runtime.release_readiness import (
    ReleaseCheck,
    classify_provider_outcome,
    release_readiness_as_dict,
    release_readiness_as_markdown,
    summarize_release_status,
)

__all__ = [
    "ReleaseCheck",
    "classify_provider_outcome",
    "release_readiness_as_dict",
    "release_readiness_as_markdown",
    "summarize_release_status",
]
