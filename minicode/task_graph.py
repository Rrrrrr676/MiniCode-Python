"""Compatibility facade for minicode.runtime.tasks.graph."""

import sys as _sys
from minicode.runtime.tasks import graph as _implementation

_implementation.__all__ = ["TaskDefinition","TaskGraph","TaskPriority","TaskSlot","TaskState","WorktreeIsolator","delete_task_graph","list_task_graphs","load_task_graph","save_task_graph"]
_sys.modules[__name__] = _implementation

from minicode.runtime.tasks.graph import (
    TaskDefinition,
    TaskGraph,
    TaskPriority,
    TaskSlot,
    TaskState,
    WorktreeIsolator,
    delete_task_graph,
    list_task_graphs,
    load_task_graph,
    save_task_graph,
)

__all__ = [
    "TaskDefinition",
    "TaskGraph",
    "TaskPriority",
    "TaskSlot",
    "TaskState",
    "WorktreeIsolator",
    "delete_task_graph",
    "list_task_graphs",
    "load_task_graph",
    "save_task_graph",
]
