"""Configuration-neutral provider identification primitives."""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Mapping


class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    CUSTOM = "custom"
    MOCK = "mock"


def detect_provider(
    model: str,
    runtime: Mapping[str, Any] | None = None,
) -> Provider:
    """Identify the provider from a model id and runtime configuration."""
    model_lower = model.lower()

    if os.environ.get("OPENROUTER_API_KEY") or model_lower.startswith("openrouter/"):
        return Provider.OPENROUTER

    vendor_prefixes = (
        "anthropic/",
        "openai/",
        "google/",
        "meta-llama/",
        "deepseek/",
        "qwen/",
        "minimax/",
        "mistralai/",
    )
    if model_lower.startswith(vendor_prefixes):
        if os.environ.get("OPENROUTER_API_KEY"):
            return Provider.OPENROUTER
        if runtime and runtime.get("openaiBaseUrl"):
            return Provider.CUSTOM
        return Provider.OPENROUTER

    if (model_lower.startswith("deepseek") or "deepseek" in model_lower) and os.environ.get(
        "DEEPSEEK_API_KEY"
    ):
        return Provider.CUSTOM

    openai_prefixes = (
        "gpt-5",
        "gpt-4",
        "gpt-3.5",
        "gpt5",
        "o1-",
        "o3-",
        "chatgpt-",
    )
    openai_exact = {
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-5.5",
        "gpt5.5",
        "o1",
        "o1-mini",
        "o3-mini",
    }
    if model_lower in openai_exact or model_lower.startswith(openai_prefixes):
        return Provider.OPENAI
    if os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        return Provider.OPENAI

    custom_base = os.environ.get("CUSTOM_API_BASE_URL", "") or (runtime or {}).get(
        "customBaseUrl", ""
    )
    if custom_base:
        return Provider.CUSTOM

    return Provider.ANTHROPIC


__all__ = ["Provider", "detect_provider"]
