"""Read deduplication and micro-compaction services."""

from minicode.context.compaction.dispatcher import MicrocompactEngine, ReadDedupManager

__all__ = ["MicrocompactEngine", "ReadDedupManager"]
