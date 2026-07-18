"""LLMWikiNG – Test-Fixtures und Test-Hilfen.

Stellt gemeinsame Fixtures für alle Tests bereit, inkl.:
- Isoliertes temporäres Projektverzeichnis (kein Zugriff auf Echtdaten)
- Schnelle Test-Wikis mit Beispiel-Seiten
- API-Client für Integrationstests
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Generator

import pytest

# Backend-Pfad für Imports hinzufügen
BACKEND_DIR = str(Path(__file__).resolve().parent.parent / "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture()
def tmp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Erstellt ein vollständig isoliertes temporäres Projektverzeichnis.

    Erstellt die gleiche Struktur wie das echte Projekt:
    - config.json
    - data/
    - wikis/main/
    - raw/
    - output_docs/
    - lang/
    - templates/
    """
    # Verzeichnisse erstellen
    wikis_root = tmp_path / "wikis"
    main_wiki = wikis_root / "main"
    data_dir = tmp_path / "data"
    raw_dir = tmp_path / "raw"
    export_dir = tmp_path / "output_docs"
    lang_dir = tmp_path / "lang"
    templates_dir = tmp_path / "templates"

    for d in [wikis_root, main_wiki, data_dir, raw_dir, export_dir, lang_dir, templates_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Standard config.json
    config = {
        "language": "de",
        "theme": "dark",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_pass": "",
        "use_tls": True,
        "recipients": "",
        "registration_enabled": True,
        "audit_enabled": True,
        "audit_disabled_categories": [],
        "ollama_host": "http://localhost:11434",
        "ollama_model": "llama3.2:3b",
        "secret_key": "test_secret_for_testing_only_1234567890abcdef",
    }
    (tmp_path / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    # Standard-Sprachdateien
    de_translations = {
        "_meta": {"name": "Deutsch"},
        "sidebar": {"home": "Startseite", "search": "Suche"},
        "index": {"welcome_heading": "Willkommen"},
    }
    (lang_dir / "de.json").write_text(json.dumps(de_translations, indent=2, ensure_ascii=False), encoding="utf-8")
    en_translations = {
        "_meta": {"name": "English"},
        "sidebar": {"home": "Home", "search": "Search"},
        "index": {"welcome_heading": "Welcome"},
    }
    (lang_dir / "en.json").write_text(json.dumps(en_translations, indent=2), encoding="utf-8")

    # Leere users.json / api_keys.json / wikis.json
    (data_dir / "users.json").write_text("[]", encoding="utf-8")
    (data_dir / "api_keys.json").write_text("[]", encoding="utf-8")
    (data_dir / "wikis.json").write_text("[]", encoding="utf-8")

    # core.config Pfade umleiten
    import core.config as cfg
    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "DATA_DIR", data_dir)
    monkeypatch.setattr(cfg, "WIKIS_ROOT", wikis_root)
    monkeypatch.setattr(cfg, "WIKI_DIR", main_wiki)
    monkeypatch.setattr(cfg, "RAW_DIR", raw_dir)
    monkeypatch.setattr(cfg, "EXPORT_DIR", export_dir)
    monkeypatch.setattr(cfg, "LANG_DIR", lang_dir)
    monkeypatch.setattr(cfg, "SCRATCH_DIR", tmp_path / "scratch")

    # Übersetzungs-Cache zurücksetzen
    monkeypatch.setattr(cfg, "_translations_cache", {})

    # Audit-DB-Pfad umleiten
    import services.audit as audit_mod
    monkeypatch.setattr(audit_mod, "AUDIT_DB", data_dir / "audit_log.db")

    # Sync-Status-Datei
    import services.sync as sync_mod
    monkeypatch.setattr(sync_mod, "SYNC_STATUS_FILE", data_dir / "sync_status.json")

    # storage-Pfade umleiten
    import core.storage as storage_mod
    monkeypatch.setattr(storage_mod, "USERS_FILE", data_dir / "users.json")
    monkeypatch.setattr(storage_mod, "KEYS_FILE", data_dir / "api_keys.json")

    # ---------------------------------------------------------------
    # Service-Module patchen: Diese importieren Config-Werte bei
    # Modul-Load als lokale Bindungen (z.B. `from core.config import PROJECT_ROOT`).
    # Nur core.config zu patchen reicht NICHT – die lokalen Referenzen
    # in den Service-Modulen bleiben auf dem alten Wert.
    # ---------------------------------------------------------------

    # services.wiki: PROJECT_ROOT, WIKI_DIR, RAW_DIR
    import services.wiki as wiki_svc
    monkeypatch.setattr(wiki_svc, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(wiki_svc, "WIKI_DIR", main_wiki)
    monkeypatch.setattr(wiki_svc, "RAW_DIR", raw_dir)

    # services.search: PROJECT_ROOT, WIKI_DIR, RAW_DIR, EXPORT_DIR
    import services.search as search_svc
    monkeypatch.setattr(search_svc, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(search_svc, "WIKI_DIR", main_wiki)
    monkeypatch.setattr(search_svc, "RAW_DIR", raw_dir)
    monkeypatch.setattr(search_svc, "EXPORT_DIR", export_dir)

    # services.sync: PROJECT_ROOT, WIKI_DIR (SYNC_STATUS_FILE bereits oben gepatcht)
    import services.sync as sync_svc
    monkeypatch.setattr(sync_svc, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sync_svc, "WIKI_DIR", main_wiki)

    # services.backup: PROJECT_ROOT
    import services.backup as backup_svc
    monkeypatch.setattr(backup_svc, "PROJECT_ROOT", tmp_path)

    # services.graph: WIKI_DIR
    import services.graph as graph_svc
    monkeypatch.setattr(graph_svc, "WIKI_DIR", main_wiki)

    # services.lint: WIKI_DIR, RAW_DIR
    import services.lint as lint_svc
    monkeypatch.setattr(lint_svc, "WIKI_DIR", main_wiki)
    monkeypatch.setattr(lint_svc, "RAW_DIR", raw_dir)

    # services.analytics: WIKI_DIR
    import services.analytics as analytics_svc
    monkeypatch.setattr(analytics_svc, "WIKI_DIR", main_wiki)

    # services.markdown: WIKI_DIR
    import services.markdown as markdown_svc
    monkeypatch.setattr(markdown_svc, "WIKI_DIR", main_wiki)

    # ---------------------------------------------------------------
    # web.py und main.py: Module-level Bindungen auf echten
    # PROJECT_ROOT. templates = Jinja2Templates(directory=...) und
    # STATIC_DIR = PROJECT_ROOT / "static" wurden beim Import der
    # Module mit dem realen Pfad erstellt und müssen ebenfalls
    # umgeleitet werden, damit TemplateNotFound-Fehler vermieden
    # werden.
    # ---------------------------------------------------------------
    import web as web_mod
    from fastapi.templating import Jinja2Templates
    _real_templates_dir = Path(__file__).resolve().parent.parent / "templates"
    monkeypatch.setattr(web_mod, "templates", Jinja2Templates(directory=str(_real_templates_dir)))

    import main as main_mod
    _real_static_dir = Path(__file__).resolve().parent.parent / "static"
    monkeypatch.setattr(main_mod, "STATIC_DIR", _real_static_dir)

    return tmp_path


@pytest.fixture()
def wiki_with_pages(tmp_project: Path) -> Path:
    """Erstellt ein Wiki mit mehreren Beispiel-Seiten für Tests."""
    wiki_root = tmp_project / "wikis" / "main"

    # index.md
    (wiki_root / "index.md").write_text(
        """---
type: System
title: "Index"
---
# Wiki-Index

Willkommen im Wiki.

## Inhalt
* [Python](./python.md)
* [Rust](./rust.md)
* [Fehlende Seite](./nonexistent.md)
""",
        encoding="utf-8",
    )

    # python.md
    (wiki_root / "python.md").write_text(
        """---
type: Concept
title: "Python Programmiersprache"
tags: [programmierung, sprache]
---
# Python Programmiersprache

Python ist eine interpreted Sprache.

* [Rust](./rust.md) ist ebenfalls toll.
* [Fehlende Seite](./nonexistent.md)
""",
        encoding="utf-8",
    )

    # rust.md
    (wiki_root / "rust.md").write_text(
        """---
type: Concept
title: "Rust Programmiersprache"
tags: [programmierung, system]
---
# Rust Programmiersprache

Rust ist eine Systemprogrammiersprache.

* [Python](./python.md) ist einfacher.
""",
        encoding="utf-8",
    )

    # trail.md
    (wiki_root / "trail.md").write_text(
        """---
type: Trail
title: "Lernpfad Programmierung"
---
# Lernpfad Programmierung

## Path

[Python](./python.md)
[Rust](./rust.md)
""",
        encoding="utf-8",
    )

    # log.md
    (wiki_root / "log.md").write_text(
        """---
okf_version: "0.1"
---
# Wiki-Aktivitätslogbuch

## 2025-01-15
* **Creation**: Python - Erstellt
* **Update**: Rust - Aktualisiert - Details hier

## 2025-01-10
* **Creation**: Rust - Erstellt
""",
        encoding="utf-8",
    )

    # ingestlater.md (System-Seite)
    (wiki_root / "ingestlater.md").write_text(
        "# Ingest Later\n\n> Liste von URLs.\n\n## Gemerkte URLs\n\n",
        encoding="utf-8",
    )

    # simple.md – Seite ohne outgoing Links (für Dead-End-Tests)
    (wiki_root / "simple.md").write_text(
        """---
type: Concept
title: "Einfache Seite"
---
# Einfache Seite

Diese Seite hat keine outgoing Links.
""",
        encoding="utf-8",
    )

    return tmp_project


@pytest.fixture()
def raw_files(tmp_project: Path) -> Path:
    """Erstellt Test-Rohdateien im raw/ Verzeichnis."""
    raw_dir = tmp_project / "raw"
    (raw_dir / "test_doc.txt").write_text("Dies ist ein Testdokument mit Python Inhalten.", encoding="utf-8")
    (raw_dir / "another_file.md").write_text("# Another File\n\nInhalt mit Rust.", encoding="utf-8")
    return tmp_project


@pytest.fixture()
def sample_users(tmp_project: Path) -> Path:
    """Erstellt Beispiel-Benutzer für Tests."""
    import core.storage as storage
    storage.create_user("admin", "Admin123!@#", role="admin")
    storage.create_user("editor", "Editor123!@#", role="editor")
    return tmp_project


@pytest.fixture()
def sample_api_keys(tmp_project: Path, sample_users: Path) -> tuple[Path, dict]:
    """Erstellt Beispiel-API-Keys und gibt (tmp_project, {username: user_dict, raw_keys}) zurück."""
    import core.storage as storage
    users = storage.list_users()
    admin = next(u for u in users if u["role"] == "admin")
    _, raw_key = storage.create_key(admin["id"], "Test-Key", require_password=False)
    return tmp_project, {"admin": admin, "raw_key": raw_key}


@pytest.fixture()
def app(tmp_project: Path):
    """Erstellt die FastAPI-App mit Test-Konfiguration."""
    # Cache zurücksetzen
    from services.cache import get_cache
    get_cache().clear()

    from main import create_app
    return create_app()


@pytest.fixture()
def client(app):
    """Erstellt einen TestClient für HTTP-Integrationstests."""
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def auth_cookie(client, sample_users) -> str:
    """Loggt einen Admin ein und gibt das Session-Cookie zurück."""
    resp = client.post(
        "/LLMWikiNG/login",
        data={"username": "admin", "password": "Admin123!@#"},
        follow_redirects=False,
    )
    # Session-Cookie aus der Response extrahieren
    # httpx Headers.items() liefert (key, value) tuples
    cookies = {}
    for key, value in resp.headers.items():
        if key.lower() == "set-cookie" and "session=" in value:
            cookie_value = value.split("session=")[1].split(";")[0]
            cookies["session"] = cookie_value
    return cookies
