"""Tests für services.sync – Sync-Logik, Index, Logbuch."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


class TestIsSyncNeeded:
    """Tests für is_sync_needed()."""

    def test_needs_sync_when_no_prior_sync(self, tmp_project):
        from services.sync import is_sync_needed
        assert is_sync_needed("main") is True

    def test_no_sync_when_clean(self, tmp_project):
        from services.sync import set_last_sync, is_sync_needed
        set_last_sync(datetime.now() + timedelta(seconds=10), "main")
        assert is_sync_needed("main") is False

    def test_sync_needed_after_file_change(self, tmp_project):
        from services.sync import set_last_sync
        from datetime import datetime
        # Set sync time to the past
        set_last_sync(datetime.now() - timedelta(hours=1), "main")
        # Create a wiki file
        wiki_root = tmp_project / "wikis" / "main"
        (wiki_root / "new.md").write_text("# New", encoding="utf-8")
        from services.sync import is_sync_needed
        assert is_sync_needed("main") is True

    def test_no_sync_for_nonexistent_wiki(self, tmp_project):
        from services.sync import set_last_sync
        set_last_sync(datetime.now() + timedelta(hours=1), "nonexistent")
        from services.sync import is_sync_needed
        assert is_sync_needed("nonexistent") is False


class TestRegenerateIndex:
    """Tests für regenerate_index()."""

    def test_creates_index_file(self, wiki_with_pages):
        from services.sync import regenerate_index
        result = regenerate_index("main")
        assert result is True
        wiki_root = wiki_with_pages / "wikis" / "main"
        assert (wiki_root / "index.md").exists()

    def test_index_contains_pages(self, wiki_with_pages):
        from services.sync import regenerate_index
        regenerate_index("main")
        wiki_root = wiki_with_pages / "wikis" / "main"
        content = (wiki_root / "index.md").read_text(encoding="utf-8")
        assert "Python" in content
        assert "Rust" in content

    def test_empty_wiki_index(self, tmp_project):
        from services.sync import regenerate_index
        regenerate_index("main")
        wiki_root = tmp_project / "wikis" / "main"
        content = (wiki_root / "index.md").read_text(encoding="utf-8")
        assert "Noch keine Seiten" in content


class TestAppendOwfLog:
    """Tests für append_okf_log()."""

    def test_creates_log_file(self, tmp_project):
        from services.sync import append_okf_log
        append_okf_log("create", "Test-Seite", "Details", "main")
        log_path = tmp_project / "wikis" / "main" / "log.md"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "Test-Seite" in content

    def test_appends_to_existing_log(self, wiki_with_pages):
        from services.sync import append_okf_log
        append_okf_log("update", "Eintrag 1", "Details 1", "main")
        append_okf_log("delete", "Eintrag 2", "Details 2", "main")
        log_path = wiki_with_pages / "wikis" / "main" / "log.md"
        content = log_path.read_text(encoding="utf-8")
        assert "Eintrag 1" in content
        assert "Eintrag 2" in content

    def test_log_action_types(self, tmp_project):
        from services.sync import append_okf_log
        append_okf_log("ingest", "Ingest-Seite", "", "main")
        log_path = tmp_project / "wikis" / "main" / "log.md"
        content = log_path.read_text(encoding="utf-8")
        assert "Creation" in content

    def test_has_frontmatter(self, tmp_project):
        from services.sync import append_okf_log
        append_okf_log("create", "Test", "", "main")
        log_path = tmp_project / "wikis" / "main" / "log.md"
        content = log_path.read_text(encoding="utf-8")
        assert content.startswith("---")


class TestSyncStatus:
    """Tests für persistente Sync-Zeitstempel."""

    def test_set_and_get_last_sync(self, tmp_project):
        from services.sync import set_last_sync, get_last_sync
        now = datetime.now()
        set_last_sync(now, "main")
        last = get_last_sync("main")
        assert last is not None

    def test_get_last_sync_nonexistent(self, tmp_project):
        from services.sync import get_last_sync
        assert get_last_sync("main") is None

    def test_per_wiki_sync_times(self, tmp_project):
        from services.sync import set_last_sync, get_last_sync
        set_last_sync(datetime.now(), "wiki1")
        set_last_sync(datetime.now() - timedelta(hours=1), "wiki2")
        assert get_last_sync("wiki1") is not None
        assert get_last_sync("wiki2") is not None
