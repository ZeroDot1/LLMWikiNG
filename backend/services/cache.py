"""LLMWikiNG – Zentrales In-Memory-Cache-System.

Verwendet dateibasierte Invalidierung via mtime-Prüfung.
Kein externer Cache-Server nötig – läuft direkt im FastAPI-Prozess.
"""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional


class WikiCache:
    """Thread-sicherer In-Memory-Cache mit mtime-basierter Invalidierung.

    Jeder Cache-Eintrag wird gegen den aktuellen mtime-Fingerabdruck des
    Wiki-Verzeichnisses validiert. Ändert sich eine Datei, wird der gesamte
    Wiki-Cache für diesen Key automatisch invalidiert.
    """

    def __init__(self, max_age_seconds: int = 300) -> None:
        """Erstellt einen neuen Cache.

        Args:
            max_age_seconds: Maximales Alter eines Cache-Eintrags in Sekunden
                             (Fallback, falls mtime-Check nicht möglich).
        """
        self._store: dict[str, dict[str, Any]] = {}  # key -> {value, ts, fingerprint}
        self._lock = threading.RLock()
        self._max_age = max_age_seconds

    # ─── Fingerprint-Berechnung ────────────────────────────────────────────

    def _dir_fingerprint(self, directory: Path) -> str:
        """Berechnet einen Fingerabdruck eines Verzeichnisses basierend auf
        den mtime-Werten aller .md-Dateien. O(n) aber sehr schnell (nur stat()).
        """
        if not directory.exists():
            return "empty"
        try:
            parts = []
            for f in sorted(directory.rglob("*.md")):
                try:
                    parts.append(f"{f.name}:{f.stat().st_mtime_ns}")
                except OSError:
                    pass
            raw = "|".join(parts)
            return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:16]
        except Exception:
            return str(time.time())

    # ─── Öffentliche API ───────────────────────────────────────────────────

    def get(self, key: str, directory: Path) -> Optional[Any]:
        """Gibt den Cache-Wert zurück oder None falls abgelaufen/ungültig."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            # Zeitbasierter Fallback-Check
            if time.monotonic() - entry["ts"] > self._max_age:
                del self._store[key]
                return None
            # mtime-Fingerprint-Check (präziser als Zeit-TTL)
            current_fp = self._dir_fingerprint(directory)
            if current_fp != entry["fingerprint"]:
                del self._store[key]
                return None
            return entry["value"]

    def set(self, key: str, value: Any, directory: Path) -> None:
        """Speichert einen Wert mit aktuellem Fingerabdruck."""
        with self._lock:
            self._store[key] = {
                "value": value,
                "ts": time.monotonic(),
                "fingerprint": self._dir_fingerprint(directory),
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


# Globale Cache-Instanz (Singleton im Prozess)
_cache = WikiCache(max_age_seconds=300)


def get_cache() -> WikiCache:
    """Gibt die globale Cache-Instanz zurück."""
    return _cache
