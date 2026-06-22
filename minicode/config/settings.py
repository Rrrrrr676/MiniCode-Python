"""Settings loading, merging, persistence, and runtime assembly."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from .paths import *
from .mcp import _read_json_file, project_mcp_path, read_mcp_config_file
from .providers import _coerce_model_list

def read_settings_file(file_path: Path) -> dict[str, Any]:
    return _read_json_file(file_path)

def merge_settings(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged_mcp = dict(base.get("mcpServers", {}))
    for name, server in override.get("mcpServers", {}).items():
        current = dict(merged_mcp.get(name, {}))
        next_server = dict(server)
        current.update(next_server)
        current["env"] = {
            **dict(merged_mcp.get(name, {}).get("env", {})),
            **dict(next_server.get("env", {})),
        }
        merged_mcp[name] = current

    return {
        **base,
        **override,
        "env": {
            **dict(base.get("env", {})),
            **dict(override.get("env", {})),
        },
        "mcpServers": merged_mcp,
    }

def load_effective_settings(cwd: str | Path | None = None) -> dict[str, Any]:
    claude_settings = read_settings_file(CLAUDE_SETTINGS_PATH)
    global_mcp = read_mcp_config_file(MINI_CODE_MCP_PATH)
    project_mcp = read_mcp_config_file(project_mcp_path(cwd))
    mini_code_settings = read_settings_file(MINI_CODE_SETTINGS_PATH)

    return merge_settings(
        merge_settings(
            merge_settings(claude_settings, {"mcpServers": global_mcp}),
            {"mcpServers": project_mcp},
        ),
        mini_code_settings,
    )

def save_mini_code_settings(updates: dict[str, Any]) -> None:
    MINI_CODE_DIR.mkdir(parents=True, exist_ok=True)
    existing = read_settings_file(MINI_CODE_SETTINGS_PATH)
    next_settings = merge_settings(existing, updates)
    MINI_CODE_SETTINGS_PATH.write_text(
        json.dumps(next_settings, indent=2) + "\n",
        encoding="utf-8",
    )

def load_runtime_config(cwd: str | Path | None = None) -> dict[str, Any]:
    effective = load_effective_settings(cwd)
    settings_env = dict(effective.get("env", {}))
    env = {**settings_env, **os.environ}

    def runtime_setting(name: str, *, prefer_settings_env: bool = False) -> str:
        if prefer_settings_env:
            value = settings_env.get(name)
            if value not in (None, ""):
                return str(value).strip()
        value = os.environ.get(name)
        if value not in (None, ""):
            return str(value).strip()
        value = settings_env.get(name)
        if value not in (None, ""):
            return str(value).strip()
        return ""

    model = (
        os.environ.get("MINI_CODE_MODEL")
        or effective.get("model")
        or runtime_setting("ANTHROPIC_MODEL", prefer_settings_env=True)
    )

    # --- Provider-specific base URLs ---
    # Anthropic
    base_url = runtime_setting("ANTHROPIC_BASE_URL", prefer_settings_env=True) or "https://api.anthropic.com"
    auth_token = runtime_setting("ANTHROPIC_AUTH_TOKEN", prefer_settings_env=True) or None
    api_key = runtime_setting("ANTHROPIC_API_KEY", prefer_settings_env=True) or None

    # OpenAI
    openai_base_url = (
        runtime_setting("OPENAI_BASE_URL", prefer_settings_env=True)
        or runtime_setting("OPENAI_API_BASE", prefer_settings_env=True)
        or effective.get("openaiBaseUrl", "")
        or "https://api.openai.com"
    )
    openai_api_key = (
        runtime_setting("OPENAI_API_KEY", prefer_settings_env=True)
        or effective.get("openaiApiKey", "")
    )

    # OpenRouter
    openrouter_base_url = (
        runtime_setting("OPENROUTER_BASE_URL", prefer_settings_env=True)
        or "https://openrouter.ai/api"
    )
    openrouter_api_key = runtime_setting("OPENROUTER_API_KEY", prefer_settings_env=True)

    # Custom endpoint
    custom_base_url = (
        runtime_setting("CUSTOM_API_BASE_URL", prefer_settings_env=True)
        or effective.get("customBaseUrl", "")
    )
    custom_api_key = (
        runtime_setting("CUSTOM_API_KEY", prefer_settings_env=True)
        or effective.get("customApiKey", "")
        or openai_api_key
    )

    raw_max_output_tokens = (
        os.environ.get("MINI_CODE_MAX_OUTPUT_TOKENS")
        or effective.get("maxOutputTokens")
        or env.get("MINI_CODE_MAX_OUTPUT_TOKENS")
    )
    max_output_tokens = None
    if raw_max_output_tokens is not None:
        try:
            parsed = int(raw_max_output_tokens)
            if parsed > 0:
                max_output_tokens = parsed
        except (TypeError, ValueError):
            max_output_tokens = None

    # Validate: at least one auth method must be available
    has_auth = any([
        auth_token, api_key, openai_api_key, openrouter_api_key, custom_api_key,
    ])
    if not model:
        raise RuntimeError("No model configured. Set ~/.mini-code/settings.json or ANTHROPIC_MODEL.")
    if not has_auth:
        raise RuntimeError(
            "No auth configured. Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, "
            "OPENROUTER_API_KEY, or CUSTOM_API_KEY."
        )

    # --- User profile paths ---
    global_user_profile = MINI_CODE_USER_PROFILE_PATH
    proj_user_profile = project_user_profile_path(cwd)
    global_managed_policy = MINI_CODE_MANAGED_POLICY_PATH
    proj_managed_policy = project_managed_policy_path(cwd)
    global_extensions = MINI_CODE_EXTENSIONS_DIR
    proj_extensions = project_extensions_dir(cwd)

    # --- User preferences from settings (lightweight, not from USER.md) ---
    user_preferences = effective.get("userPreferences", {})
    response_language = (
        str(env.get("MINI_CODE_LANGUAGE", "")).strip()
        or user_preferences.get("language", "")
    )
    response_verbosity = (
        str(env.get("MINI_CODE_VERBOSITY", "")).strip()
        or user_preferences.get("verbosity", "")
    )
    fallback_models = _coerce_model_list(
        os.environ.get("MINI_CODE_MODEL_FALLBACKS", "")
        or effective.get("fallbackModels", [])
    )
    anthropic_fallback_models = _coerce_model_list(
        os.environ.get("ANTHROPIC_MODEL_FALLBACKS", "")
        or effective.get("anthropicFallbackModels", [])
    )
    openai_fallback_models = _coerce_model_list(
        os.environ.get("OPENAI_MODEL_FALLBACKS", "")
        or effective.get("openaiFallbackModels", [])
    )
    openrouter_fallback_models = _coerce_model_list(
        os.environ.get("OPENROUTER_MODEL_FALLBACKS", "")
        or effective.get("openrouterFallbackModels", [])
    )
    custom_fallback_models = _coerce_model_list(
        os.environ.get("CUSTOM_MODEL_FALLBACKS", "")
        or effective.get("customFallbackModels", [])
    )

    return {
        "model": model,
        "configuredModel": model,
        "baseUrl": base_url,
        "authToken": auth_token,
        "apiKey": api_key,
        "anthropicDefaultSonnetModel": str(
            runtime_setting("ANTHROPIC_DEFAULT_SONNET_MODEL", prefer_settings_env=True)
            or effective.get("anthropicDefaultSonnetModel")
            or runtime_setting("ANTHROPIC_MODEL", prefer_settings_env=True)
            or effective.get("model", "")
        ).strip(),
        "anthropicDefaultOpusModel": str(
            runtime_setting("ANTHROPIC_DEFAULT_OPUS_MODEL", prefer_settings_env=True)
            or effective.get("anthropicDefaultOpusModel")
            or runtime_setting("ANTHROPIC_MODEL", prefer_settings_env=True)
            or effective.get("model", "")
        ).strip(),
        "anthropicDefaultHaikuModel": str(
            runtime_setting("ANTHROPIC_DEFAULT_HAIKU_MODEL", prefer_settings_env=True)
            or effective.get("anthropicDefaultHaikuModel")
            or runtime_setting("ANTHROPIC_MODEL", prefer_settings_env=True)
            or effective.get("model", "")
        ).strip(),
        "openaiBaseUrl": openai_base_url,
        "openaiApiKey": openai_api_key,
        "openrouterBaseUrl": openrouter_base_url,
        "openrouterApiKey": openrouter_api_key,
        "customBaseUrl": custom_base_url,
        "customApiKey": custom_api_key,
        "maxOutputTokens": max_output_tokens,
        "mcpServers": effective.get("mcpServers", {}),
        "globalUserProfilePath": str(global_user_profile),
        "projectUserProfilePath": str(proj_user_profile),
        "globalManagedPolicyPath": str(global_managed_policy),
        "projectManagedPolicyPath": str(proj_managed_policy),
        "globalExtensionsDir": str(global_extensions),
        "projectExtensionsDir": str(proj_extensions),
        "responseLanguage": response_language,
        "responseVerbosity": response_verbosity,
        "fallbackModels": fallback_models,
        "anthropicFallbackModels": anthropic_fallback_models,
        "openaiFallbackModels": openai_fallback_models,
        "openrouterFallbackModels": openrouter_fallback_models,
        "customFallbackModels": custom_fallback_models,
        "runtimeProfile": str(
            os.environ.get("MINI_CODE_RUNTIME_PROFILE")
            or effective.get("runtimeProfile", "")
            or "single"
        ).strip().lower(),
        "toolProfile": str(
            os.environ.get("MINI_CODE_TOOL_PROFILE")
            or effective.get("toolProfile", "")
            or "core"
        ).strip().lower(),
        "sourceSummary": f"config: {MINI_CODE_SETTINGS_PATH} > {CLAUDE_SETTINGS_PATH} > process.env",
    }

__all__ = ['read_settings_file', 'merge_settings', 'load_effective_settings', 'save_mini_code_settings', 'load_runtime_config']
