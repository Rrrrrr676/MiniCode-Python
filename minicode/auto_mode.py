"""Compatibility facade for minicode.safety.auto_mode."""

import sys as _sys
from minicode.safety import auto_mode as _implementation

_implementation.__all__ = ["AutoModeChecker","DANGEROUS_PATTERNS","HIGH_RISK_COMMANDS","LOW_RISK_TOOLS","MEDIUM_RISK_TOOLS","ModeState","PermissionMode","RiskAssessment","RiskLevel","SAFE_TOOLS","get_checker","get_mode_state","set_permission_mode"]
_sys.modules[__name__] = _implementation

from minicode.safety.auto_mode import (
    AutoModeChecker,
    DANGEROUS_PATTERNS,
    HIGH_RISK_COMMANDS,
    LOW_RISK_TOOLS,
    MEDIUM_RISK_TOOLS,
    ModeState,
    PermissionMode,
    RiskAssessment,
    RiskLevel,
    SAFE_TOOLS,
    get_checker,
    get_mode_state,
    set_permission_mode,
)

__all__ = [
    "AutoModeChecker",
    "DANGEROUS_PATTERNS",
    "HIGH_RISK_COMMANDS",
    "LOW_RISK_TOOLS",
    "MEDIUM_RISK_TOOLS",
    "ModeState",
    "PermissionMode",
    "RiskAssessment",
    "RiskLevel",
    "SAFE_TOOLS",
    "get_checker",
    "get_mode_state",
    "set_permission_mode",
]
