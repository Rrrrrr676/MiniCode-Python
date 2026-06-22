"""User and project-scoped configuration paths."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

MINI_CODE_DIR = Path.home() / ".mini-code"

MINI_CODE_SETTINGS_PATH = MINI_CODE_DIR / "settings.json"

MINI_CODE_HISTORY_PATH = MINI_CODE_DIR / "history.json"

MINI_CODE_PERMISSIONS_PATH = MINI_CODE_DIR / "permissions.json"

MINI_CODE_MCP_PATH = MINI_CODE_DIR / "mcp.json"

MINI_CODE_USER_PROFILE_PATH = MINI_CODE_DIR / "USER.md"

MINI_CODE_MANAGED_POLICY_PATH = MINI_CODE_DIR / "MANAGED.md"

MINI_CODE_EXTENSIONS_DIR = MINI_CODE_DIR / "extensions"

CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

def project_user_profile_path(cwd: str | Path | None = None) -> Path:
    """Return the project-level USER.md path."""
    return Path(cwd or Path.cwd()) / ".mini-code" / "USER.md"

def project_managed_policy_path(cwd: str | Path | None = None) -> Path:
    """Return the project-level MANAGED.md path."""
    return Path(cwd or Path.cwd()) / ".mini-code" / "MANAGED.md"

def project_extensions_dir(cwd: str | Path | None = None) -> Path:
    """Return the project-level extensions directory."""
    return Path(cwd or Path.cwd()) / ".mini-code" / "extensions"

def project_mcp_path(cwd: str | Path | None = None) -> Path:
    return Path(cwd or Path.cwd()) / ".mcp.json"

__all__ = ['CLAUDE_SETTINGS_PATH', 'MINI_CODE_DIR', 'MINI_CODE_EXTENSIONS_DIR', 'MINI_CODE_HISTORY_PATH', 'MINI_CODE_MANAGED_POLICY_PATH', 'MINI_CODE_MCP_PATH', 'MINI_CODE_PERMISSIONS_PATH', 'MINI_CODE_SETTINGS_PATH', 'MINI_CODE_USER_PROFILE_PATH', 'project_extensions_dir', 'project_managed_policy_path', 'project_mcp_path', 'project_user_profile_path']
