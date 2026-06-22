"""Compatibility facade for minicode.context.compaction.micro_legacy."""

import sys as _sys
from minicode.context.compaction import micro_legacy as _implementation

_implementation.__all__ = ["COMPRESSIBLE_READ_ONLY_TOOLS","COMPRESSIBLE_WRITE_TOOLS","MicroCompactionStats","MicroCompactor","MicroCompactorConfig","NON_COMPRESSIBLE_TOOLS","get_micro_compactor","micro_compact"]
_sys.modules[__name__] = _implementation

from minicode.context.compaction.micro_legacy import (
    COMPRESSIBLE_READ_ONLY_TOOLS,
    COMPRESSIBLE_WRITE_TOOLS,
    MicroCompactionStats,
    MicroCompactor,
    MicroCompactorConfig,
    NON_COMPRESSIBLE_TOOLS,
    get_micro_compactor,
    micro_compact,
)

__all__ = [
    "COMPRESSIBLE_READ_ONLY_TOOLS",
    "COMPRESSIBLE_WRITE_TOOLS",
    "MicroCompactionStats",
    "MicroCompactor",
    "MicroCompactorConfig",
    "NON_COMPRESSIBLE_TOOLS",
    "get_micro_compactor",
    "micro_compact",
]
