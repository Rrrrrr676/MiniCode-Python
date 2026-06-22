"""Compatibility facade for minicode.control.ablation."""

import sys as _sys
from minicode.control import ablation as _implementation

_implementation.__all__ = ["AblationArmResult","AblationTaskProfile","CyberneticAblationRunner","DEFAULT_TASKS","format_ablation_report","load_harness_run_evidence","load_harness_task_profiles"]
_sys.modules[__name__] = _implementation

from minicode.control.ablation import (
    AblationArmResult,
    AblationTaskProfile,
    CyberneticAblationRunner,
    DEFAULT_TASKS,
    format_ablation_report,
    load_harness_run_evidence,
    load_harness_task_profiles,
)

__all__ = [
    "AblationArmResult",
    "AblationTaskProfile",
    "CyberneticAblationRunner",
    "DEFAULT_TASKS",
    "format_ablation_report",
    "load_harness_run_evidence",
    "load_harness_task_profiles",
]
