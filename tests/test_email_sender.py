"""Tests für services.email_sender – SMTP-Konfiguration."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestLoadSmtpConfig:
    """Tests für load_smtp_config()."""

    def test_loads_from_config_file(self, tmp_project):
        from services.email_sender import load_smtp_config
        config = load_smtp_config()
        assert "smtp_host" in config
        assert "smtp_port" in config
        assert config["smtp_host"] == "smtp.gmail.com"

    def test_defaults_when_no_config(self, tmp_project):
        from services.email_sender import load_smtp_config
        from core.config import CONFIG_FILE
        CONFIG_FILE.unlink(missing_ok=True)
        config = load_smtp_config()
        assert config["smtp_host"] == "smtp.gmail.com"
        assert config["smtp_port"] == 587

    def test_returns_all_required_fields(self, tmp_project):
        from services.email_sender import load_smtp_config
        config = load_smtp_config()
        required = {"smtp_host", "smtp_port", "smtp_user", "smtp_pass",
                     "use_tls", "recipients", "registration_enabled"}
        assert required.issubset(config.keys())


class TestSaveSmtpConfig:
    """Tests für save_smtp_config()."""

    def test_saves_smtp_config(self, tmp_project):
        from services.email_sender import save_smtp_config, load_smtp_config
        ok = save_smtp_config({
            "smtp_host": "smtp.test.de",
            "smtp_port": 465,
        })
        assert ok is True
        config = load_smtp_config()
        assert config["smtp_host"] == "smtp.test.de"
        assert config["smtp_port"] == 465

    def test_preserves_other_settings(self, tmp_project):
        from services.email_sender import save_smtp_config, load_smtp_config
        save_smtp_config({"smtp_host": "test.de"})
        config = load_smtp_config()
        assert config["language"] == "de"  # Other settings preserved

    def test_returns_false_on_error(self, tmp_project, monkeypatch):
        from services.email_sender import save_smtp_config
        monkeypatch.setattr("services.email_sender.CONFIG_FILE", Path("/nonexistent/config.json"))
        result = save_smtp_config({"test": "value"})
        assert result is False
