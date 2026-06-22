"""Compatibility facade for minicode.runtime.routing."""

import sys as _sys
from minicode.runtime import routing as _implementation

_implementation.__all__ = ["AgentRouter","DEFAULT_TIERS","ModelTier","RoutingDecision","TaskComplexity","TaskProfile","extract_task_profile","get_agent_router","reset_agent_router"]
_sys.modules[__name__] = _implementation

from minicode.runtime.routing import (
    AgentRouter,
    DEFAULT_TIERS,
    ModelTier,
    RoutingDecision,
    TaskComplexity,
    TaskProfile,
    extract_task_profile,
    get_agent_router,
    reset_agent_router,
)

__all__ = [
    "AgentRouter",
    "DEFAULT_TIERS",
    "ModelTier",
    "RoutingDecision",
    "TaskComplexity",
    "TaskProfile",
    "extract_task_profile",
    "get_agent_router",
    "reset_agent_router",
]
