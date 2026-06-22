"""Configuration-independent model fallback selection."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


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
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _is_valid_http_url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value or ""))
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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
    return list(dict.fromkeys(candidates))


def default_model_fallbacks(
    runtime: dict[str, Any] | None,
    provider_name: str | None = None,
    current_model: str | None = None,
) -> list[str]:
    runtime = runtime or {}
    provider_key = (provider_name or "").strip().lower()
    active_model = str(current_model or runtime.get("model", "")).strip()
    candidates: list[str] = []
    has_openai = bool(runtime.get("openaiApiKey")) and _is_valid_http_url(
        runtime.get("openaiBaseUrl")
    )
    has_openrouter = bool(runtime.get("openrouterApiKey")) and _is_valid_http_url(
        runtime.get("openrouterBaseUrl")
    )

    if provider_key == "anthropic":
        sonnet_default = str(
            runtime.get("anthropicDefaultSonnetModel") or "claude-sonnet-4-20250514"
        ).strip()
        haiku_default = str(
            runtime.get("anthropicDefaultHaikuModel") or "claude-haiku-3-20240307"
        ).strip()
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
        if normalized and normalized != active_model and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


__all__ = ["configured_model_fallbacks", "default_model_fallbacks"]
