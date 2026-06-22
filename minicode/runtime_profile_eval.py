"""Compatibility facade for minicode.runtime.profile_eval."""

import sys as _sys
from minicode.runtime import profile_eval as _implementation

_implementation.__all__ = ["ProviderDiagnostic","RuntimeEvalCondition","RuntimeEvalRow","RuntimeEvalScenario","evaluate_runtime_profiles","runtime_profile_eval_as_dict","runtime_profile_eval_as_markdown","summarize_runtime_profile_eval"]
_sys.modules[__name__] = _implementation

from minicode.runtime.profile_eval import (
    ProviderDiagnostic,
    RuntimeEvalCondition,
    RuntimeEvalRow,
    RuntimeEvalScenario,
    evaluate_runtime_profiles,
    runtime_profile_eval_as_dict,
    runtime_profile_eval_as_markdown,
    summarize_runtime_profile_eval,
)

__all__ = [
    "ProviderDiagnostic",
    "RuntimeEvalCondition",
    "RuntimeEvalRow",
    "RuntimeEvalScenario",
    "evaluate_runtime_profiles",
    "runtime_profile_eval_as_dict",
    "runtime_profile_eval_as_markdown",
    "summarize_runtime_profile_eval",
]
