"""Memory storage boundary.

Persistence remains encapsulated by ``MemoryManager`` while this module offers
the stable storage-facing types used by callers during migration.
"""

from minicode.memory.manager import MemoryFile, MemoryPaths

__all__ = ["MemoryFile", "MemoryPaths"]
