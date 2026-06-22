"""Scoped MCP configuration API."""

from minicode.config import (
    get_mcp_config_path,
    load_scoped_mcp_servers,
    read_mcp_config_file,
    save_scoped_mcp_servers,
)

__all__ = [
    "get_mcp_config_path",
    "load_scoped_mcp_servers",
    "read_mcp_config_file",
    "save_scoped_mcp_servers",
]
