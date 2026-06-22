"""Compatibility facade for minicode.runtime.product_surfaces."""

import sys as _sys
from minicode.runtime import product_surfaces as _implementation

_implementation.__all__ = ["DelegationStatus","ExtensionManifest","HookStatus","InstructionLayer","PromptBundle","ReadinessReport","build_delegation_status","build_hook_status","build_product_snapshot","build_readiness_report","collect_extension_manifests","collect_instruction_layers","extension_manifest_payload","extension_search_roots","format_extension_summary","format_instruction_summary","resolve_extension_manifest","set_extension_enabled"]
_sys.modules[__name__] = _implementation

from minicode.runtime.product_surfaces import (
    _preview_text,
    DelegationStatus,
    ExtensionManifest,
    HookStatus,
    InstructionLayer,
    PromptBundle,
    ReadinessReport,
    build_delegation_status,
    build_hook_status,
    build_product_snapshot,
    build_readiness_report,
    collect_extension_manifests,
    collect_instruction_layers,
    extension_manifest_payload,
    extension_search_roots,
    format_extension_summary,
    format_instruction_summary,
    resolve_extension_manifest,
    set_extension_enabled,
)

__all__ = [
    "DelegationStatus",
    "ExtensionManifest",
    "HookStatus",
    "InstructionLayer",
    "PromptBundle",
    "ReadinessReport",
    "build_delegation_status",
    "build_hook_status",
    "build_product_snapshot",
    "build_readiness_report",
    "collect_extension_manifests",
    "collect_instruction_layers",
    "extension_manifest_payload",
    "extension_search_roots",
    "format_extension_summary",
    "format_instruction_summary",
    "resolve_extension_manifest",
    "set_extension_enabled",
]
