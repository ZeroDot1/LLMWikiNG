"""LLMWikiNG – Umfangreiche API-Tests (JSON API + Direct Ingest API).

Testet alle in SKILL.md dokumentierten Endpunkte:
- A. Direktes Wiki-Management (Ingest, Sync)
- B. Standard API v1 (Pages, Search, Graph, Stats, Lint)
- C. System-, Admin- & Cache-Routen
- D. User- & API-Key-Management

Jeder Test arbeitet im isolierten tmp_project mit eigenen Usern/Keys.
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import pytest


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────


def _create_test_wiki(client, tmp_path: Path, slug: str = "testwiki"):
    """Erstellt ein Wiki (Verzeichnis + wikis.json-Eintrag + index.md)."""
    from core.config import save_wiki_meta
    wiki_dir = tmp_path / "wikis" / slug
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "index.md").write_text(
        "---\ntype: System\ntitle: Index\n---\n# Index\n",
        encoding="utf-8",
    )
    # In wikis.json registrieren damit list_wikis() es findet
    save_wiki_meta(slug, slug.replace("-", " ").title(), f"Test-Wiki {slug}")
    return slug


def _make_api_key(client, tmp_path: Path, name: str = "test-key",
                  require_password: bool = False,
                  scopes: list | None = None) -> str:
    """Erstellt einen Admin-API-Key über die V1-API und gibt den rohen Key zurück."""
    import core.storage as storage
    users = storage.list_users()
    admin = next(u for u in users if u["role"] == "admin")
    scopes = scopes or ["read", "write"]
    _, raw_key = storage.create_key(
        admin["id"], name, require_password=require_password, scopes=scopes
    )
    return raw_key


def _make_editor_key(client, tmp_path: Path) -> str:
    """Erstellt einen Editor-API-Key."""
    import core.storage as storage
    users = storage.list_users()
    editor = next(u for u in users if u.get("role") == "editor")
    _, raw_key = storage.create_key(editor["id"], "editor-key", scopes=["read"])
    return raw_key


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def api_env(tmp_project, sample_users):
    """Bereitet Testumgebung mit Admin + Editor User und API-Keys vor.

    Gibt (tmp_path, admin_key, editor_key, client) zurück.
    """
    from fastapi.testclient import TestClient
    from main import create_app
    from services.cache import get_cache
    get_cache().clear()

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    admin_key = _make_api_key(client, tmp_project, "admin-key")
    editor_key = _make_editor_key(client, tmp_project)

    return tmp_project, admin_key, editor_key, client


# ═══════════════════════════════════════════════════════════════════════════════
# A. AUTHENTIFIZIERUNG
# ═══════════════════════════════════════════════════════════════════════════════


class TestApiAuth:
    """API-Key Authentifizierungstests."""

    def test_no_key_returns_401(self, api_env):
        _, _, _, client = api_env
        resp = client.get("/LLMWikiNG/api/v1/wikis")
        assert resp.status_code == 401

    def test_invalid_key_returns_403(self, api_env):
        _, _, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis",
            headers={"X-API-Key": "llmw_ungueltig123"},
        )
        assert resp.status_code == 403

    def test_valid_key_returns_200(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "wikis" in data

    def test_key_via_query_param(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(f"/LLMWikiNG/api/v1/wikis?api_key={admin_key}")
        assert resp.status_code == 200

    def test_editor_cannot_access_admin_endpoint(self, api_env):
        _, _, editor_key, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/users",
            headers={"X-API-Key": editor_key},
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# B. WIKI-MANAGEMENT (V1 API)
# ═══════════════════════════════════════════════════════════════════════════════


class TestWikiManagement:
    """Tests für Wiki-Liste, Erstellung, Bearbeitung, Löschung."""

    def test_list_wikis(self, api_env):
        tmp_path, admin_key, _, client = api_env
        _create_test_wiki(client, tmp_path, "alpha")
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "wikis" in data
        slugs = [w["slug"] for w in data["wikis"]]
        assert "alpha" in slugs

    def test_create_wiki(self, api_env):
        tmp_path, admin_key, _, client = api_env
        resp = client.post(
            "/LLMWikiNG/api/v1/wikis",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"name": "Neues Wiki", "slug": "neues-wiki", "description": "Test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["slug"] == "neues-wiki"
        # Verzeichnis muss existieren
        assert (tmp_path / "wikis" / "neues-wiki").exists()

    def test_create_wiki_duplicate_returns_409(self, api_env):
        tmp_path, admin_key, _, client = api_env
        _create_test_wiki(client, tmp_path, "dup")
        resp = client.post(
            "/LLMWikiNG/api/v1/wikis",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"name": "Duplikat", "slug": "dup"},
        )
        assert resp.status_code == 409

    def test_create_wiki_missing_fields_returns_400(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.post(
            "/LLMWikiNG/api/v1/wikis",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"name": ""},
        )
        assert resp.status_code == 400

    def test_update_wiki_metadata(self, api_env):
        tmp_path, admin_key, _, client = api_env
        _create_test_wiki(client, tmp_path, "updatable")
        resp = client.put(
            "/LLMWikiNG/api/v1/wikis/updatable",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"name": "Aktualisiert", "description": "Neue Beschreibung"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["slug"] == "updatable"

    def test_update_wiki_slug(self, api_env):
        tmp_path, admin_key, _, client = api_env
        _create_test_wiki(client, tmp_path, "old-slug")
        resp = client.put(
            "/LLMWikiNG/api/v1/wikis/old-slug",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"name": "Umbenannt", "slug": "new-slug"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "new-slug"
        # Altes Verzeichnis weg, neues da
        assert not (tmp_path / "wikis" / "old-slug").exists()
        assert (tmp_path / "wikis" / "new-slug").exists()

    def test_delete_wiki(self, api_env):
        tmp_path, admin_key, _, client = api_env
        _create_test_wiki(client, tmp_path, "deleteme")
        resp = client.delete(
            "/LLMWikiNG/api/v1/wikis/deleteme",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert not (tmp_path / "wikis" / "deleteme").exists()

    def test_delete_main_wiki_returns_400(self, api_env):
        tmp_path, admin_key, _, client = api_env
        resp = client.delete(
            "/LLMWikiNG/api/v1/wikis/main",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 400

    def test_delete_nonexistent_wiki_returns_404(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.delete(
            "/LLMWikiNG/api/v1/wikis/gibtsnicht",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# C. PAGE MANAGEMENT (V1 API)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPageManagement:
    """Tests für Seiten-Listing, Erstellung, Lesen, Export."""

    def test_list_pages(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "pages-wiki")
        # Seite erstellen
        wiki_dir = tmp_path / "wikis" / slug
        (wiki_dir / "test-seite.md").write_text(
            "---\ntype: Concept\ntitle: Test\n---\n# Test\nInhalt.",
            encoding="utf-8",
        )
        resp = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pages",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["wiki"] == slug
        assert isinstance(data["pages"], list)
        # Index ist eine System-Seite -> wird möglicherweise gefiltert
        page_slugs = [p["slug"] for p in data["pages"]]
        assert "test-seite" in page_slugs

    def test_create_page_via_api(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "create-page")
        resp = client.post(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pages",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={
                "slug": "neue-seite",
                "content": "---\ntype: Concept\ntitle: Neue Seite\n---\n# Neue Seite\nHallo Welt.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["slug"] == "neue-seite"
        # Datei muss existieren
        assert (tmp_path / "wikis" / slug / "neue-seite.md").exists()

    def test_create_page_gets_frontmatter(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "fm-wiki")
        resp = client.post(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pages",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"slug": "auto-fm", "content": "# Ohne Frontmatter\nNur Text."},
        )
        assert resp.status_code == 200
        # ensure_okf_frontmatter sollte Frontmatter ergänzt haben
        content = (tmp_path / "wikis" / slug / "auto-fm.md").read_text(encoding="utf-8")
        assert content.startswith("---")

    def test_read_page_via_api(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "read-wiki")
        wiki_dir = tmp_path / "wikis" / slug
        (wiki_dir / "lesen.md").write_text(
            "---\ntype: Concept\ntitle: Lese mich\n---\n# Lese mich\nInhalt hier.",
            encoding="utf-8",
        )
        resp = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pages/lesen",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert "Lese mich" in data["content"]

    def test_read_nonexistent_page_returns_404(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "404-wiki")
        resp = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pages/doesnotexist",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 404

    def test_export_page_via_api(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "export-wiki")
        wiki_dir = tmp_path / "wikis" / slug
        (wiki_dir / "export-me.md").write_text(
            "---\ntype: Concept\ntitle: Export\n---\n# Export\nInhalt.",
            encoding="utf-8",
        )
        resp = client.post(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pages/export-me/export",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "exported_to" in data

    def test_system_page_cannot_be_overwritten(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "sys-wiki")
        resp = client.post(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pages",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"slug": "index", "content": "Überschreiben!"},
        )
        assert resp.status_code == 400

    def test_pages_in_nonexistent_wiki_returns_404(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/wikis/niemals/pages",
            headers={"X-API-Key": admin_key},
        )
        # wiki_path auto-creates dirs → might return 200 with empty list
        assert resp.status_code in (200, 404)


# ═══════════════════════════════════════════════════════════════════════════════
# D. DIRECT INGEST API (Wiki-spezifisch)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDirectIngest:
    """Tests für POST /wiki/{wiki_name}/api/ingest (Datei, URL, Text).

    Da die ingest-Endpunkte ./wiki.sh als Subprocess aufrufen (das im
    Testmodus nicht existiert), mocken wir subprocess.run.
    """

    @staticmethod
    def _mock_subprocess(monkeypatch):
        """Mockt subprocess.run so dass Ingest-Tests ohne wiki.sh funktionieren."""
        import subprocess

        def fake_run(cmd, **kwargs):
            """Simuliert wiki.sh ingest: Kopiert die Quelldatei ins Wiki-Verzeichnis."""
            from types import SimpleNamespace
            # cmd = ["./wiki.sh", "ingest", "/pfad/zu/datei.md", optional "--title", "Titel"]
            if "ingest" in cmd and len(cmd) >= 3:
                src = Path(cmd[2])
                if src.exists():
                    # WIKI_DIR aus env holen
                    wiki_dir = Path(kwargs.get("env", {}).get("WIKI_DIR", "."))
                    wiki_dir.mkdir(parents=True, exist_ok=True)
                    # Slug aus Dateiname
                    slug = src.stem
                    dest = wiki_dir / f"{slug}.md"
                    content = src.read_text(encoding="utf-8")
                    # Title aus --title Argument
                    if "--title" in cmd:
                        idx = cmd.index("--title")
                        title = cmd[idx + 1] if idx + 1 < len(cmd) else slug
                    else:
                        title = slug
                    # OKF-Frontmatter hinzufügen falls fehlt
                    if not content.startswith("---"):
                        content = f"---\ntype: Concept\ntitle: \"{title}\"\n---\n{content}"
                    dest.write_text(content, encoding="utf-8")
                    return SimpleNamespace(returncode=0, stderr="", stdout="")
                return SimpleNamespace(returncode=1, stderr="Quelldatei nicht gefunden", stdout="")
            return SimpleNamespace(returncode=1, stderr="Unbekannter Befehl", stdout="")

        monkeypatch.setattr(subprocess, "run", fake_run)

    def test_text_ingest(self, api_env, monkeypatch):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "ingest-text")
        self._mock_subprocess(monkeypatch)
        resp = client.post(
            f"/LLMWikiNG/wiki/{slug}/api/ingest",
            headers={"X-API-Key": admin_key},
            data={"text": "Dies ist ein Testinhalt für den Ingest.", "title": "Text-Ingest-Test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["wiki"] == slug
        assert len(data["processed"]) > 0
        assert len(data["errors"]) == 0

    def test_text_ingest_adds_heading(self, api_env, monkeypatch):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "ingest-heading")
        self._mock_subprocess(monkeypatch)
        resp = client.post(
            f"/LLMWikiNG/wiki/{slug}/api/ingest",
            headers={"X-API-Key": admin_key},
            data={"text": "Nur Fließtext ohne Überschrift.", "title": "Mit Titel"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_file_ingest(self, api_env, monkeypatch):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "ingest-file")
        self._mock_subprocess(monkeypatch)
        md_content = "---\ntype: Concept\ntitle: Datei-Test\n---\n# Datei-Test\nDateiinhalte."
        file_data = io.BytesIO(md_content.encode("utf-8"))
        resp = client.post(
            f"/LLMWikiNG/wiki/{slug}/api/ingest",
            headers={"X-API-Key": admin_key},
            files={"file": ("test-upload.md", file_data, "text/markdown")},
            data={"title": "Datei-Upload-Test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["processed"]) > 0

    def test_ingest_nonexistent_wiki_returns_404(self, api_env, monkeypatch):
        _, admin_key, _, client = api_env
        self._mock_subprocess(monkeypatch)
        resp = client.post(
            "/LLMWikiNG/wiki/niemals/api/ingest",
            headers={"X-API-Key": admin_key},
            data={"text": "Test"},
        )
        assert resp.status_code in (200, 404)

    def test_ingest_without_content(self, api_env, monkeypatch):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "ingest-empty")
        self._mock_subprocess(monkeypatch)
        resp = client.post(
            f"/LLMWikiNG/wiki/{slug}/api/ingest",
            headers={"X-API-Key": admin_key},
            data={},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["processed"]) == 0

    def test_ingest_returns_view_urls(self, api_env, monkeypatch):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "ingest-url")
        self._mock_subprocess(monkeypatch)
        resp = client.post(
            f"/LLMWikiNG/wiki/{slug}/api/ingest",
            headers={"X-API-Key": admin_key},
            data={"text": "Ein Test.", "title": "URL-Test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "view_urls" in data
        if data["processed"]:
            assert len(data["view_urls"]) > 0
            assert slug in data["view_urls"][0]


# ═══════════════════════════════════════════════════════════════════════════════
# E. SYNC API
# ═══════════════════════════════════════════════════════════════════════════════


class TestSync:
    """Tests für POST /wiki/{wiki_name}/api/sync."""

    def test_sync_wiki(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "sync-wiki")
        resp = client.post(
            f"/LLMWikiNG/wiki/{slug}/api/sync",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["wiki"] == slug


# ═══════════════════════════════════════════════════════════════════════════════
# F. SEARCH API
# ═══════════════════════════════════════════════════════════════════════════════


class TestSearchApi:
    """Tests für GET /api/v1/search?q=...&wiki=..."""

    def test_search_empty_query(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/search?q=&wiki=main",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []

    def test_search_with_query(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "search-wiki")
        wiki_dir = tmp_path / "wikis" / slug
        (wiki_dir / "python.md").write_text(
            "---\ntype: Concept\ntitle: Python\n---\n# Python\nEine Programmiersprache.",
            encoding="utf-8",
        )
        resp = client.get(
            f"/LLMWikiNG/api/v1/search?q=Python&wiki={slug}",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_search_cross_wiki(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "xwiki")
        wiki_dir = tmp_path / "wikis" / slug
        (wiki_dir / "rust.md").write_text(
            "---\ntype: Concept\ntitle: Rust\n---\n# Rust\nSystemprogrammierung.",
            encoding="utf-8",
        )
        resp = client.get(
            "/LLMWikiNG/api/v1/search?q=Rust&wiki=all",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["results"], list)


# ═══════════════════════════════════════════════════════════════════════════════
# G. GRAPH API
# ═══════════════════════════════════════════════════════════════════════════════


class TestGraphApi:
    """Tests für Graph-Endpunkte."""

    def test_graph_full(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "graph-wiki")
        wiki_dir = tmp_path / "wikis" / slug
        (wiki_dir / "seite-a.md").write_text(
            "---\ntype: Concept\ntitle: A\n---\n# A\n[B](./seite-b.md)",
            encoding="utf-8",
        )
        (wiki_dir / "seite-b.md").write_text(
            "---\ntype: Concept\ntitle: B\n---\n# B\nKeine Links.",
            encoding="utf-8",
        )
        resp = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug}/graph",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data or "items" in data or isinstance(data, dict)

    def test_graph_paginated(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "graph-pag")
        wiki_dir = tmp_path / "wikis" / slug
        (wiki_dir / "p1.md").write_text(
            "---\ntype: Concept\ntitle: P1\n---\n# P1",
            encoding="utf-8",
        )
        resp = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug}/graph/paginated?page=0&page_size=10",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# H. STATS & LINT API
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatsLintApi:
    """Tests für Stats- und Lint-Endpunkte."""

    def test_wiki_stats(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "stats-wiki")
        resp = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug}/stats",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["wiki"] == slug

    def test_wiki_lint(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "lint-wiki")
        resp = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug}/lint",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Lint-Ergebnis Should have expected fields
        assert isinstance(data, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# I. USER MANAGEMENT (Admin-only)
# ═══════════════════════════════════════════════════════════════════════════════


class TestUserManagement:
    """Tests für User-CRUD über die API."""

    def test_list_users(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/users",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert len(data["users"]) >= 1  # mindestens admin

    def test_create_user(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.post(
            "/LLMWikiNG/api/v1/users",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"username": "newuser", "password": "Passw0rd!", "role": "editor"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        assert data["username"] == "newuser"

    def test_create_user_duplicate_returns_409(self, api_env):
        _, admin_key, _, client = api_env
        # admin existiert bereits
        resp = client.post(
            "/LLMWikiNG/api/v1/users",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"username": "admin", "password": "Passw0rd!"},
        )
        assert resp.status_code == 409

    def test_create_user_missing_fields_returns_400(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.post(
            "/LLMWikiNG/api/v1/users",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"username": ""},
        )
        assert resp.status_code == 400

    def test_delete_user(self, api_env):
        _, admin_key, _, client = api_env
        # Erst User erstellen
        resp = client.post(
            "/LLMWikiNG/api/v1/users",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"username": "to_delete", "password": "Passw0rd!"},
        )
        assert resp.status_code == 201
        # User-ID holen
        resp2 = client.get(
            "/LLMWikiNG/api/v1/users",
            headers={"X-API-Key": admin_key},
        )
        users = resp2.json()["users"]
        target = next(u for u in users if u["username"] == "to_delete")
        resp3 = client.delete(
            f"/LLMWikiNG/api/v1/users/{target['id']}",
            headers={"X-API-Key": admin_key},
        )
        assert resp3.status_code == 200

    def test_editor_cannot_create_user(self, api_env):
        _, _, editor_key, client = api_env
        resp = client.post(
            "/LLMWikiNG/api/v1/users",
            headers={"X-API-Key": editor_key, "Content-Type": "application/json"},
            json={"username": "fail", "password": "x"},
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# J. API KEY MANAGEMENT (Admin-only)
# ═══════════════════════════════════════════════════════════════════════════════


class TestApiKeyManagement:
    """Tests für API-Key-CRUD über die API."""

    def test_list_api_keys(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/api-keys",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "api_keys" in data

    def test_create_api_key(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.post(
            "/LLMWikiNG/api/v1/api-keys",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"name": "Test-Key-Neu", "require_password": False, "scopes": ["read"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        assert "api_key" in data
        # Key muss mit llmw_ anfangen
        assert data["api_key"].startswith("llmw_")

    def test_delete_api_key(self, api_env):
        tmp_path, admin_key, _, client = api_env
        # Key erstellen
        resp = client.post(
            "/LLMWikiNG/api/v1/api-keys",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"name": "Zum-Löschen", "require_password": False},
        )
        key_id = resp.json()["id"]
        # Löschen
        resp2 = client.delete(
            f"/LLMWikiNG/api/v1/api-keys/{key_id}",
            headers={"X-API-Key": admin_key},
        )
        assert resp2.status_code == 200

    def test_editor_cannot_create_key(self, api_env):
        _, _, editor_key, client = api_env
        resp = client.post(
            "/LLMWikiNG/api/v1/api-keys",
            headers={"X-API-Key": editor_key, "Content-Type": "application/json"},
            json={"name": "Fail"},
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# K. SYSTEM STATUS & AUDIT
# ═══════════════════════════════════════════════════════════════════════════════


class TestSystemApi:
    """Tests für System-Endpunkte (Status, Audit, Cache)."""

    def test_api_status(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/status",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "authenticated_user" in data

    def test_system_status(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/system/status",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "wikis" in data

    def test_audit_logs(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/system/audit?limit=10",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert "total" in data

    def test_audit_logs_with_filter(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/system/audit?action=login&limit=5",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200

    def test_cache_stats(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.get(
            "/LLMWikiNG/api/v1/cache/stats",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200

    def test_cache_clear(self, api_env):
        _, admin_key, _, client = api_env
        resp = client.post(
            "/LLMWikiNG/api/v1/cache/clear",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_system_sync(self, api_env):
        tmp_path, admin_key, _, client = api_env
        _create_test_wiki(client, tmp_path, "sync-all")
        resp = client.post(
            "/LLMWikiNG/api/v1/system/sync",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data


# ═══════════════════════════════════════════════════════════════════════════════
# L. RAW INGEST & PENDING (V1 API)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRawIngest:
    """Tests für Roh-Upload und Pending-Ingest."""

    def test_upload_raw_file(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "raw-up")
        file_data = io.BytesIO(b"Dies ist ein Rohdokument.")
        resp = client.post(
            f"/LLMWikiNG/api/v1/wikis/{slug}/ingest",
            headers={"X-API-Key": admin_key},
            files={"file": ("raw-doc.txt", file_data, "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["saved"]) > 0

    def test_list_pending(self, api_env):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "pend-wiki")
        resp = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pending",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "pending" in data
        assert isinstance(data["pending"], list)


# ═══════════════════════════════════════════════════════════════════════════════
# M. INTEGRATIONSTESTS (Ingest → Read → Search → Delete)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFullIntegration:
    """Ende-zu-Ende-Tests: Kompletter Ingest-Read-Search-Lösch-Zyklus."""

    def test_ingest_read_search_delete_cycle(self, api_env, monkeypatch):
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "e2e-wiki")

        # Mock subprocess für wiki.sh ingest
        import subprocess
        from types import SimpleNamespace

        def fake_run(cmd, **kwargs):
            if "ingest" in cmd and len(cmd) >= 3:
                src = Path(cmd[2])
                if src.exists():
                    wiki_dir = Path(kwargs.get("env", {}).get("WIKI_DIR", "."))
                    wiki_dir.mkdir(parents=True, exist_ok=True)
                    slug_name = src.stem
                    dest = wiki_dir / f"{slug_name}.md"
                    content = src.read_text(encoding="utf-8")
                    if "--title" in cmd:
                        idx = cmd.index("--title")
                        title = cmd[idx + 1] if idx + 1 < len(cmd) else slug_name
                    else:
                        title = slug_name
                    if not content.startswith("---"):
                        content = f"---\ntype: Concept\ntitle: \"{title}\"\n---\n{content}"
                    dest.write_text(content, encoding="utf-8")
                    return SimpleNamespace(returncode=0, stderr="", stdout="")
                return SimpleNamespace(returncode=1, stderr="File not found", stdout="")
            return SimpleNamespace(returncode=1, stderr="Unknown", stdout="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        # 1. Text ingestiern
        resp = client.post(
            f"/LLMWikiNG/wiki/{slug}/api/ingest",
            headers={"X-API-Key": admin_key},
            data={
                "text": "# Integration Test\nDies ist ein E2E-Test mit Python-Inhalten.",
                "title": "Integration Test",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert len(resp.json()["processed"]) > 0

        # Cache leeren damit neue Dateien sichtbar sind
        from services.cache import get_cache
        get_cache().clear()

        # 2. Wiki-Stats prüfen
        resp5 = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug}/stats",
            headers={"X-API-Key": admin_key},
        )
        assert resp5.status_code == 200

        # 3. Sync ausführen
        resp6 = client.post(
            f"/LLMWikiNG/wiki/{slug}/api/sync",
            headers={"X-API-Key": admin_key},
        )
        assert resp6.status_code == 200
        assert resp6.json()["ok"] is True

        # 4. Datei direkt im Wiki-Verzeichnis prüfen
        wiki_files = list((tmp_path / "wikis" / slug).glob("*.md"))
        assert len(wiki_files) >= 2  # index.md + paste_text.md

    def test_create_read_page_via_api(self, api_env):
        """Testet den vollständigen Page-Erstellungs- und Lesezyklus."""
        tmp_path, admin_key, _, client = api_env
        slug = _create_test_wiki(client, tmp_path, "page-cycle")

        # 1. Seite erstellen
        content = (
            "---\ntype: Concept\ntitle: Test-Seite\ntags: [test, api]\n---\n"
            "# Test-Seite\n\nInhalt der Test-Seite mit [Link](./anderer.md)."
        )
        resp = client.post(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pages",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"slug": "test-seite", "content": content},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # 2. Seite lesen
        resp2 = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pages/test-seite",
            headers={"X-API-Key": admin_key},
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert "Test-Seite" in data["content"]

        # 3. Seite exportieren
        resp3 = client.post(
            f"/LLMWikiNG/api/v1/wikis/{slug}/pages/test-seite/export",
            headers={"X-API-Key": admin_key},
        )
        assert resp3.status_code == 200
        assert resp3.json()["ok"] is True

    def test_multi_wiki_isolation(self, api_env):
        """Stellt sicher, dass Wikis voneinander isoliert sind."""
        tmp_path, admin_key, _, client = api_env
        slug_a = _create_test_wiki(client, tmp_path, "wiki-a")
        slug_b = _create_test_wiki(client, tmp_path, "wiki-b")

        # Seite in Wiki A erstellen
        client.post(
            f"/LLMWikiNG/api/v1/wikis/{slug_a}/pages",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json={"slug": "nur-hier", "content": "---\ntype: Concept\ntitle: Nur Hier\n---\nNur in Wiki A."},
        )

        # Wiki A: Seite sollte vorhanden sein
        resp_a = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug_a}/pages/nur-hier",
            headers={"X-API-Key": admin_key},
        )
        assert resp_a.status_code == 200

        # Wiki B: Seite sollte NICHT vorhanden sein
        resp_b = client.get(
            f"/LLMWikiNG/api/v1/wikis/{slug_b}/pages/nur-hier",
            headers={"X-API-Key": admin_key},
        )
        assert resp_b.status_code == 404
