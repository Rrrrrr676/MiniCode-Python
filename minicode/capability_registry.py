"""Compatibility facade for minicode.runtime.capabilities."""

import sys as _sys
from minicode.runtime import capabilities as _implementation

_implementation.__all__ = ["Capability","CapabilityDomain","CapabilityMetadata","CapabilityRegistry","CapabilityScope","RegisteredCapability","capability","get_registry","register_instance_capability"]
_sys.modules[__name__] = _implementation

from minicode.runtime.capabilities import (
    Capability,
    CapabilityDomain,
    CapabilityMetadata,
    CapabilityRegistry,
    CapabilityScope,
    RegisteredCapability,
    capability,
    get_registry,
    register_instance_capability,
)

__all__ = [
    "Capability",
    "CapabilityDomain",
    "CapabilityMetadata",
    "CapabilityRegistry",
    "CapabilityScope",
    "RegisteredCapability",
    "capability",
    "get_registry",
    "register_instance_capability",
]
