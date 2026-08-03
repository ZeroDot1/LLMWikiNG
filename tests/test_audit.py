# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests für services.audit – Audit-Logging SQLite."""

from __future__ import annotations

import sqlite3
import csv
import io
from datetime import datetime, timedelta

import pytest


class TestIsAuditEnabled:
    """Tests für is_audit_enabled()."""

    def test_enabled_by_default(self, tmp_project):
        from services.audit import is_audit_enabled
        assert is_audit_enabled("login_success") is True

    def test_disabled_globally(self, tmp_project):
        from core.config import save_app_config
        from services.audit import is_audit_enabled
        save_app_config({"audit_enabled": False})
        assert is_audit_enabled("login_success") is False

    def test_disabled_by_category(self, tmp_project):
        from core.config import save_app_config
        from services.audit import is_audit_enabled
        save_app_config({"audit_enabled": True, "audit_disabled_categories": ["auth"]})
        assert is_audit_enabled("login_success") is False

    def test_other_categories_still_enabled(self, tmp_project):
        from core.config import save_app_config
        from services.audit import is_audit_enabled
        save_app_config({"audit_enabled": True, "audit_disabled_categories": ["auth"]})
        assert is_audit_enabled("page_save") is True

    def test_unknown_action_defaults_to_system(self, tmp_project):
        from services.audit import is_audit_enabled
        assert is_audit_enabled("unknown_action_xyz") is True

    def test_mcp_category(self, tmp_project):
        from services.audit import is_audit_enabled
        assert is_audit_enabled("mcp_tool_call") is True

    def test_disable_mcp_category(self, tmp_project):
        from core.config import save_app_config
        from services.audit import is_audit_enabled
        save_app_config({"audit_enabled": True, "audit_disabled_categories": ["mcp"]})
        assert is_audit_enabled("mcp_tool_call") is False
        assert is_audit_enabled("page_save") is True


