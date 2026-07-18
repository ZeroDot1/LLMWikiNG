"""Tests für services.cache – WikiCache In-Memory-Cache."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from services.cache import WikiCache


class TestWikiCache:
    """Tests für den WikiCache."""

    def test_set_and_get(self, tmp_path):
        cache = WikiCache(max_age_seconds=60)
        cache.set("key1", {"data": "test"}, tmp_path)
        result = cache.get("key1", tmp_path)
        assert result == {"data": "test"}

    def test_get_nonexistent_key(self, tmp_path):
        cache = WikiCache()
        assert cache.get("nonexistent", tmp_path) is None

    def test_cache_invalidated_by_file_change(self, tmp_path):
        """Cache-Eintrag sollte ungültig werden, wenn sich Dateien ändern."""
        cache = WikiCache(max_age_seconds=300)
        (tmp_path / "test.md").write_text("original")
        cache.set("key1", [1, 2, 3], tmp_path)

        # Noch gültig
        assert cache.get("key1", tmp_path) == [1, 2, 3]

        # Datei ändern → Cache ungültig
        (tmp_path / "test.md").write_text("modified")
        assert cache.get("key1", tmp_path) is None

    def test_cache_invalidated_by_new_file(self, tmp_path):
        cache = WikiCache(max_age_seconds=300)
        cache.set("key1", "value", tmp_path)
        assert cache.get("key1", tmp_path) == "value"

        # Neue Datei hinzufügen
        (tmp_path / "new.md").write_text("new")
        assert cache.get("key1", tmp_path) is None

    def test_cache_expires_by_time(self, tmp_path):
        cache = WikiCache(max_age_seconds=0)  # Sofort abgelaufen
        cache.set("key1", "value", tmp_path)
        assert cache.get("key1", tmp_path) is None

    def test_invalidate_specific_key(self, tmp_path):
        cache = WikiCache(max_age_seconds=300)
        cache.set("a", 1, tmp_path)
        cache.set("b", 2, tmp_path)
        cache.invalidate("a")
        assert cache.get("a", tmp_path) is None
        assert cache.get("b", tmp_path) == 2

    def test_invalidate_prefix(self, tmp_path):
        cache = WikiCache(max_age_seconds=300)
        cache.set("pages:main", [1], tmp_path)
        cache.set("pages:test", [2], tmp_path)
        cache.set("graph:main", [3], tmp_path)
        cache.invalidate_prefix("pages:")
        assert cache.get("pages:main", tmp_path) is None
        assert cache.get("pages:test", tmp_path) is None
        assert cache.get("graph:main", tmp_path) == [3]

    def test_clear_all(self, tmp_path):
        cache = WikiCache(max_age_seconds=300)
        cache.set("a", 1, tmp_path)
        cache.set("b", 2, tmp_path)
        cache.clear()
        assert cache.get("a", tmp_path) is None
        assert cache.get("b", tmp_path) is None

    def test_stats(self, tmp_path):
        cache = WikiCache(max_age_seconds=300)
        cache.set("a", 1, tmp_path)
        cache.set("b", 2, tmp_path)
        stats = cache.stats()
        assert stats["entries"] == 2
        assert set(stats["keys"]) == {"a", "b"}

    def test_empty_directory_fingerprint(self):
        cache = WikiCache()
        # Non-existent directory
        fp = cache._dir_fingerprint(Path("/nonexistent/path"))
        assert fp == "empty"

    def test_cache_none_value(self, tmp_path):
        """None-Werte sollten korrekt gespeichert/abgerufen werden."""
        cache = WikiCache(max_age_seconds=300)
        cache.set("key1", None, tmp_path)
        assert cache.get("key1", tmp_path) is None

    def test_overwrite_existing_key(self, tmp_path):
        cache = WikiCache(max_age_seconds=300)
        cache.set("key1", "old", tmp_path)
        cache.set("key1", "new", tmp_path)
        assert cache.get("key1", tmp_path) == "new"

    def test_thread_safety_concurrent_access(self, tmp_path):
        """Einfacher Test für Thread-Safety."""
        import threading
        cache = WikiCache(max_age_seconds=300)
        errors = []

        def writer():
            for i in range(100):
                cache.set(f"key{i}", i, tmp_path)

        def reader():
            for i in range(100):
                try:
                    cache.get(f"key{i}", tmp_path)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
