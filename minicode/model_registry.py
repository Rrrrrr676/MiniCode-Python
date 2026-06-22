"""Compatibility facade for minicode.providers.registry."""

import sys as _sys
from minicode.providers import registry as _implementation

_implementation.__all__ = ["BUILTIN_MODELS","ModelInfo","ModelSelectionController","ModelSelectionDecision","ModelSelectionSignal","ModelSwitch","ProviderConfig","ReasoningEffort","build_provider_config","create_model_adapter","format_model_list","format_model_status","list_available_models","resolve_model_info"]
_sys.modules[__name__] = _implementation

from minicode.providers.registry import (
    BUILTIN_MODELS,
    ModelInfo,
    ModelSelectionController,
    ModelSelectionDecision,
    ModelSelectionSignal,
    ModelSwitch,
    ProviderConfig,
    ReasoningEffort,
    build_provider_config,
    create_model_adapter,
    format_model_list,
    format_model_status,
    list_available_models,
    resolve_model_info,
)

__all__ = [
    "BUILTIN_MODELS",
    "ModelInfo",
    "ModelSelectionController",
    "ModelSelectionDecision",
    "ModelSelectionSignal",
    "ModelSwitch",
    "ProviderConfig",
    "ReasoningEffort",
    "build_provider_config",
    "create_model_adapter",
    "format_model_list",
    "format_model_status",
    "list_available_models",
    "resolve_model_info",
]
