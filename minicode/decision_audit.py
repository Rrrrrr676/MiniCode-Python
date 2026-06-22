"""Compatibility facade for minicode.observability.decision_audit."""

import sys as _sys
from minicode.observability import decision_audit as _implementation

_implementation.__all__ = ["DecisionAuditor","DecisionOutcome","DecisionRecord","DecisionType","audited","get_auditor"]
_sys.modules[__name__] = _implementation

from minicode.observability.decision_audit import (
    DecisionAuditor,
    DecisionOutcome,
    DecisionRecord,
    DecisionType,
    audited,
    get_auditor,
)

__all__ = [
    "DecisionAuditor",
    "DecisionOutcome",
    "DecisionRecord",
    "DecisionType",
    "audited",
    "get_auditor",
]
