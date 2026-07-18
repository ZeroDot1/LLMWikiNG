"""Tests für services.audit – Audit-Logging SQLite."""

from __future__ import annotations

import sqlite3

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


class TestInitDB:
    """Tests für init_db()."""

    def test_creates_database(self, tmp_project):
        from services.audit import init_db, AUDIT_DB
        init_db()
        assert AUDIT_DB.exists()

    def test_creates_correct_table(self, tmp_project):
        from services.audit import init_db, AUDIT_DB
        init_db()
        conn = sqlite3.connect(AUDIT_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_idempotent(self, tmp_project):
        from services.audit import init_db
        init_db()
        init_db()  # Should not raise


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

    def test_category_assignment(self, tmp_project):
        from services.audit import init_db, log_action, get_logs
        init_db()
        log_action("page_save", details="Test")
        logs, _ = get_logs()
        assert logs[0]["category"] == "pages"


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

    def test_pagination(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(limit=1, offset=0)
        assert total == 3
        assert len(logs) == 1

    def test_limit(self, tmp_project):
        from services.audit import get_logs
        self._populate(tmp_project)
        logs, total = get_logs(limit=2)
        assert len(logs) == 2


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
