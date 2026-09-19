# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – central in-memory cache with explicit invalidation and TTL."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional


class WikiCache:
    """Thread-safe cache whose hot path performs no filesystem traversal.

    Mutating services explicitly invalidate affected prefixes.  The TTL is a
    safety net for direct filesystem edits and separate processes.
    """

    def __init__(self, max_age_seconds: int = 300) -> None:
        """Erstellt einen neuen Cache.

        Args:
            max_age_seconds: Maximum age of an entry as a direct-edit fallback.
        """
        self._store: dict[str, dict[str, Any]] = {}  # key -> {value, ts}
        self._lock = threading.RLock()
        self._max_age = max_age_seconds

    def get(self, key: str, directory: Path) -> Optional[Any]:
        """Return a value unless it is expired; ``directory`` is API-compatible."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() - entry["ts"] > self._max_age:
                del self._store[key]
                return None
            return entry["value"]

    def set(self, key: str, value: Any, directory: Path) -> None:
        """Store a value; callers invalidate affected keys after mutations."""
        with self._lock:
            self._store[key] = {
                "value": value,
                "ts": time.monotonic(),
            }

    def invalidate(self, key: str) -> None:
        """Löscht einen spezifischen Cache-Eintrag."""
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        """Löscht alle Einträge mit dem gegebenen Key-Präfix."""
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]

    def clear(self) -> None:
        """Löscht den gesamten Cache."""
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        """Gibt Cache-Statistiken zurück."""
        with self._lock:
            return {
                "entries": len(self._store),
                "keys": list(self._store.keys()),
            }


_cache = WikiCache(max_age_seconds=300)


def get_cache() -> WikiCache:
    """Gibt die globale Cache-Instanz zurück."""
    return _cache
