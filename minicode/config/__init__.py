"""Explicit public configuration API."""

from .paths import *
from .paths import __all__ as _paths_all
from .providers import *
from .providers import __all__ as _providers_all
from .mcp import *
from .mcp import __all__ as _mcp_all
from .settings import *
from .settings import __all__ as _settings_all
from .diagnostics import *
from .diagnostics import __all__ as _diagnostics_all

__all__ = list(dict.fromkeys([
    *_paths_all, *_providers_all, *_mcp_all, *_settings_all, *_diagnostics_all,
]))
