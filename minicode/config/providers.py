"""Provider fallback, channel, and validation policy."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from minicode.core.provider_spec import Provider, detect_provider

KNOWN_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-haiku-3-20240307",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-5.5",
    "gpt5.5",
    "o1",
    "o1-mini",
    "o3-mini",
    # OpenRouter popular models
    "openrouter/auto",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-opus-4",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "meta-llama/llama-4-maverick",
    "deepseek/deepseek-r1",
    "deepseek/deepseek-chat",
    "qwen/qwen3-235b-a22b",
    "minimax/minimax-m1",
]

def _coerce_model_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered

def configured_model_fallbacks(
    runtime: dict[str, Any] | None,
    provider_name: str | None = None,
) -> list[str]:
    runtime = runtime or {}
    candidates = _coerce_model_list(runtime.get("fallbackModels"))
    provider_key = (provider_name or "").strip().lower()
    provider_specific_keys = {
        "anthropic": "anthropicFallbackModels",
        "openai": "openaiFallbackModels",
        "openrouter": "openrouterFallbackModels",
        "custom": "customFallbackModels",
    }
    if provider_key in provider_specific_keys:
        candidates.extend(_coerce_model_list(runtime.get(provider_specific_keys[provider_key])))
    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered

def default_model_fallbacks(
    runtime: dict[str, Any] | None,
    provider_name: str | None = None,
    current_model: str | None = None,
) -> list[str]:
    runtime = runtime or {}
    provider_key = (provider_name or "").strip().lower()
    active_model = str(current_model or runtime.get("model", "")).strip()
    candidates: list[str] = []

    has_openai = bool(runtime.get("openaiApiKey")) and _is_valid_http_url(runtime.get("openaiBaseUrl"))
    has_openrouter = bool(runtime.get("openrouterApiKey")) and _is_valid_http_url(runtime.get("openrouterBaseUrl"))

    if provider_key == "anthropic":
        sonnet_default = str(runtime.get("anthropicDefaultSonnetModel") or "claude-sonnet-4-20250514").strip()
        haiku_default = str(runtime.get("anthropicDefaultHaikuModel") or "claude-haiku-3-20240307").strip()
        if active_model == "claude-opus-4-20250514":
            candidates.extend([sonnet_default, haiku_default])
        elif active_model == "claude-haiku-3-20240307":
            candidates.append(sonnet_default)
        elif active_model.startswith("claude-"):
            candidates.append(haiku_default)
        else:
            if has_openai:
                candidates.extend(["gpt-4o", "gpt-4o-mini"])
            if has_openrouter:
                candidates.append("openrouter/auto")
    elif provider_key == "openai":
        if active_model == "gpt-4o-mini":
            candidates.append("gpt-4o")
        elif active_model == "gpt-4o":
            candidates.append("gpt-4o-mini")
        else:
            candidates.extend(["gpt-4o", "gpt-4o-mini"])
        if has_openrouter:
            candidates.append("openrouter/auto")
    elif provider_key == "openrouter":
        candidates.append("openrouter/auto")
        if has_openai:
            candidates.append("gpt-4o-mini")
    elif provider_key == "custom":
        if has_openai:
            candidates.extend(["gpt-4o", "gpt-4o-mini"])
        elif has_openrouter:
            candidates.append("openrouter/auto")

    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if not normalized or normalized == active_model or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered

def effective_model_fallbacks(
    runtime: dict[str, Any] | None,
    provider_name: str | None = None,
    current_model: str | None = None,
) -> list[str]:
    runtime = runtime or {}
    active_model = str(current_model or runtime.get("model", "")).strip()
    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in [
        *configured_model_fallbacks(runtime, provider_name),
        *default_model_fallbacks(runtime, provider_name, current_model=active_model),
    ]:
        normalized = str(candidate or "").strip()
        if not normalized or normalized == active_model or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered

def describe_provider_channel(
    runtime: dict[str, Any] | None,
    provider_name: str | None = None,
) -> str:
    runtime = runtime or {}
    provider_key = (provider_name or "").strip().lower()
    if not provider_key:
        from minicode.core.provider_spec import detect_provider

        provider_key = detect_provider(
            str(runtime.get("model", "")).strip(),
            runtime,
        ).value

    if provider_key == "anthropic":
        has_base = _is_valid_http_url(runtime.get("baseUrl"))
        has_token = bool(runtime.get("authToken"))
        has_key = bool(runtime.get("apiKey"))
        if has_base and has_token and has_key:
            return "anthropic-compatible via baseUrl/authToken (+ apiKey)"
        if has_base and has_token:
            return "anthropic-compatible via baseUrl/authToken"
        if has_key:
            return "anthropic via apiKey"
        return "anthropic channel not configured"

    if provider_key == "openai":
        if runtime.get("openaiApiKey") and _is_valid_http_url(runtime.get("openaiBaseUrl")):
            return "openai via openaiApiKey/openaiBaseUrl"
        return "openai channel not configured"

    if provider_key == "openrouter":
        if runtime.get("openrouterApiKey") and _is_valid_http_url(runtime.get("openrouterBaseUrl")):
            return "openrouter via openrouterApiKey/openrouterBaseUrl"
        return "openrouter channel not configured"

    if provider_key == "custom":
        if runtime.get("customApiKey") and _is_valid_http_url(runtime.get("customBaseUrl")):
            return "custom via customApiKey/customBaseUrl"
        return "custom channel not configured"

    return f"{provider_key or 'unknown'} channel"

def describe_fallback_guidance(
    runtime: dict[str, Any] | None,
    provider_name: str | None = None,
    current_model: str | None = None,
) -> list[str]:
    runtime = runtime or {}
    provider_key = (provider_name or "").strip().lower()
    if not provider_key:
        from minicode.core.provider_spec import detect_provider

        provider_key = detect_provider(
            str(current_model or runtime.get("model", "")).strip(),
            runtime,
        ).value

    active_model = str(current_model or runtime.get("model", "")).strip()
    configured = configured_model_fallbacks(runtime, provider_key)
    defaults = default_model_fallbacks(runtime, provider_key, current_model=active_model)
    guidance: list[str] = []
    provider_specific_key = {
        "anthropic": "anthropicFallbackModels",
        "openai": "openaiFallbackModels",
        "openrouter": "openrouterFallbackModels",
        "custom": "customFallbackModels",
    }.get(provider_key, "fallbackModels")

    if (
        provider_key == "anthropic"
        and bool(runtime.get("authToken"))
        and _is_valid_http_url(runtime.get("baseUrl"))
        and not runtime.get("apiKey")
    ):
        guidance.append(
            "Primary runtime is using a single anthropic-compatible channel from baseUrl/authToken."
        )

    if not configured:
        if defaults:
            preview = ", ".join(defaults[:3])
            guidance.append(
                "Default failover is already available for this runtime"
                f"{': ' + preview if preview else '.'}"
                " If those models are still unavailable on the current provider, "
                f"set fallbackModels or {provider_specific_key} to models that the provider actually exposes, "
                "or switch provider credentials."
            )
        else:
            guidance.append(
                f"Add fallbackModels or {provider_specific_key} to enable model failover."
            )

    if provider_key in {"anthropic", "custom"}:
        if not runtime.get("openaiApiKey") and not runtime.get("openrouterApiKey") and not runtime.get("customApiKey"):
            guidance.append(
                "No local fallback credentials are configured for OpenAI, OpenRouter, or custom providers."
            )
    elif provider_key == "openai":
        if not runtime.get("openrouterApiKey") and not runtime.get("customApiKey"):
            guidance.append(
                "No local fallback credentials are configured for OpenRouter or custom providers."
            )
    elif provider_key == "openrouter":
        if not runtime.get("openaiApiKey") and not runtime.get("customApiKey"):
            guidance.append(
                "No local fallback credentials are configured for OpenAI or custom providers."
            )

    ordered: list[str] = []
    seen: set[str] = set()
    for item in guidance:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered

def _suggest_model_name(typed: str) -> str:
    """根据输入建议最接近的合法模型名称"""
    if not typed:
        return ""

    # 简单的前缀匹配
    for model in KNOWN_MODELS:
        if model.startswith(typed.lower()):
            return model

    # 模糊匹配：包含输入字符的模型
    for model in KNOWN_MODELS:
        if typed.lower() in model:
            return model

    return ""

def _is_valid_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(str(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

def validate_provider_runtime(runtime: dict[str, Any]) -> list[str]:
    """Validate the auth/base-url required by the detected provider.

    A generic API key is not enough: if the selected model routes to OpenAI,
    OpenAI-compatible credentials must be present; likewise for Anthropic,
    OpenRouter, and custom endpoints.
    """
    from minicode.core.provider_spec import Provider, detect_provider

    model = str(runtime.get("model", "")).strip()
    provider = detect_provider(model, runtime)
    errors: list[str] = []

    if provider == Provider.OPENAI:
        if not runtime.get("openaiApiKey"):
            errors.append(
                "Provider is openai for this model, but OPENAI_API_KEY/openaiApiKey is not configured."
            )
        if not _is_valid_http_url(runtime.get("openaiBaseUrl")):
            errors.append("OpenAI base URL must be an http(s) URL.")
    elif provider == Provider.OPENROUTER:
        if not runtime.get("openrouterApiKey"):
            errors.append(
                "Provider is openrouter for this model, but OPENROUTER_API_KEY is not configured."
            )
        if not _is_valid_http_url(runtime.get("openrouterBaseUrl")):
            errors.append("OpenRouter base URL must be an http(s) URL.")
    elif provider == Provider.CUSTOM:
        if not runtime.get("customBaseUrl"):
            errors.append("Provider is custom, but CUSTOM_API_BASE_URL/customBaseUrl is not configured.")
        elif not _is_valid_http_url(runtime.get("customBaseUrl")):
            errors.append("Custom base URL must be an http(s) URL.")
        if not runtime.get("customApiKey"):
            errors.append("Provider is custom, but CUSTOM_API_KEY/customApiKey is not configured.")
    elif provider == Provider.ANTHROPIC:
        if not (runtime.get("apiKey") or runtime.get("authToken")):
            errors.append(
                "Provider is anthropic for this model, but ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN is not configured."
            )
        if not _is_valid_http_url(runtime.get("baseUrl")):
            errors.append("Anthropic base URL must be an http(s) URL.")

    return errors

__all__ = ['KNOWN_MODELS', '_coerce_model_list', 'configured_model_fallbacks', 'default_model_fallbacks', 'effective_model_fallbacks', 'describe_provider_channel', 'describe_fallback_guidance', '_suggest_model_name', '_is_valid_http_url', 'validate_provider_runtime']
