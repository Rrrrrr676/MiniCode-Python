"""Compatibility facade for minicode.runtime.tasks.object."""

import sys as _sys
from minicode.runtime.tasks import object as _implementation

_implementation.__all__ = ["Constraint","ConstraintType","ExpectedOutput","TaskBuilder","TaskObject","TaskState","build_task","get_task_builder"]
_sys.modules[__name__] = _implementation

from minicode.runtime.tasks.object import (
    Constraint,
    ConstraintType,
    ExpectedOutput,
    TaskBuilder,
    TaskObject,
    TaskState,
    build_task,
    get_task_builder,
)

__all__ = [
    "Constraint",
    "ConstraintType",
    "ExpectedOutput",
    "TaskBuilder",
    "TaskObject",
    "TaskState",
    "build_task",
    "get_task_builder",
]
