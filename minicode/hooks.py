"""Compatibility facade for minicode.integrations.hooks."""

import sys as _sys
from minicode.integrations import hooks as _implementation

_implementation.__all__ = ["HookContext","HookEvent","HookManager","HookRegistration","create_logging_hook","create_script_hook","fire_hook","fire_hook_sync","get_hook_manager","register_hook"]
_sys.modules[__name__] = _implementation

from minicode.integrations.hooks import (
    HookContext,
    HookEvent,
    HookManager,
    HookRegistration,
    create_logging_hook,
    create_script_hook,
    fire_hook,
    fire_hook_sync,
    get_hook_manager,
    register_hook,
)

__all__ = [
    "HookContext",
    "HookEvent",
    "HookManager",
    "HookRegistration",
    "create_logging_hook",
    "create_script_hook",
    "fire_hook",
    "fire_hook_sync",
    "get_hook_manager",
    "register_hook",
]
