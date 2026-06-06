import minicode.config as config_module
from minicode.config import (
    default_model_fallbacks,
    effective_model_fallbacks,
    load_runtime_config,
    merge_settings,
    validate_provider_runtime,
)


def test_merge_settings_merges_env_and_mcp_servers() -> None:
    merged = merge_settings(
        {
            "env": {"A": "1"},
            "mcpServers": {
                "fs": {"command": "npx", "args": ["a"], "env": {"X": "1"}}
            },
        },
        {
            "env": {"B": "2"},
            "mcpServers": {
                "fs": {"command": "uvx", "env": {"Y": "2"}},
                "search": {"command": "python"},
            },
        },
    )

    assert merged["env"] == {"A": "1", "B": "2"}
    assert merged["mcpServers"]["fs"]["command"] == "uvx"
    assert merged["mcpServers"]["fs"]["args"] == ["a"]
    assert merged["mcpServers"]["fs"]["env"] == {"X": "1", "Y": "2"}
    assert merged["mcpServers"]["search"]["command"] == "python"


def test_validate_provider_runtime_rejects_mismatched_provider_key() -> None:
    errors = validate_provider_runtime(
        {
            "model": "gpt-4o",
            "openaiApiKey": "",
            "apiKey": "anthropic-key-does-not-unlock-openai",
            "openaiBaseUrl": "https://api.openai.com",
        }
    )

    assert any("OPENAI_API_KEY" in error for error in errors)


def test_validate_provider_runtime_accepts_openrouter_prefixed_model() -> None:
    errors = validate_provider_runtime(
        {
            "model": "anthropic/claude-sonnet-4",
            "openrouterApiKey": "sk-or-test",
            "openrouterBaseUrl": "https://openrouter.ai/api",
        }
    )

    assert errors == []


def test_load_runtime_config_includes_runtime_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        config_module,
        "load_effective_settings",
        lambda cwd=None: {
            "model": "anthropic/claude-sonnet-4",
            "runtimeProfile": "single-deep",
            "env": {"ANTHROPIC_API_KEY": "test-key"},
        },
    )
    monkeypatch.delenv("MINI_CODE_RUNTIME_PROFILE", raising=False)
    monkeypatch.delenv("MINI_CODE_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    runtime = load_runtime_config(cwd=".")

    assert runtime["runtimeProfile"] == "single-deep"


def test_load_runtime_config_includes_anthropic_family_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        config_module,
        "load_effective_settings",
        lambda cwd=None: {
            "model": "deepseek-v4-pro[1m]",
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "test-token",
                "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-pro[1m]",
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro[1m]",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-v4-pro[1m]",
            },
        },
    )
    monkeypatch.delenv("MINI_CODE_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_SONNET_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_OPUS_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", raising=False)

    runtime = load_runtime_config(cwd=".")

    assert runtime["anthropicDefaultSonnetModel"] == "deepseek-v4-pro[1m]"
    assert runtime["anthropicDefaultOpusModel"] == "deepseek-v4-pro[1m]"
    assert runtime["anthropicDefaultHaikuModel"] == "deepseek-v4-pro[1m]"


def test_load_runtime_config_includes_structured_fallback_models(monkeypatch) -> None:
    monkeypatch.setattr(
        config_module,
        "load_effective_settings",
        lambda cwd=None: {
            "model": "claude-sonnet-4-20250514",
            "fallbackModels": ["gpt-4o", "openrouter/auto"],
            "anthropicFallbackModels": "qwen3.6-plus, claude-haiku-3-20240307",
            "env": {"ANTHROPIC_API_KEY": "test-key"},
        },
    )
    monkeypatch.delenv("MINI_CODE_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MINI_CODE_MODEL_FALLBACKS", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL_FALLBACKS", raising=False)

    runtime = load_runtime_config(cwd=".")

    assert runtime["fallbackModels"] == ["gpt-4o", "openrouter/auto"]
    assert runtime["anthropicFallbackModels"] == [
        "qwen3.6-plus",
        "claude-haiku-3-20240307",
    ]


def test_default_model_fallbacks_seed_bounded_cross_provider_chain_for_non_claude_anthropic() -> None:
    runtime = {
        "model": "deepseek-v4-pro[1m]",
        "openaiApiKey": "openai-key",
        "openaiBaseUrl": "https://api.openai.com",
        "openrouterApiKey": "openrouter-key",
        "openrouterBaseUrl": "https://openrouter.ai/api/v1",
    }

    assert default_model_fallbacks(runtime, "anthropic") == [
        "gpt-4o",
        "gpt-4o-mini",
        "openrouter/auto",
    ]


def test_effective_model_fallbacks_prefer_explicit_before_defaults() -> None:
    runtime = {
        "model": "claude-sonnet-4-20250514",
        "fallbackModels": ["gpt-4o"],
        "anthropicDefaultHaikuModel": "claude-haiku-3-20240307",
        "apiKey": "anthropic-key",
        "baseUrl": "https://api.anthropic.com",
    }

    assert effective_model_fallbacks(runtime, "anthropic") == [
        "gpt-4o",
        "claude-haiku-3-20240307",
    ]


def test_load_runtime_config_falls_back_to_model_for_missing_anthropic_family_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        config_module,
        "load_effective_settings",
        lambda cwd=None: {
            "model": "deepseek-v4-pro[1m]",
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "test-token",
            },
        },
    )
    monkeypatch.delenv("MINI_CODE_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_SONNET_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_OPUS_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", raising=False)

    runtime = load_runtime_config(cwd=".")

    assert runtime["anthropicDefaultSonnetModel"] == "deepseek-v4-pro[1m]"
    assert runtime["anthropicDefaultOpusModel"] == "deepseek-v4-pro[1m]"
    assert runtime["anthropicDefaultHaikuModel"] == "deepseek-v4-pro[1m]"
