"""Runtime-facing exports for product surface snapshots."""

from minicode.integrations.product_surfaces import (
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

__all__ = [name for name in globals() if not name.startswith("_")]
