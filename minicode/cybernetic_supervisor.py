"""Compatibility facade for minicode.control.supervisor."""

import sys as _sys
from minicode.control import supervisor as _implementation

_implementation.__all__ = ["ControlSnapshot","CyberneticSupervisor","SUPERVISOR_STATE_PATH","SupervisorReport","SupervisorRisk","load_supervisor_report","save_supervisor_report"]
_sys.modules[__name__] = _implementation

from minicode.control.supervisor import (
    ControlSnapshot,
    CyberneticSupervisor,
    SUPERVISOR_STATE_PATH,
    SupervisorReport,
    SupervisorRisk,
    load_supervisor_report,
    save_supervisor_report,
)

__all__ = [
    "ControlSnapshot",
    "CyberneticSupervisor",
    "SUPERVISOR_STATE_PATH",
    "SupervisorReport",
    "SupervisorRisk",
    "load_supervisor_report",
    "save_supervisor_report",
]
