"""Periodic session autosave policy."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from minicode.config import MINI_CODE_DIR
from minicode.observability.logging import log_session_event

from .session_models import SessionData
from .session_storage import AUTOSAVE_INTERVAL_SECONDS, save_session

class AutosaveManager:
    """Manages automatic session saving with rate limiting and delta support.

    Uses incremental saves for autosave (fast) and full saves for
    explicit save commands (consistent).
    """

    def __init__(self, session: SessionData, interval: int = AUTOSAVE_INTERVAL_SECONDS):
        self.session = session
        self.interval = interval
        self._last_save_time = time.time()  # Initialize to current time
        self._dirty = False
        self._full_save_counter = 0

    def mark_dirty(self) -> None:
        """Mark session as needing save."""
        self._dirty = True

    def should_save(self) -> bool:
        """Check if autosave should trigger."""
        if not self._dirty:
            return False
        elapsed = time.time() - self._last_save_time
        return elapsed >= self.interval

    def save_if_needed(self) -> bool:
        """Save if dirty and interval elapsed. Uses delta saves for speed.

        Returns True if saved.
        """
        if self.should_save():
            # Use incremental delta save for autosave (fast)
            save_session(self.session, force_full=False)
            self._last_save_time = time.time()
            self._dirty = False
            self._full_save_counter += 1
            return True
        return False

    def force_save(self) -> None:
        """Force immediate full save regardless of interval."""
        save_session(self.session, force_full=True)
        self._last_save_time = time.time()
        self._dirty = False
        self._full_save_counter = 0

__all__ = ["AutosaveManager"]
