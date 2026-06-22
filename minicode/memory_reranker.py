"""Compatibility facade for minicode.memory.reranker."""

import sys as _sys
from minicode.memory import reranker as _implementation

_implementation.__all__ = ["MemoryReranker","RERANK_PROMPT","RerankCandidate","RerankResult","create_reranker"]
_sys.modules[__name__] = _implementation

from minicode.memory.reranker import (
    MemoryReranker,
    RERANK_PROMPT,
    RerankCandidate,
    RerankResult,
    create_reranker,
)

__all__ = ["MemoryReranker","RERANK_PROMPT","RerankCandidate","RerankResult","create_reranker"]
