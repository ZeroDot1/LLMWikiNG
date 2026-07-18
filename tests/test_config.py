"""Tests für core.config – Konfiguration, Slugs, Übersetzungen, Wikis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestSlugifyWiki:
    """Tests für slugify_wiki()."""

    def test_simple_name(self):
        from core.config import slugify_wiki
        assert slugify_wiki("Mein Wiki") == "mein-wiki"

    def test_german_umlauts(self):
        from core.config import slugify_wiki
        assert slugify_wiki("Übergrößen") == "uebergroessen"

    def test_german_umlauts_ae(self):
        from core.config import slugify_wiki
        assert slugify_wiki("Änderung") == "aenderung"

    def test_german_umlauts_oe(self):
        from core.config import slugify_wiki
        assert slugify_wiki("Schönheit") == "schoenheit"

    def test_german_umlauts_ss(self):
        from core.config import slugify_wiki
        assert slugify_wiki("Straße") == "strasse"

    def test_special_characters(self):
        from core.config import slugify_wiki
        # @ und ! werden zu Bindestrichen, der nachfolgende wird entfernt
        assert slugify_wiki("Wiki@2025!") == "wiki-2025"

    def test_empty_string_returns_main(self):
        from core.config import slugify_wiki
        assert slugify_wiki("") == "main"

    def test_whitespace_only_returns_main(self):
        from core.config import slugify_wiki
        assert slugify_wiki("   ") == "main"

    def test_leading_trailing_hyphens_stripped(self):
        from core.config import slugify_wiki
        assert slugify_wiki("--test--") == "test"

    def test_uppercase_lowercased(self):
        from core.config import slugify_wiki
        assert slugify_wiki("WIKI") == "wiki"

    def test_mixed_content(self):
        from core.config import slugify_wiki
        assert slugify_wiki("  Mein Wiki 2025  ") == "mein-wiki-2025"

    def test_already_clean(self):
        from core.config import slugify_wiki
        assert slugify_wiki("mein-wiki") == "mein-wiki"


class TestWikiPath:
    """Tests für wiki_path()."""

    def test_creates_directory(self, tmp_project):
        from core.config import wiki_path
        p = wiki_path("testwiki")
        assert p.exists()
        assert p.is_dir()

    def test_default_is_main(self, tmp_project):
        from core.config import wiki_path, WIKIS_ROOT
        p = wiki_path()
        assert p == WIKIS_ROOT / "main"

    def test_slugified_name(self, tmp_project):
        from core.config import wiki_path, WIKIS_ROOT
        p = wiki_path("Mein Wiki")
        assert p == WIKIS_ROOT / "mein-wiki"


class TestAppConfig:
    """Tests für load_app_config / save_app_config."""

    def test_load_returns_defaults_when_no_file(self, tmp_project, monkeypatch):
        from core.config import load_app_config, CONFIG_FILE
        CONFIG_FILE.unlink(missing_ok=True)
        cfg = load_app_config()
        assert "language" in cfg
        assert "theme" in cfg
        assert "smtp_host" in cfg

    def test_load_reads_existing_config(self, tmp_project):
        from core.config import load_app_config
        cfg = load_app_config()
        assert cfg["language"] == "de"
        assert cfg["theme"] == "dark"

    def test_save_app_config(self, tmp_project):
        from core.config import save_app_config, load_app_config
        ok = save_app_config({"language": "en"})
        assert ok is True
        cfg = load_app_config()
        assert cfg["language"] == "en"

    def test_save_merges_with_existing(self, tmp_project):
        from core.config import save_app_config, load_app_config
        save_app_config({"language": "fr"})
        save_app_config({"theme": "light"})
        cfg = load_app_config()
        assert cfg["language"] == "fr"
        assert cfg["theme"] == "light"

    def test_save_returns_false_on_error(self, tmp_project, monkeypatch):
        from core.config import save_app_config
        monkeypatch.setattr("core.config.CONFIG_FILE", Path("/nonexistent/path/config.json"))
        result = save_app_config({"test": "value"})
        assert result is False

    def test_load_invalid_json_returns_defaults(self, tmp_project):
        from core.config import load_app_config, CONFIG_FILE
        CONFIG_FILE.write_text("{ungültiges json!!!", encoding="utf-8")
        cfg = load_app_config()
        assert "language" in cfg  # Defaults


class TestTranslations:
    """Tests für das Übersetzungssystem."""

    def test_get_available_languages(self, tmp_project):
        from core.config import get_available_languages
        langs = get_available_languages()
        assert "de" in langs
        assert "en" in langs

    def test_load_translations_de(self, tmp_project):
        from core.config import load_translations
        t = load_translations("de")
        assert "sidebar" in t
        assert t["sidebar"]["home"] == "Startseite"

    def test_load_translations_en(self, tmp_project):
        from core.config import load_translations
        t = load_translations("en")
        assert t["sidebar"]["home"] == "Home"

    def test_load_translations_fallback(self, tmp_project):
        from core.config import load_translations
        t = load_translations("xx")
        # Should fallback to DEFAULT_LANG
        assert isinstance(t, dict)

    def test_translator_dot_notation(self, tmp_project):
        from core.config import Translator
        t = Translator("de")
        assert t("sidebar.home") == "Startseite"
        assert t("sidebar.search") == "Suche"

    def test_translator_missing_key_returns_key(self, tmp_project):
        from core.config import Translator
        t = Translator("de")
        assert t("nonexistent.key") == "nonexistent.key"

    def test_translator_none_key(self, tmp_project):
        from core.config import Translator
        t = Translator("de")
        assert t(None) is None

    def test_translator_with_kwargs(self, tmp_project, monkeypatch):
        from core.config import Translator, LANG_DIR
        # Create a test translation with format placeholder
        test_trans = {"test": "Hello {name}!"}
        (LANG_DIR / "test.json").write_text(json.dumps(test_trans), encoding="utf-8")
        monkeypatch.setattr("core.config._translations_cache", {})

        t = Translator("test")
        result = t("test", name="Welt")
        assert result == "Hello Welt!"

    def test_resolve_lang_priority(self, tmp_project):
        from core.config import resolve_lang
        # Query-Param hat Priorität
        assert resolve_lang("en", None) == "en"

    def test_resolve_lang_cookie_fallback(self, tmp_project):
        from core.config import resolve_lang
        assert resolve_lang(None, "en") == "en"

    def test_resolve_lang_config_fallback(self, tmp_project):
        from core.config import resolve_lang
        assert resolve_lang(None, None) == "de"  # aus config.json


class TestSetDefaultLang:
    """Tests für Sprach-Setter/Getter."""

    def test_set_and_get(self):
        from core.config import set_default_lang, get_default_lang
        original = get_default_lang()
        set_default_lang("en")
        assert get_default_lang() == "en"
        set_default_lang(original)  # Cleanup


class TestGetDirectorySize:
    """Tests für get_directory_size()."""

    def test_empty_directory(self, tmp_path):
        from core.config import get_directory_size
        assert get_directory_size(tmp_path) == 0

    def test_with_files(self, tmp_path):
        from core.config import get_directory_size
        (tmp_path / "test.txt").write_text("Hello World")
        assert get_directory_size(tmp_path) == len("Hello World")

    def test_with_subdirectories(self, tmp_path):
        from core.config import get_directory_size
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.txt").write_text("A")
        (sub / "b.txt").write_text("BB")
        assert get_directory_size(tmp_path) == 3


class TestListWikis:
    """Tests für list_wikis()."""

    def test_empty_when_no_wikis(self, tmp_project):
        from core.config import list_wikis
        wikis = list_wikis()
        # Could be empty or have "main" depending on initialization
        assert isinstance(wikis, list)

    def test_lists_existing_wikis(self, tmp_project):
        from core.config import list_wikis, DATA_DIR
        # Create a wiki with an index.md
        wiki_root = tmp_project / "wikis" / "mywiki"
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "index.md").write_text("# Test", encoding="utf-8")

        # wikis.json löschen, damit list_wikis() auto-discovery nutzt
        wikis_json = DATA_DIR / "wikis.json"
        wikis_json.unlink(missing_ok=True)

        wikis = list_wikis()
        slugs = [w["slug"] for w in wikis]
        assert "mywiki" in slugs

    def test_wiki_metadata(self, tmp_project):
        from core.config import list_wikis, DATA_DIR
        wiki_root = tmp_project / "wikis" / "test"
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "page.md").write_text("# Page", encoding="utf-8")
        (wiki_root / "index.md").write_text("# Index", encoding="utf-8")

        # wikis.json löschen, damit list_wikis() auto-discovery nutzt
        wikis_json = DATA_DIR / "wikis.json"
        wikis_json.unlink(missing_ok=True)

        wikis = list_wikis()
        test_wiki = next((w for w in wikis if w["slug"] == "test"), None)
        assert test_wiki is not None
        assert test_wiki["page_count"] == 1  # page.md counts, index.md doesn't


class TestSaveWikiMeta:
    """Tests für save_wiki_meta()."""

    def test_save_new_wiki_meta(self, tmp_project):
        from core.config import save_wiki_meta, list_wikis
        save_wiki_meta("test-wiki", "Test Wiki", "Eine Beschreibung")
        wikis = list_wikis()
        test_wiki = next((w for w in wikis if w["slug"] == "test-wiki"), None)
        assert test_wiki is not None
        assert test_wiki["name"] == "Test Wiki"
        assert test_wiki["description"] == "Eine Beschreibung"

    def test_update_existing_wiki_meta(self, tmp_project):
        from core.config import save_wiki_meta, list_wikis
        save_wiki_meta("test", "Alt", "Alt")
        save_wiki_meta("test", "Neu", "Neu")
        wikis = list_wikis()
        test_wiki = next((w for w in wikis if w["slug"] == "test"), None)
        assert test_wiki["name"] == "Neu"
