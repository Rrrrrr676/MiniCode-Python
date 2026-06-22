"""Compatibility facade for minicode.memory.vector."""

import sys as _sys
from minicode.memory import vector as _implementation

_implementation.__all__ = ["SparseVectorStore","VectorMemoryStore","merge_bm25_vector"]
_sys.modules[__name__] = _implementation

from minicode.memory.vector import (
    SparseVectorStore,
    VectorMemoryStore,
    merge_bm25_vector,
)

__all__ = ["SparseVectorStore","VectorMemoryStore","merge_bm25_vector"]
