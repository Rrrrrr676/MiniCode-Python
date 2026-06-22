"""Compatibility facade for minicode.memory.injector."""

import sys as _sys
from minicode.memory import injector as _implementation

_implementation.__all__ = ["InjectedMemory","MemoryInjectionController","MemoryInjectionDecision","MemoryInjectionMode","MemoryInjectionSignal","MemoryInjector"]
_sys.modules[__name__] = _implementation

from minicode.memory.injector import (
    InjectedMemory,
    MemoryInjectionController,
    MemoryInjectionDecision,
    MemoryInjectionMode,
    MemoryInjectionSignal,
    MemoryInjector,
)

__all__ = ["InjectedMemory","MemoryInjectionController","MemoryInjectionDecision","MemoryInjectionMode","MemoryInjectionSignal","MemoryInjector"]
