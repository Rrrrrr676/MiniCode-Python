"""Compatibility facade for minicode.runtime.pipeline."""

import sys as _sys
from minicode.runtime import pipeline as _implementation

_implementation.__all__ = ["PipelineEngine","PipelinePlan","PipelineResult","Step","StepExecutor","StepPlanner","StepState","StepType","get_pipeline_engine","process_task"]
_sys.modules[__name__] = _implementation

from minicode.runtime.pipeline import (
    PipelineEngine,
    PipelinePlan,
    PipelineResult,
    Step,
    StepExecutor,
    StepPlanner,
    StepState,
    StepType,
    get_pipeline_engine,
    process_task,
)

__all__ = [
    "PipelineEngine",
    "PipelinePlan",
    "PipelineResult",
    "Step",
    "StepExecutor",
    "StepPlanner",
    "StepState",
    "StepType",
    "get_pipeline_engine",
    "process_task",
]
