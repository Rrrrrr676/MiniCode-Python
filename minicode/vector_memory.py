"""Vector-based memory search — parallel path to BM25.

Uses sentence-transformers (all-MiniLM-L6-v2) for semantic similarity search.
Optional dependency: falls back gracefully if not installed.
Results are merged with BM25 results via reciprocal rank fusion.

Install: pip install sentence-transformers
"""
from __future__ import annotations

import math
from typing import Any

from minicode.logging_config import get_logger

logger = get_logger("vector_memory")


class VectorMemoryStore:
    """Lightweight vector store for semantic memory search.

    Uses all-MiniLM-L6-v2 (384-dim, ~80MB) for local embedding.
    Stores embeddings in-memory with cosine similarity retrieval.
    """

    def __init__(self):
        self._model = None
        self._embeddings: dict[str, list[float]] = {}  # entry_id -> embedding
        self._enabled = False
        self._load_model()

    def _load_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._enabled = True
            logger.info("VectorMemoryStore: loaded all-MiniLM-L6-v2")
        except ImportError:
            logger.info("VectorMemoryStore: sentence-transformers not installed, vector search disabled")
        except Exception as e:
            logger.warning("VectorMemoryStore: model load failed: %s", e)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def index_entries(self, entries: list[Any]) -> int:
        """Index memory entries for vector search. Returns count of indexed entries."""
        if not self._enabled or not self._model:
            return 0

        count = 0
        for entry in entries:
            eid = getattr(entry, 'id', '')
            if eid in self._embeddings:
                continue
            content = getattr(entry, 'content', '')
            if not content.strip():
                continue
            try:
                embedding = self._model.encode(content[:500], show_progress_bar=False)
                self._embeddings[eid] = embedding.tolist()
                count += 1
            except Exception:
                pass
        return count

    def search(
        self, query: str, candidate_ids: list[str] | None = None, top_k: int = 10
    ) -> list[tuple[str, float]]:
        """Vector similarity search. Returns [(entry_id, cosine_similarity), ...]."""
        if not self._enabled or not self._model or not self._embeddings:
            return []

        try:
            query_emb = self._model.encode(query[:500], show_progress_bar=False).tolist()
        except Exception:
            return []

        results: list[tuple[str, float]] = []
        for eid, emb in self._embeddings.items():
            if candidate_ids and eid not in candidate_ids:
                continue
            sim = self._cosine_similarity(query_emb, emb)
            if sim > 0.3:
                results.append((eid, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def clear(self) -> None:
        self._embeddings.clear()


def merge_bm25_vector(
    bm25_results: list[Any],
    vector_results: list[tuple[str, float]],
    k: int = 60,
) -> list[Any]:
    """Reciprocal rank fusion between BM25 and vector results.

    Args:
        bm25_results: MemoryEntry list from BM25 (already ranked).
        vector_results: [(entry_id, cosine_sim), ...] from vector search.
        k: RRF constant (default 60).

    Returns:
        Merged and re-ranked list of MemoryEntry.
    """
    if not vector_results:
        return bm25_results

    # Build rank maps
    bm25_rank: dict[str, int] = {}
    for i, entry in enumerate(bm25_results):
        bm25_rank[getattr(entry, 'id', '')] = i + 1

    vector_rank: dict[str, int] = {}
    for i, (eid, _) in enumerate(vector_results):
        vector_rank[eid] = i + 1

    # Score all entries via RRF
    all_ids = set(bm25_rank.keys()) | set(vector_rank.keys())
    scores: dict[str, float] = {}
    for eid in all_ids:
        score = 0.0
        if eid in bm25_rank:
            score += 1.0 / (k + bm25_rank[eid])
        if eid in vector_rank:
            score += 1.0 / (k + vector_rank[eid])
        scores[eid] = score

    # Sort by RRF score
    eid_to_entry = {getattr(e, 'id', ''): e for e in bm25_results}
    for eid, _ in vector_results:
        if eid not in eid_to_entry:
            # Entry found only via vector search — need to get it from somewhere
            pass

    sorted_ids = sorted(scores.keys(), key=lambda eid: scores[eid], reverse=True)
    return [eid_to_entry[eid] for eid in sorted_ids if eid in eid_to_entry]
