"""Configuration validation and diagnostic rendering."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from .providers import *
from .settings import load_runtime_config

def validate_config(cwd: str | Path | None = None) -> tuple[bool, list[str]]:
    """验证配置完整性，返回 (是否有效，错误列表)

    检查项：
    1. 模型名称是否配置
    2. API key 是否配置
    3. 模型名称拼写是否正确
    4. MCP 配置文件是否合法
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        config = load_runtime_config(cwd)
        errors.extend(validate_provider_runtime(config))

        # 检查模型名称拼写
        model = config.get("model", "")
        if model and not any(model.lower() == km.lower() for km in KNOWN_MODELS):
            suggestion = _suggest_model_name(model)
            if suggestion:
                warnings.append(
                    f"Unknown model '{model}'. Did you mean '{suggestion}'?"
                )
            else:
                warnings.append(
                    f"Unknown model '{model}'. Known models: {', '.join(KNOWN_MODELS[:3])}..."
                )

        # 检查 MCP 配置
        mcp_servers = config.get("mcpServers", {})
        for name, server in mcp_servers.items():
            if not server.get("command"):
                errors.append(f"MCP server '{name}' has no command configured")

        return len(errors) == 0, errors + warnings

    except RuntimeError as e:
        error_msg = str(e)

        # 提供友好的错误消息
        if "No model configured" in error_msg:
            suggestion = _suggest_model_name(os.environ.get("MINI_CODE_MODEL", ""))
            help_msg = (
                f"Error: {error_msg}\n\n"
                "How to fix:\n"
                "  1. Set model name: export ANTHROPIC_MODEL=claude-sonnet-4-20250514\n"
                "  2. Or edit ~/.mini-code/settings.json:\n"
                f'     {{"model": "claude-sonnet-4-20250514"}}\n'
            )
            if suggestion:
                help_msg += f"\n  Did you mean: {suggestion}?\n"
            help_msg += f"\n  Known models: {', '.join(KNOWN_MODELS[:3])}..."
            errors.append(help_msg)

        elif "No auth configured" in error_msg:
            help_msg = (
                f"Error: {error_msg}\n\n"
                "How to fix:\n"
                "  1. Anthropic:  export ANTHROPIC_API_KEY=sk-ant-...\n"
                "  2. OpenAI:     export OPENAI_API_KEY=sk-...\n"
                "  3. OpenRouter: export OPENROUTER_API_KEY=sk-or-...\n"
                "  4. Custom:     export CUSTOM_API_KEY=... + CUSTOM_API_BASE_URL=...\n"
                "  5. Or edit ~/.mini-code/settings.json:\n"
                '     {"env": {"ANTHROPIC_API_KEY": "sk-ant-..."}}\n'
            )
            errors.append(help_msg)
        else:
            errors.append(str(e))

        return False, errors
    except Exception as e:
        return False, [f"Unexpected error: {e}"]

def format_config_diagnostic(cwd: str | Path | None = None) -> str:
    """格式化配置诊断信息"""
    is_valid, messages = validate_config(cwd)

    lines = ["Configuration Diagnostics", "=" * 40, ""]

    if is_valid:
        lines.append("Status: OK")
        if messages:
            lines.append("")
            lines.append("Warnings:")
            for msg in messages:
                lines.append(f"  [WARN] {msg}")
    else:
        lines.append("Status: ERRORS")
        lines.append("")
        lines.append("Errors:")
        for msg in messages:
            lines.append(f"  [ERROR] {msg}")

    # 显示当前配置摘要
    try:
        config = load_runtime_config(cwd)
        model_name = config.get('model', 'not set')
        lines.append("")
        lines.append("Current Configuration")
        lines.append("-" * 40)
        lines.append(f"  Model: {model_name}")

        # Show provider info
        from minicode.core.provider_spec import Provider, detect_provider
        provider = detect_provider(model_name, config)
        lines.append(f"  Provider: {provider.value}")
        lines.append(f"  Channel: {describe_provider_channel(config, provider.value)}")

        if provider == Provider.ANTHROPIC:
            lines.append(f"  Base URL: {config.get('baseUrl', 'not set')}")
            auth_methods = []
            if config.get("authToken"):
                auth_methods.append("ANTHROPIC_AUTH_TOKEN")
            if config.get("apiKey"):
                auth_methods.append("ANTHROPIC_API_KEY")
        elif provider == Provider.OPENAI:
            lines.append(f"  OpenAI Base URL: {config.get('openaiBaseUrl', 'not set')}")
            auth_methods = ["OPENAI_API_KEY"] if config.get("openaiApiKey") else []
        elif provider == Provider.OPENROUTER:
            lines.append(f"  OpenRouter Base URL: {config.get('openrouterBaseUrl', 'not set')}")
            auth_methods = ["OPENROUTER_API_KEY"] if config.get("openrouterApiKey") else []
        elif provider == Provider.CUSTOM:
            lines.append(f"  Custom Base URL: {config.get('customBaseUrl', 'not set')}")
            auth_methods = ["CUSTOM_API_KEY"] if config.get("customApiKey") else []
        else:
            auth_methods = []

        lines.append(f"  Auth: {', '.join(auth_methods) or 'none'}")

        fallback_models = effective_model_fallbacks(config, provider.value, current_model=model_name)
        if fallback_models:
            lines.append(f"  Fallback Models: {', '.join(fallback_models)}")
        lines.append(f"  MCP Servers: {len(config.get('mcpServers', {}))}")
        lines.append(f"  Tool Profile: {config.get('toolProfile', 'core')}")

        # User profile info
        global_profile_path = config.get('globalUserProfilePath', '')
        project_profile_path = config.get('projectUserProfilePath', '')
        if global_profile_path:
            gp_exists = Path(global_profile_path).exists()
            lines.append(f"  Global Profile: {global_profile_path} ({'exists' if gp_exists else 'not found'})")
        if project_profile_path:
            pp_exists = Path(project_profile_path).exists()
            lines.append(f"  Project Profile: {project_profile_path} ({'exists' if pp_exists else 'not found'})")
        if config.get('responseLanguage'):
            lines.append(f"  Response Language: {config.get('responseLanguage')}")
        if config.get('responseVerbosity'):
            lines.append(f"  Response Verbosity: {config.get('responseVerbosity')}")
    except Exception:
        pass

    return "\n".join(lines)

__all__ = ["validate_config", "format_config_diagnostic"]
