"""Compatibility facade for minicode.integrations.mcp."""

import sys as _sys
from minicode.integrations import mcp as _implementation

_implementation.__all__ = ["ALLOWED_COMMANDS","DANGEROUS_SHELL_CHARS","MAX_MCP_PAYLOAD_BYTES","McpServerSummary","StdioMcpClient","create_mcp_backed_tools"]
_sys.modules[__name__] = _implementation

from minicode.integrations.mcp import (
    _validate_mcp_command,
    ALLOWED_COMMANDS,
    DANGEROUS_SHELL_CHARS,
    MAX_MCP_PAYLOAD_BYTES,
    McpServerSummary,
    StdioMcpClient,
    create_mcp_backed_tools,
)

__all__ = [
    "ALLOWED_COMMANDS",
    "DANGEROUS_SHELL_CHARS",
    "MAX_MCP_PAYLOAD_BYTES",
    "McpServerSummary",
    "StdioMcpClient",
    "create_mcp_backed_tools",
]