class TestInitDB:
    """Tests für init_db()."""

    def _reset_init(self):
        import services.audit as audit_mod
        audit_mod._db_initialized = False

    def test_creates_database(self, tmp_project):
        self._reset_init()
        from services.audit import init_db, AUDIT_DB
        init_db()
        assert AUDIT_DB.exists()

    def test_creates_correct_table(self, tmp_project):
        self._reset_init()
        from services.audit import init_db, AUDIT_DB
        init_db()
        conn = sqlite3.connect(AUDIT_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_idempotent(self, tmp_project):
        self._reset_init()
        from services.audit import init_db
        init_db()
        init_db()  # Should not raise

    def test_has_category_column(self, tmp_project):
        """Prüft dass die category-Spalte existiert (Migration)."""
        self._reset_init()
        from services.audit import init_db, AUDIT_DB
        init_db()
        conn = sqlite3.connect(AUDIT_DB)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(audit_logs)")
        columns = [col[1] for col in cursor.fetchall()]
        conn.close()
        assert "category" in columns

    def test_has_indexes(self, tmp_project):
        """Prüft dass die Indizes existieren."""
        self._reset_init()
        from services.audit import init_db, AUDIT_DB
        init_db()
        conn = sqlite3.connect(AUDIT_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert "idx_timestamp" in indexes
        assert "idx_action" in indexes
        assert "idx_username" in indexes
        assert "idx_category" in indexes

    def test_wal_mode(self, tmp_project):
        """Prüft dass WAL-Modus aktiviert ist."""
        self._reset_init()
        from services.audit import init_db, AUDIT_DB
        init_db()
        conn = sqlite3.connect(AUDIT_DB)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()
        assert mode.lower() == "wal"


class TestLogAction:
    """Tests für log_action()."""

    def test_logs_action(self, tmp_project):
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("login_success", details="Test login", user_id="u1", username="admin")
        logs, total = get_logs()
        assert total == 1
        assert logs[0]["action"] == "login_success"
        assert logs[0]["username"] == "admin"

    def test_does_not_log_when_disabled(self, tmp_project):
        from core.config import save_app_config
        from services.audit import init_db, log_action, get_logs
        init_db()
        save_app_config({"audit_enabled": False})
        log_action("login_success")
        _, total = get_logs()
        assert total == 0

    def test_stores_ip_address(self, tmp_project):
        """Testet IP-Erkennung (mit Mock-Request)."""
        from services.audit import init_db, log_action, get_logs
        init_db()

        class MockClient:
            host = "192.168.1.1"

        class MockRequest:
            headers = {"user-agent": "TestAgent/1.0"}
            client = MockClient()

        log_action("login_success", request=MockRequest())
        logs, _ = get_logs()
        assert logs[0]["ip_address"] == "192.168.1.1"
        assert logs[0]["user_agent"] == "TestAgent/1.0"

    def test_x_forwarded_for_ip(self, tmp_project):
        from services.audit import init_db, log_action, get_logs
        init_db()

        class MockClient:
            host = "127.0.0.1"

        class MockRequest:
            headers = {"x-forwarded-for": "10.0.0.1, 10.0.0.2", "user-agent": "Test"}
            client = MockClient()

        log_action("login_success", request=MockRequest())
        logs, _ = get_logs()
        assert logs[0]["ip_address"] == "10.0.0.1"

    def test_x_real_ip(self, tmp_project):
        """Testet x-real-ip Header als Fallback."""
        from services.audit import init_db, log_action, get_logs
        init_db()

        class MockClient:
            host = "127.0.0.1"

        class MockRequest:
            headers = {"x-real-ip": "172.16.0.1", "user-agent": "Test"}
            client = MockClient()

        log_action("login_success", request=MockRequest())
        logs, _ = get_logs()
        assert logs[0]["ip_address"] == "172.16.0.1"

    def test_no_request(self, tmp_project):
        """Testet log_action ohne Request-Objekt."""
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("settings_change", details="Theme changed")
        logs, _ = get_logs()
        assert logs[0]["ip_address"] == "unknown"
        assert logs[0]["user_agent"] is None

    def test_category_assignment(self, tmp_project):
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("page_save", details="Test")
        logs, _ = get_logs()
        assert logs[0]["category"] == "pages"

    def test_unknown_action_gets_system_category(self, tmp_project):
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("some_unknown_action")
        logs, _ = get_logs()
        assert logs[0]["category"] == "system"

    def test_timestamp_format(self, tmp_project):
        """Prüft dass der Zeitstempel im ISO-Format gespeichert wird."""
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("login_success")
        logs, _ = get_logs()
        ts = logs[0]["timestamp"]
        # Sollte als ISO-String parsebar sein
        datetime.fromisoformat(ts)

    def test_user_id_and_username(self, tmp_project):
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("user_create", user_id="u42", username="testuser")
        logs, _ = get_logs()
        assert logs[0]["user_id"] == "u42"
        assert logs[0]["username"] == "testuser"

    def test_multiple_actions(self, tmp_project):
        """Mehrere Aktionen werden korrekt gespeichert und sortiert."""
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("login_success", username="alice")
        log_action("page_save", username="bob")
        log_action("logout", username="alice")
        logs, total = get_logs()
        assert total == 3
        # Neueste zuerst
        assert logs[0]["action"] == "logout"
        assert logs[2]["action"] == "login_success"

    def test_disabled_category_not_logged(self, tmp_project):
        """Aktionen einer deaktivierten Kategorie werden nicht gespeichert."""
        from core.config import save_app_config
        from services.audit import init_db, log_action, get_logs
        init_db()
        save_app_config({"audit_enabled": True, "audit_disabled_categories": ["pages"]})
        log_action("page_save", details="Should not be logged")
        log_action("login_success", details="Should be logged")
        logs, total = get_logs()
        assert total == 1
        assert logs[0]["action"] == "login_success"

    def test_db_error_does_not_crash(self, tmp_project):
        """Datenbankfehler beim Logging duerfen die App nicht crashen."""
        from services.audit import init_db, log_action
        import services.audit as audit_mod
        init_db()
        # Ungueltigen DB-Pfad setzen
        original_db = audit_mod.AUDIT_DB
        try:
            audit_mod.AUDIT_DB = "/nonexistent/path/db.sqlite"
            # Sollte keine Exception werfen
            log_action("login_success")
        finally:
            audit_mod.AUDIT_DB = original_db


class TestGetLogs:
    """Tests für get_logs() mit Filtern."""

    def _populate(self, tmp_project):
        from services.audit import init_db, log_action
        init_db()
        log_action("login_success", user_id="u1", username="admin")
        log_action("page_save", user_id="u1", username="admin")
        log_action("login_failed", details="wrong pw")

    def test_filter_by_action(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(action="login")
        assert total == 2  # login_success and login_failed

    def test_filter_by_exact_action(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(action="page_save")
        assert total == 1
        assert logs[0]["action"] == "page_save"

    def test_filter_by_category(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(category="pages")
        assert total == 1

    def test_filter_by_username(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(username="admin")
        assert total == 2

    def test_filter_by_search(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(search="wrong pw")
        assert total == 1

    def test_search_in_username(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(search="admin")
        assert total == 2

    def test_search_in_ip(self, tmp_project):
        """Suche funktioniert auch in IP-Adressen."""
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("login_success", username="admin")

        class MockClient:
            host = "192.168.42.7"
        class MockRequest:
            headers = {"user-agent": "Test"}
            client = MockClient()
        log_action("login_success", request=MockRequest())

        logs, total = get_logs(search="192.168.42")
        assert total == 1

    def test_pagination(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(limit=1, offset=0)
        assert total == 3
        assert len(logs) == 1

    def test_offset(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(limit=1, offset=2)
        assert len(logs) == 1
        assert total == 3

    def test_limit(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(limit=2)
        assert len(logs) == 2

    def test_date_range_filter(self, tmp_project):
        """Filterung nach Datum funktioniert."""
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("login_success", username="admin")
        # Alle Logs sind von heute, also nach gestern filtern
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        logs, total = get_logs(start_date=yesterday)
        assert total >= 1

    def test_end_date_filter(self, tmp_project):
        """Enddatum-Filter funktioniert."""
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("login_success", username="admin")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        logs, total = get_logs(end_date=tomorrow)
        assert total >= 1

    def test_empty_result(self, tmp_project):
        from services.audit import get_logs
        logs, total = get_logs(search="nichtvorhanden_xyz_99999")
        assert total == 0
        assert logs == []

    def test_combined_filters(self, tmp_project):
        """Mehrere Filter kombiniert."""
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("login_success", username="admin")
        log_action("login_failed", username="admin")
        log_action("page_save", username="bob")
        logs, total = get_logs(action="login", username="admin")
        assert total == 2


class TestGetAllLogs:
    """Tests für get_all_logs() — unbegrenzter Export."""

    def test_returns_all_without_limit(self, tmp_project):
        from services.audit import init_db, log_action, get_all_logs
        init_db()
        for i in range(5):
            log_action("login_success", username=f"user_{i}")
        logs = get_all_logs()
        assert len(logs) == 5

    def test_filter_by_action(self, tmp_project):
        from services.audit import init_db, log_action, get_all_logs
        init_db()
        log_action("login_success")
        log_action("page_save")
        log_action("login_failed")
        logs = get_all_logs(action="login")
        assert len(logs) == 2

    def test_empty_result(self, tmp_project):
        from services.audit import init_db, get_all_logs
        init_db()
        logs = get_all_logs(action="nonexistent_xyz")
        assert logs == []


class TestGetRecentAuditLogs:
    """Tests für get_recent_audit_logs()."""

    def test_returns_most_recent(self, tmp_project):
        from services.audit import init_db, log_action, get_recent_audit_logs
        init_db()
        for i in range(10):
            log_action("login_success", username=f"user_{i}")
        logs = get_recent_audit_logs(limit=3)
        assert len(logs) == 3

    def test_empty_database(self, tmp_project):
        from services.audit import init_db, get_recent_audit_logs
        init_db()
        logs = get_recent_audit_logs()
        assert logs == []

    def test_default_limit(self, tmp_project):
        from services.audit import init_db, log_action, get_recent_audit_logs
        init_db()
        for i in range(10):
            log_action("login_success")
        logs = get_recent_audit_logs()
        assert len(logs) == 5  # Default limit


class TestGetCategoryStats:
    """Tests für get_category_stats()."""

    def test_returns_stats(self, tmp_project):
        from services.audit import init_db, log_action, get_category_stats
        init_db()
        log_action("login_success")
        log_action("page_save")
        log_action("page_save")
        stats = get_category_stats()
        assert stats.get("auth", 0) >= 1
        assert stats.get("pages", 0) >= 2

    def test_empty_database(self, tmp_project):
        from services.audit import init_db, get_category_stats
        init_db()
        stats = get_category_stats()
        assert stats == {}

    def test_all_categories_represented(self, tmp_project):
        """Jede Aktion sollte in der korrekten Kategorie landen."""
        from services.audit import init_db, log_action, get_category_stats
        init_db()
        log_action("login_success")
        log_action("page_save")
        log_action("api_key_create")
        log_action("wiki_create")
        log_action("settings_change")
        log_action("mcp_tool_call")
        stats = get_category_stats()
        assert stats.get("auth", 0) >= 1
        assert stats.get("pages", 0) >= 1
        assert stats.get("api_keys", 0) >= 1
        assert stats.get("wikis", 0) >= 1
        assert stats.get("system", 0) >= 1
        assert stats.get("mcp", 0) >= 1


class TestGetTotalCount:
    """Tests für get_total_count()."""

    def test_returns_zero_for_empty(self, tmp_project):
        from services.audit import init_db, get_total_count
        init_db()
        assert get_total_count() == 0

    def test_returns_correct_count(self, tmp_project):
        from services.audit import init_db, log_action, get_total_count
        init_db()
        log_action("login_success")
        log_action("page_save")
        log_action("logout")
        assert get_total_count() == 3


class TestPruneLogs:
    """Tests für prune_logs()."""

    def test_prune_removes_old(self, tmp_project):
        from services.audit import init_db, log_action, prune_logs, get_logs
        init_db()
        log_action("login_success")
        deleted = prune_logs(2099)  # Prüfe alles vor 2099
        assert deleted >= 1
        _, total = get_logs()
        assert total == 0

    def test_prune_with_month(self, tmp_project):
        """Prune mit spezifischem Monat."""
        from services.audit import init_db, log_action, prune_logs
        init_db()
        log_action("login_success")
        deleted = prune_logs(2099, month=12)
        assert deleted >= 1

    def test_prune_returns_zero_when_nothing_to_delete(self, tmp_project):
        from services.audit import init_db, prune_logs
        init_db()
        deleted = prune_logs(2020)
        assert deleted == 0

    def test_db_error_returns_zero(self, tmp_project):
        """Datenbankfehler gibt 0 zurück."""
        from services.audit import prune_logs
        import services.audit as audit_mod
        original_db = audit_mod.AUDIT_DB
        try:
            audit_mod.AUDIT_DB = "/nonexistent/path/db.sqlite"
            deleted = prune_logs(2099)
            assert deleted == 0
        finally:
            audit_mod.AUDIT_DB = original_db


class TestExportLogsCsv:
    """Tests für export_logs_csv()."""

    def test_csv_output_format(self, tmp_project):
        from services.audit import init_db, log_action, export_logs_csv
        init_db()
        log_action("login_success", user_id="u1", username="admin", details="Test")

        from services.audit import get_all_logs
        logs = get_all_logs()
        csv_str = export_logs_csv(logs)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        # Header + 1 data row
        assert len(rows) == 2
        assert rows[0] == ["ID", "Timestamp", "User ID", "Username", "Category", "Action", "Details", "IP Address", "User Agent"]
        assert rows[1][4] == "auth"  # Category
        assert rows[1][5] == "login_success"  # Action

    def test_csv_empty_logs(self, tmp_project):
        from services.audit import export_logs_csv
        csv_str = export_logs_csv([])
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        # Only header
        assert len(rows) == 1

    def test_csv_with_all_fields(self, tmp_project):
        """Alle CSV-Felder werden korrekt gefüllt."""
        from services.audit import export_logs_csv
        test_log = {
            "id": 42,
            "timestamp": "2026-01-15T10:30:00",
            "user_id": "abc123",
            "username": "testuser",
            "category": "auth",
            "action": "login_success",
            "details": "Login via Browser",
            "ip_address": "192.168.1.100",
            "user_agent": "Mozilla/5.0",
        }
        csv_str = export_logs_csv([test_log])
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        assert rows[1][0] == "42"
        assert rows[1][2] == "abc123"
        assert rows[1][3] == "testuser"
        assert rows[1][6] == "Login via Browser"
        assert rows[1][7] == "192.168.1.100"

    def test_csv_handles_missing_fields(self, tmp_project):
        """CSV-Export verarbeitet fehlende Felder gracefully."""
        from services.audit import export_logs_csv
        test_log = {"id": 1, "timestamp": "2026-01-15T10:00:00", "action": "test"}
        csv_str = export_logs_csv([test_log])
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        # Fehlende Felder werden als leerer String dargestellt
        assert rows[1][2] == ""  # user_id
        assert rows[1][3] == ""  # username


class TestActionCategories:
    """Tests für ACTION_CATEGORIES Mapping."""

    def test_all_expected_actions_mapped(self):
        """Alle erwarteten Aktionen sollten einer Kategorie zugeordnet sein."""
        from services.audit import ACTION_CATEGORIES
        expected_actions = [
            "login", "login_success", "login_failed", "logout", "setup_admin",
            "user_create", "user_edit", "user_delete", "user_change_password",
            "api_key_create", "api_key_delete", "api_key_reveal",
            "system_secret_reveal", "system_secret_regenerate",
            "mcp_key_create", "mcp_key_delete", "mcp_key_reveal",
            "page_create", "page_save", "page_delete", "page_export", "page_upload",
            "wiki_create", "wiki_sync", "wiki_delete",
            "activity_log_clear", "api_ingest_upload",
            "search", "ingest", "ingest_save_later",
            "settings_change", "theme_change",
            "system_startup", "system_shutdown",
            "audit_prune", "audit_export",
            "mcp_tool_call", "mcp_write_concept", "mcp_delete_page",
            "mcp_create_wiki", "mcp_delete_wiki", "mcp_sync",
            "mcp_update", "mcp_clear_cache", "mcp_create_backup", "mcp_restore_backup",
        ]
        for action in expected_actions:
            assert action in ACTION_CATEGORIES, f"Action '{action}' nicht in ACTION_CATEGORIES"

    def test_all_categories_in_all_categories(self):
        """Alle Kategorien aus ACTION_CATEGORIES sollten in ALL_CATEGORIES sein."""
        from services.audit import ACTION_CATEGORIES, ALL_CATEGORIES
        used_categories = set(ACTION_CATEGORIES.values())
        for cat in used_categories:
            assert cat in ALL_CATEGORIES, f"Kategorie '{cat}' nicht in ALL_CATEGORIES"


class TestDbInitialized:
    """Tests für den _db_initialized Cache."""

    def test_initial_state(self, tmp_project):
        import services.audit as audit_mod
        # Nach monkeypatch-Reset sollte False sein
        audit_mod._db_initialized = False
        audit_mod.init_db()
        assert audit_mod._db_initialized is True

    def test_skips_reinit(self, tmp_project):
        """Zweiter Aufruf von init_db() sollte DB nicht neu initialisieren."""
        import services.audit as audit_mod
        audit_mod._db_initialized = True
        # Sollte keinen Fehler werfen und sofort zurueckkehren
        audit_mod.init_db()
        assert audit_mod._db_initialized is True
