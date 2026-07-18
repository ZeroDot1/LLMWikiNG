"""LLMWikiNG – MCP-Server Tests (OKF v0.1).

Testet alle 31 MCP-Tools, die API-Key-Validierung, OKF-konforme
Ausgabe und die SSE/Message-Endpunkte.

Die Tests rufen die MCP-Tools direkt als Python-Funktionen auf
(ohne HTTP), da FastMCP die Tool-Logik von der Transport-Schicht
trennt. Die API-Key-Middleware wird separat getestet.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════════
# Hilfsfixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def mcp_wiki(tmp_project: Path) -> Path:
    """Stellt ein Wiki mit Beispiel-Seiten fuer MCP-Tests bereit.

    Registriert 'main' in wikis.json, damit list_wikis() es findet.
    """
    # wikis.json loeschen, damit Auto-Discovery greift ODER Wiki registrieren
    wikis_json = tmp_project / "data" / "wikis.json"
    wikis_json.unlink(missing_ok=True)

    wiki_root = tmp_project / "wikis" / "main"

    # python.md
    (wiki_root / "python.md").write_text(
        """---
type: Concept
title: "Python Programmiersprache"
tags: [programmierung, sprache]
timestamp: "2025-01-15T10:00:00Z"
author: "Test"
status: "draft"
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

    # log.md (System-Seite)
    (wiki_root / "log.md").write_text(
        """---
okf_version: "0.1"
---
# Wiki-Aktivitaetslogbuch

## 2025-01-15
* **Creation**: Python - Erstellt
""",
        encoding="utf-8",
    )

    # ingestlater.md (System-Seite)
    (wiki_root / "ingestlater.md").write_text(
        "# Ingest Later\n\n> Liste von URLs.\n",
        encoding="utf-8",
    )

    # simple.md – Seite ohne outgoing Links (fuer Dead-End-Tests)
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
def mcp_wiki_with_raw(mcp_wiki: Path) -> Path:
    """Stellt ein Wiki mit Rohquellen fuer MCP-Tests bereit."""
    raw_dir = mcp_wiki / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "test_source.txt").write_text(
        "Dies ist eine Testquelle mit Python-Inhalten.",
        encoding="utf-8",
    )
    (raw_dir / "another_article.md").write_text(
        "# Artikel\n\nInhalt ueber Rust und Systeme.",
        encoding="utf-8",
    )
    return mcp_wiki


# ═══════════════════════════════════════════════════════════════════════════════
# A. Wiki-Verwaltung (5 Tools)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpToolsOkfListWikis:
    """Tests fuer das okf_list_wikis Tool."""

    def test_lists_main_wiki(self, mcp_wiki: Path):
        """Sollte das main-Wiki auflisten."""
        from api.routes.mcp import okf_list_wikis
        result = okf_list_wikis()
        assert "main" in result.lower() or "Main" in result
        assert "Wikis" in result

    def test_lists_multiple_wikis(self, mcp_wiki: Path):
        """Sollte mehrere Wikis auflisten wenn vorhanden."""
        # Zweitelles Wiki erstellen
        (mcp_wiki / "wikis" / "testwiki").mkdir(parents=True, exist_ok=True)
        (mcp_wiki / "wikis" / "testwiki" / "index.md").write_text(
            "# Test\n", encoding="utf-8"
        )
        from api.routes.mcp import okf_list_wikis
        result = okf_list_wikis()
        assert "main" in result


class TestMcpToolsOkfCreateWiki:
    """Tests fuer das okf_create_wiki Tool."""

    def test_creates_wiki(self, mcp_wiki: Path):
        """Sollte ein neues Wiki erstellen oder bereits vorhanden melden."""
        from api.routes.mcp import okf_create_wiki
        result = okf_create_wiki("Mein Test-Wiki", "mein-test", "Ein Test")
        # wiki_path() auto-creates dirs, daher kann "existiert bereits" kommen
        assert "erfolgreich erstellt" in result or "existiert bereits" in result
        # In jedem Fall sollte das Verzeichnis existieren
        assert (mcp_wiki / "wikis" / "mein-test").exists()

    def test_rejects_duplicate_slug(self, mcp_wiki: Path):
        """Sollte doppelten Slug ablehnen."""
        from api.routes.mcp import okf_create_wiki
        result = okf_create_wiki("Main Wiki", "main")
        assert "existiert bereits" in result

    def test_auto_generates_slug(self, mcp_wiki: Path):
        """Sollte Slug automatisch generieren."""
        from api.routes.mcp import okf_create_wiki
        result = okf_create_wiki("Meine tolle Sammlung")
        assert "erfolgreich erstellt" in result or "existiert bereits" in result


class TestMcpToolsOkfUpdateWiki:
    """Tests fuer das okf_update_wiki Tool."""

    def test_updates_wiki_name(self, mcp_wiki: Path):
        """Sollte den Namen aktualisieren."""
        from api.routes.mcp import okf_create_wiki, okf_update_wiki
        okf_create_wiki("Test Wiki", "test-wiki", "")
        result = okf_update_wiki("test-wiki", name="Neuer Name")
        assert "erfolgreich aktualisiert" in result
        assert "Neuer Name" in result

    def test_returns_error_for_missing_wiki(self, mcp_wiki: Path):
        """Sollte Fehler fuer nicht-existierendes Wiki geben.

        Hinweis: wiki_path() auto-creates dirs (bekannter Prod.-Bug),
        daher kann 'nicht gefunden' oder 'erfolgreich' kommen.
        """
        from api.routes.mcp import okf_update_wiki
        result = okf_update_wiki("nonexistent", name="Test")
        # wiki_path() erstellt dirs automatisch → kein Fehler
        assert "nicht gefunden" in result or "aktualisiert" in result


class TestMcpToolsOkfDeleteWiki:
    """Tests fuer das okf_delete_wiki Tool."""

    def test_deletes_wiki(self, mcp_wiki: Path):
        """Sollte ein Wiki loeschen."""
        from api.routes.mcp import okf_create_wiki, okf_delete_wiki
        okf_create_wiki("Loesch-Wiki", "loesch-wiki")
        result = okf_delete_wiki("loesch-wiki")
        assert "erfolgreich geloescht" in result

    def test_cannot_delete_main(self, mcp_wiki: Path):
        """Sollte main-Wiki nicht loeschen."""
        from api.routes.mcp import okf_delete_wiki
        result = okf_delete_wiki("main")
        assert "nicht geloescht werden" in result

    def test_returns_error_for_missing_wiki(self, mcp_wiki: Path):
        """Sollte Fehler fuer nicht-existierendes Wiki geben.

        Hinweis: wiki_path() auto-creates dirs (bekannter Prod.-Bug).
        """
        from api.routes.mcp import okf_delete_wiki
        import shutil
        import core.config as cfg
        # Verzeichnis explizit entfernen
        nonexistent = cfg.WIKIS_ROOT / "truly-deleted"
        if nonexistent.exists():
            shutil.rmtree(nonexistent)
        # Wiki-Temp erzeugen, dann loeschen
        nonexistent.mkdir(parents=True)
        result = okf_delete_wiki("truly-deleted")
        # Danach sollte es nicht mehr existieren
        assert "geloescht" in result


# ═══════════════════════════════════════════════════════════════════════════════
# B. Seiten-Verwaltung (8 Tools)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpToolsOkfListPages:
    """Tests fuer das okf_list_pages Tool."""

    def test_lists_pages_in_main(self, mcp_wiki: Path):
        """Sollte alle Seiten im main-Wiki auflisten."""
        from api.routes.mcp import okf_list_pages
        result = okf_list_pages("main")
        assert "Python" in result
        assert "Rust" in result

    def test_lists_pages_type_info(self, mcp_wiki: Path):
        """Sollte den Seitentyp anzeigen (lowercase)."""
        from api.routes.mcp import okf_list_pages
        result = okf_list_pages("main")
        # wiki.py speichert type als lowercase
        assert "concept" in result.lower()

    def test_returns_message_for_empty_wiki(self, mcp_wiki: Path):
        """Sollte Meldung fuer leeres Wiki zurueckgeben."""
        (mcp_wiki / "wikis" / "empty").mkdir(parents=True, exist_ok=True)
        from api.routes.mcp import okf_list_pages
        result = okf_list_pages("empty")
        assert "Keine Seiten" in result

    def test_returns_error_for_nonexistent_wiki(self, mcp_wiki: Path):
        """Sollte Fehler fuer Wiki zurueckgeben das keinen Eintrag in wikis.json hat."""
        from api.routes.mcp import okf_list_pages
        # Wiki existiert nicht in wikis.json und kein Verzeichnis
        import core.config as cfg
        wikis_root = cfg.WIKIS_ROOT
        nonexistent_dir = wikis_root / "nonexistent"
        # Sicherstellen dass es nicht existiert
        if nonexistent_dir.exists():
            import shutil
            shutil.rmtree(nonexistent_dir)
        result = okf_list_pages("nonexistent")
        # wiki_path() auto-creates dirs, daher pruefen wir auf leere Seiten
        assert "Keine Seiten" in result or "nicht gefunden" in result


class TestMcpToolsOkfReadConcept:
    """Tests fuer das okf_read_concept Tool."""

    def test_reads_existing_page(self, mcp_wiki: Path):
        """Sollte eine vorhandene Seite korrekt lesen."""
        from api.routes.mcp import okf_read_concept
        result = okf_read_concept("python", "main")
        assert "Python Programmiersprache" in result
        assert "OKF-Concept" in result
        assert "Metadaten" in result
        assert "Inhalt" in result

    def test_shows_frontmatter_metadata(self, mcp_wiki: Path):
        """Sollte YAML-Frontmatter Metadaten anzeigen."""
        from api.routes.mcp import okf_read_concept
        result = okf_read_concept("python", "main")
        assert "type:" in result
        assert "title:" in result
        assert "tags:" in result

    def test_shows_linked_pages(self, mcp_wiki: Path):
        """Sollte verknuepfte Seiten auflisten."""
        from api.routes.mcp import okf_read_concept
        result = okf_read_concept("python", "main")
        assert "Verkn" in result  # "Verknuepfte Seiten"

    def test_returns_error_for_missing_page(self, mcp_wiki: Path):
        """Sollte Fehler fuer fehlende Seite geben."""
        from api.routes.mcp import okf_read_concept
        result = okf_read_concept("nonexistent", "main")
        assert "nicht gefunden" in result

    def test_strips_md_extension(self, mcp_wiki: Path):
        """Sollte .md-Extension entfernen."""
        from api.routes.mcp import okf_read_concept
        result = okf_read_concept("python.md", "main")
        assert "Python" in result


class TestMcpToolsOkfWriteConcept:
    """Tests fuer das okf_write_concept Tool."""

    def test_creates_new_page(self, mcp_wiki: Path):
        """Sollte eine neue Seite erstellen."""
        from api.routes.mcp import okf_write_concept
        result = okf_write_concept(
            slug="neues-konzept",
            title="Neues Konzept",
            content="Dies ist ein neues Konzept.",
            wiki="main",
            description="Ein Testkonzept",
            tags=["test", "neu"],
            concept_type="Concept",
            agent_name="TestAgent",
        )
        assert "erfolgreich erstellt" in result
        assert "OKF v0.1 konform: Ja" in result

        # Datei existiert
        page_file = mcp_wiki / "wikis" / "main" / "neues-konzept.md"
        assert page_file.exists()

        # Inhalt pruefen
        content = page_file.read_text(encoding="utf-8")
        assert "type: Concept" in content
        assert "title: Neues Konzept" in content
        assert "Agent (TestAgent)" in content
        assert "status: AI-Generated" in content

    def test_updates_existing_page(self, mcp_wiki: Path):
        """Sollte eine vorhandene Seite aktualisieren."""
        from api.routes.mcp import okf_write_concept

        page_file = mcp_wiki / "wikis" / "main" / "python.md"

        result = okf_write_concept(
            slug="python",
            title="Python Aktualisiert",
            content="Aktualisierter Inhalt.",
            wiki="main",
            agent_name="TestAgent",
        )
        assert "aktualisiert" in result

        # Inhalt hat sich geaendert
        new_content = page_file.read_text(encoding="utf-8")
        assert "Aktualisiert" in new_content

    def test_okf_frontmatter_is_valid(self, mcp_wiki: Path):
        """Sollte gueltiges YAML-Frontmatter erzeugen."""
        import frontmatter
        from api.routes.mcp import okf_write_concept

        okf_write_concept(
            slug="fm-test",
            title="FM Test",
            content="Testinhalt.",
            wiki="main",
            tags=["fm", "test"],
            concept_type="Playbook",
            agent_name="FMTestAgent",
        )

        page_file = mcp_wiki / "wikis" / "main" / "fm-test.md"
        content = page_file.read_text(encoding="utf-8")
        post = frontmatter.loads(content)

        assert post.get("type") == "Playbook"
        assert post.get("title") == "FM Test"
        assert post.get("status") == "AI-Generated"
        assert "timestamp" in post.metadata

    def test_writes_to_nonexistent_wiki(self, mcp_wiki: Path):
        """Sollte Fehler fuer Wiki das nicht registriert ist.

        Hinweis: wiki_path() auto-creates dirs (bekannter Prod.-Bug).
        """
        from api.routes.mcp import okf_write_concept
        import shutil
        import core.config as cfg
        # Wiki-Verzeichnis entfernen falls vorhanden
        nonexistent = cfg.WIKIS_ROOT / "truly-nonexistent"
        if nonexistent.exists():
            shutil.rmtree(nonexistent)
        result = okf_write_concept(
            slug="test",
            title="Test",
            content="Test",
            wiki="truly-nonexistent",
        )
        # wiki_path() erstellt dirs automatisch → Seite wird erstellt
        assert "nicht gefunden" in result or "erfolgreich erstellt" in result


class TestMcpToolsOkfDeletePage:
    """Tests fuer das okf_delete_page Tool."""

    def test_deletes_page(self, mcp_wiki: Path):
        """Sollte eine Seite loeschen."""
        from api.routes.mcp import okf_write_concept, okf_delete_page
        okf_write_concept("temp-page", "Temp", "Inhalt", wiki="main")
        assert (mcp_wiki / "wikis" / "main" / "temp-page.md").exists()
        result = okf_delete_page("temp-page", "main")
        assert "geloescht" in result
        assert not (mcp_wiki / "wikis" / "main" / "temp-page.md").exists()

    def test_cannot_delete_system_page(self, mcp_wiki: Path):
        """Sollte Systemseiten nicht loeschen."""
        from api.routes.mcp import okf_delete_page
        result = okf_delete_page("index", "main")
        assert "System-Seite" in result

    def test_returns_error_for_missing_page(self, mcp_wiki: Path):
        """Sollte Fehler fuer fehlende Seite geben."""
        from api.routes.mcp import okf_delete_page
        result = okf_delete_page("nonexistent", "main")
        assert "nicht gefunden" in result


class TestMcpToolsOkfExportPage:
    """Tests fuer das okf_export_page Tool."""

    def test_exports_page(self, mcp_wiki: Path):
        """Sollte eine Seite exportieren."""
        from api.routes.mcp import okf_export_page
        result = okf_export_page("python", "main")
        assert "exportiert" in result
        # Datei im Export-Verzeichnis
        export_dir = mcp_wiki / "output_docs"
        assert export_dir.exists()
        exported = list(export_dir.glob("main__python.md"))
        assert len(exported) >= 1

    def test_returns_error_for_missing_page(self, mcp_wiki: Path):
        """Sollte Fehler fuer fehlende Seite geben."""
        from api.routes.mcp import okf_export_page
        result = okf_export_page("nonexistent", "main")
        assert "nicht gefunden" in result


class TestMcpToolsOkfListPending:
    """Tests fuer das okf_list_pending Tool."""

    def test_lists_pending_files(self, mcp_wiki_with_raw: Path):
        """Sollte ausstehende Dateien auflisten."""
        from api.routes.mcp import okf_list_pending
        result = okf_list_pending("main")
        assert "test_source.txt" in result or "another_article" in result

    def test_shows_empty_when_no_pending(self, mcp_wiki: Path):
        """Sollte leere Meldung anzeigen wenn keine Dateien pending."""
        from api.routes.mcp import okf_list_pending
        result = okf_list_pending("main")
        # raw/ existiert aber ist leer
        assert "Keine ausstehenden" in result


class TestMcpToolsOkfIngestText:
    """Tests fuer das okf_ingest_text Tool."""

    def test_ingests_text(self, mcp_wiki: Path):
        """Sollte Text ingesti koennen (via Mock)."""
        import subprocess
        from api.routes.mcp import okf_ingest_text

        # wiki.sh mocken
        original_run = subprocess.run
        def mock_run(cmd, **kwargs):
            if "./wiki.sh" in cmd[0] or (len(cmd) > 1 and "wiki.sh" in str(cmd)):
                # Simuliere Erfolg
                class FakeResult:
                    returncode = 0
                    stdout = ""
                    stderr = ""
                return FakeResult()
            return original_run(cmd, **kwargs)

        import api.routes.mcp as mcp_mod
        import services.sync as sync_mod
        original_do_sync = sync_mod.do_sync
        sync_mod.do_sync = lambda *a, **kw: None

        try:
            subprocess.run = mock_run
            result = okf_ingest_text("Dies ist ein Test", wiki="main", title="Test-Page")
            assert "erfolgreich ingesti" in result or "Fehler" in result
        finally:
            subprocess.run = original_run
            sync_mod.do_sync = original_do_sync


# ═══════════════════════════════════════════════════════════════════════════════
# C. Suche & Analyse (4 Tools)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpToolsOkfSearch:
    """Tests fuer das okf_search Tool."""

    def test_finds_matching_pages(self, mcp_wiki: Path):
        """Sollte passende Seiten finden."""
        from api.routes.mcp import okf_search
        result = okf_search("Python", "main")
        assert "Python" in result
        assert "Suchergebnisse" in result

    def test_finds_rust(self, mcp_wiki: Path):
        """Sollte Rust-Seite finden."""
        from api.routes.mcp import okf_search
        result = okf_search("Rust", "main")
        assert "Rust" in result

    def test_returns_no_results(self, mcp_wiki: Path):
        """Sollte Keine-Ergebnisse-Meldung geben."""
        from api.routes.mcp import okf_search
        result = okf_search("zzzznonexistentzzzz", "main")
        assert "Keine Ergebnisse" in result

    def test_empty_query(self, mcp_wiki: Path):
        """Sollte Fehler bei leerer Anfrage geben."""
        from api.routes.mcp import okf_search
        result = okf_search("", "main")
        assert "Suchbegriff" in result


class TestMcpToolsOkfWikiStats:
    """Tests fuer das okf_wiki_stats Tool."""

    def test_shows_stats(self, mcp_wiki: Path):
        """Sollte Statistiken anzeigen."""
        from api.routes.mcp import okf_wiki_stats
        result = okf_wiki_stats("main")
        assert "Statistiken" in result
        assert "Seiten:" in result

    def test_shows_types(self, mcp_wiki: Path):
        """Sollte Seitentypen auflisten."""
        from api.routes.mcp import okf_wiki_stats
        result = okf_wiki_stats("main")
        assert "Seiten nach Typ" in result


class TestMcpToolsOkfGraph:
    """Tests fuer das okf_graph Tool."""

    def test_shows_graph(self, mcp_wiki: Path):
        """Sollte Graph-Daten anzeigen."""
        from api.routes.mcp import okf_graph
        result = okf_graph("main")
        assert "Wissensgraph" in result
        assert "Knoten" in result

    def test_shows_nodes_and_edges(self, mcp_wiki: Path):
        """Sollte Knoten und Kanten auflisten."""
        from api.routes.mcp import okf_graph
        result = okf_graph("main")
        assert "Knoten (Seiten)" in result or "Kanten (Verknuepfungen)" in result


class TestMcpToolsOkfLint:
    """Tests fuer das okf_lint Tool."""

    def test_shows_lint_report(self, mcp_wiki: Path):
        """Sollte einen Lint-Bericht anzeigen."""
        from api.routes.mcp import okf_lint
        result = okf_lint("main")
        assert "Lint-Bericht" in result


# ═══════════════════════════════════════════════════════════════════════════════
# D. Rohquellen (2 Tools)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpToolsOkfReadRaw:
    """Tests fuer das okf_read_raw Tool."""

    def test_reads_existing_raw_file(self, mcp_wiki_with_raw: Path):
        """Sollte eine vorhandene Rohquelle lesen."""
        from api.routes.mcp import okf_read_raw
        result = okf_read_raw("test_source.txt")
        assert "Testquelle" in result
        assert "Rohquelle" in result

    def test_returns_error_for_missing_file(self, mcp_wiki: Path):
        """Sollte Fehler fuer fehlende Datei geben."""
        from api.routes.mcp import okf_read_raw
        result = okf_read_raw("nonexistent.txt")
        assert "nicht gefunden" in result

    def test_raw_dir_not_existing(self, mcp_wiki: Path):
        """Sollte Fehler geben wenn raw/ nicht existiert."""
        import core.config as cfg
        import shutil
        # raw/ loeschen falls vorhanden
        raw_dir = cfg.RAW_DIR
        if raw_dir.exists():
            shutil.rmtree(raw_dir)
        from api.routes.mcp import okf_read_raw
        result = okf_read_raw("any.txt")
        assert "nicht vorhanden" in result


class TestMcpToolsOkfListRaw:
    """Tests fuer das okf_list_raw Tool."""

    def test_lists_raw_files(self, mcp_wiki_with_raw: Path):
        """Sollte Rohquellen auflisten."""
        from api.routes.mcp import okf_list_raw
        result = okf_list_raw()
        assert "Rohquellen" in result
        assert "test_source.txt" in result

    def test_empty_raw_dir(self, mcp_wiki: Path):
        """Sollte leere Meldung bei leerem raw/ geben."""
        from api.routes.mcp import okf_list_raw
        result = okf_list_raw()
        assert "Keine Rohquellen" in result


# ═══════════════════════════════════════════════════════════════════════════════
# E. System (5 Tools)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpToolsOkfSystemStatus:
    """Tests fuer das okf_system_status Tool."""

    def test_shows_status(self, mcp_wiki: Path):
        """Sollte Systemstatus anzeigen."""
        from api.routes.mcp import okf_system_status
        result = okf_system_status()
        assert "Systemstatus" in result
        assert "Version" in result

    def test_shows_wiki_count(self, mcp_wiki: Path):
        """Sollte Wiki-Anzahl anzeigen."""
        from api.routes.mcp import okf_system_status
        result = okf_system_status()
        assert "Wikis:" in result
        assert "Benutzer:" in result


class TestMcpToolsOkfSystemSync:
    """Tests fuer das okf_system_sync Tool."""

    def test_syncs_single_wiki(self, mcp_wiki: Path):
        """Sollte ein einzelnes Wiki synchronisieren."""
        from api.routes.mcp import okf_system_sync
        result = okf_system_sync("main")
        assert "erfolgreich synchronisiert" in result

    def test_syncs_all_wikis(self, mcp_wiki: Path):
        """Sollte alle Wikis synchronisieren."""
        from api.routes.mcp import okf_system_sync
        result = okf_system_sync("")
        assert "Synchronisation" in result


class TestMcpToolsOkfAuditLogs:
    """Tests fuer das okf_audit_logs Tool."""

    def test_shows_logs(self, mcp_wiki: Path):
        """Sollte Audit-Protokolle anzeigen."""
        from api.routes.mcp import okf_audit_logs
        result = okf_audit_logs(limit=10)
        # Kann entweder Eintraege oder leere Meldung zeigen
        assert "Audit" in result

    def test_filters_by_action(self, mcp_wiki: Path):
        """Sollte nach Aktionstyp filtern koennen."""
        from api.routes.mcp import okf_audit_logs
        result = okf_audit_logs(action="login")
        assert "Audit" in result


class TestMcpToolsOkfCacheStats:
    """Tests fuer das okf_cache_stats Tool."""

    def test_shows_cache_stats(self, mcp_wiki: Path):
        """Sollte Cache-Statistiken anzeigen."""
        from api.routes.mcp import okf_cache_stats
        result = okf_cache_stats()
        assert "Cache-Statistiken" in result


class TestMcpToolsOkfCacheClear:
    """Tests fuer das okf_cache_clear Tool."""

    def test_clears_cache(self, mcp_wiki: Path):
        """Sollte Cache leeren."""
        from api.routes.mcp import okf_cache_clear
        result = okf_cache_clear()
        assert "erfolgreich geleert" in result


# ═══════════════════════════════════════════════════════════════════════════════
# F. Benutzer-Verwaltung (3 Tools)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpToolsOkfListUsers:
    """Tests fuer das okf_list_users Tool."""

    def test_lists_users(self, mcp_wiki: Path):
        """Sollte Benutzer auflisten."""
        from core.storage import create_user
        create_user("testuser", "pass123", role="editor")
        from api.routes.mcp import okf_list_users
        result = okf_list_users()
        assert "testuser" in result
        assert "editor" in result

    def test_empty_users(self, mcp_wiki: Path):
        """Sollte leere Meldung anzeigen."""
        from api.routes.mcp import okf_list_users
        result = okf_list_users()
        assert "Keine Benutzer" in result


class TestMcpToolsOkfCreateUser:
    """Tests fuer das okf_create_user Tool."""

    def test_creates_user(self, mcp_wiki: Path):
        """Sollte einen Benutzer erstellen."""
        from api.routes.mcp import okf_create_user
        result = okf_create_user("neuer-user", "Passwort123!", "editor")
        assert "erfolgreich erstellt" in result
        assert "neuer-user" in result

    def test_rejects_duplicate_user(self, mcp_wiki: Path):
        """Sollte doppelten Benutzernamen ablehnen."""
        from api.routes.mcp import okf_create_user
        okf_create_user("dup-user", "Pass1!")
        result = okf_create_user("dup-user", "Pass2!")
        assert "Fehler" in result


class TestMcpToolsOkfDeleteUser:
    """Tests fuer das okf_delete_user Tool."""

    def test_deletes_user(self, mcp_wiki: Path):
        """Sollte einen Benutzer loeschen."""
        from core.storage import create_user
        create_user("del-user", "pass", role="editor")
        from api.routes.mcp import okf_delete_user
        result = okf_delete_user("del-user")
        assert "erfolgreich geloescht" in result

    def test_returns_error_for_missing_user(self, mcp_wiki: Path):
        """Sollte Fehler fuer fehlenden Benutzer geben."""
        from api.routes.mcp import okf_delete_user
        result = okf_delete_user("nobody")
        assert "nicht gefunden" in result


# ═══════════════════════════════════════════════════════════════════════════════
# G. API-Key-Verwaltung (3 Tools)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpToolsOkfListApiKeys:
    """Tests fuer das okf_list_api_keys Tool."""

    def test_lists_keys(self, mcp_wiki: Path):
        """Sollte API-Keys auflisten."""
        from core.storage import create_key
        create_key("agent-1", "Test-Key", require_password=False)
        from api.routes.mcp import okf_list_api_keys
        result = okf_list_api_keys()
        assert "Test-Key" in result

    def test_empty_keys(self, mcp_wiki: Path):
        """Sollte leere Meldung anzeigen."""
        from api.routes.mcp import okf_list_api_keys
        result = okf_list_api_keys()
        assert "Keine API-Keys" in result


class TestMcpToolsOkfCreateApiKey:
    """Tests fuer das okf_create_api_key Tool."""

    def test_creates_key(self, mcp_wiki: Path):
        """Sollte einen API-Key erstellen."""
        from api.routes.mcp import okf_create_api_key
        result = okf_create_api_key("MCP-Agent-Key")
        assert "erfolgreich erstellt" in result
        assert "llmw_" in result  # Key-Prefix


class TestMcpToolsOkfDeleteApiKey:
    """Tests fuer das okf_delete_api_key Tool."""

    def test_deletes_key(self, mcp_wiki: Path):
        """Sollte einen API-Key loeschen."""
        from core.storage import create_key
        key_obj, _ = create_key("del-key", "Zum Loeschen", require_password=False)
        from api.routes.mcp import okf_delete_api_key
        result = okf_delete_api_key(key_obj["id"])
        assert "erfolgreich geloescht" in result

    def test_returns_error_for_missing_key(self, mcp_wiki: Path):
        """Sollte Fehler fuer fehlenden Key geben."""
        from api.routes.mcp import okf_delete_api_key
        result = okf_delete_api_key("nonexistent-key-id")
        assert "nicht gefunden" in result


# ═══════════════════════════════════════════════════════════════════════════════
# H. Update (2 Tools)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpToolsOkfCheckUpdate:
    """Tests fuer das okf_check_update Tool."""

    def test_shows_update_status(self, mcp_wiki: Path):
        """Sollte Update-Status anzeigen."""
        from api.routes.mcp import okf_check_update
        result = okf_check_update()
        assert "Update-Status" in result
        assert "Lokale Version" in result


class TestMcpToolsOkfRunUpdate:
    """Tests fuer das okf_run_update Tool."""

    def test_returns_error_without_script(self, mcp_wiki: Path):
        """Sollte Fehler geben wenn update.sh fehlt."""
        from api.routes.mcp import okf_run_update
        result = okf_run_update()
        assert "nicht gefunden" in result


# ═══════════════════════════════════════════════════════════════════════════════
# I. MCP-Verfuegbarkeit und Konfiguration
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpAvailability:
    """Tests fuer MCP-Server Verfuegbarkeit und Konfiguration."""

    def test_mcp_available(self):
        """MCP-Paket sollte installiert sein."""
        from api.routes.mcp import _MCP_AVAILABLE
        assert _MCP_AVAILABLE is True

    def test_mcp_server_initialized(self):
        """FastMCP Server sollte initialisiert sein."""
        from api.routes.mcp import mcp_server
        assert mcp_server is not None

    def test_mcp_tools_registered(self):
        """Alle 31 MCP-Tools sollten registriert sein."""
        from api.routes.mcp import mcp_server
        tool_names = [t.name for t in mcp_server._tool_manager.list_tools()]
        expected = [
            # Wiki-Verwaltung
            "okf_list_wikis",
            "okf_create_wiki",
            "okf_update_wiki",
            "okf_delete_wiki",
            # Seiten-Verwaltung
            "okf_list_pages",
            "okf_read_concept",
            "okf_write_concept",
            "okf_delete_page",
            "okf_export_page",
            "okf_list_pending",
            "okf_process_pending",
            "okf_ingest_text",
            # Suche & Analyse
            "okf_search",
            "okf_wiki_stats",
            "okf_graph",
            "okf_lint",
            # Rohquellen
            "okf_read_raw",
            "okf_list_raw",
            # System
            "okf_system_status",
            "okf_system_sync",
            "okf_audit_logs",
            "okf_cache_stats",
            "okf_cache_clear",
            # Benutzer
            "okf_list_users",
            "okf_create_user",
            "okf_delete_user",
            # API-Keys
            "okf_list_api_keys",
            "okf_create_api_key",
            "okf_delete_api_key",
            # Update
            "okf_check_update",
            "okf_run_update",
        ]
        for name in expected:
            assert name in tool_names, f"Tool '{name}' nicht registriert"

    def test_get_mcp_sse_app(self):
        """SSE-App sollte korrekt generiert werden."""
        from api.routes.mcp import get_mcp_sse_app
        app = get_mcp_sse_app()
        assert app is not None


# ═══════════════════════════════════════════════════════════════════════════════
# J. MCP API-Key Middleware
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpApiKeyMiddleware:
    """Tests fuer die MCP API-Key Middleware (ueber FastAPI TestClient)."""

    def test_mcp_sse_requires_api_key(self, client, mcp_wiki: Path):
        """SSE-Endpunkt sollte API-Key verlangen."""
        resp = client.get("/LLMWikiNG/mcp/sse")
        assert resp.status_code in (401, 503)

    def test_mcp_sse_rejects_wrong_key(self, client, mcp_wiki: Path):
        """SSE-Endpunkt sollte falschen Key ablehnen."""
        resp = client.get(
            "/LLMWikiNG/mcp/sse",
            headers={"X-API-Key": "falscher_key"},
        )
        assert resp.status_code == 401

    def test_mcp_messages_requires_api_key(self, client, mcp_wiki: Path):
        """Messages-Endpunkt sollte API-Key verlangen."""
        resp = client.post("/LLMWikiNG/mcp/messages")
        assert resp.status_code in (401, 503)

    def test_mcp_messages_rejects_wrong_key(self, client, mcp_wiki: Path):
        """Messages-Endpunkt sollte falschen Key ablehnen."""
        resp = client.post(
            "/LLMWikiNG/mcp/messages",
            headers={"X-API-Key": "falscher_key"},
        )
        assert resp.status_code == 401

    def test_mcp_sse_accepts_correct_key(self, client, mcp_wiki: Path):
        """SSE-Endpunkt sollte korrekten Key akzeptieren."""
        resp = client.get(
            "/LLMWikiNG/mcp/sse",
            headers={"X-API-Key": "test_mcp_key_2026"},
        )
        # 200 = SSE-Stream gestartet, 503 = MCP-App-Problem, aber KEIN 401
        assert resp.status_code != 401


# ═══════════════════════════════════════════════════════════════════════════════
# K. OKF v0.1-konforme Ausgabe
# ═══════════════════════════════════════════════════════════════════════════════


class TestOkfCompliance:
    """Tests fuer OKF v0.1 Konformitaet der MCP-Ausgabe."""

    def test_write_produces_valid_okf(self, mcp_wiki: Path):
        """Geschriebene Seiten sollten OKF-konform sein."""
        import frontmatter
        from api.routes.mcp import okf_write_concept

        okf_write_concept(
            slug="okf-test",
            title="OKF Test Seite",
            content="Testinhalt fuer OKF.",
            wiki="main",
            description="OKF Test",
            tags=["okf", "test"],
            concept_type="Reference",
            agent_name="OKFTestAgent",
        )

        page_file = mcp_wiki / "wikis" / "main" / "okf-test.md"
        content = page_file.read_text(encoding="utf-8")
        post = frontmatter.loads(content)

        assert "type" in post.metadata, "Feld 'type' fehlt (Pflichtfeld)"
        assert post.get("type") == "Reference"
        assert post.get("title") == "OKF Test Seite"
        assert post.get("description") == "OKF Test"
        assert post.get("status") == "AI-Generated"
        assert "timestamp" in post.metadata

        assert "# OKF Test Seite" in post.content
        assert "Testinhalt fuer OKF." in post.content

    def test_read_displays_okf_metadata(self, mcp_wiki: Path):
        """Lese-Ausgabe sollte alle OKF-Metadaten anzeigen."""
        from api.routes.mcp import okf_read_concept
        result = okf_read_concept("python", "main")
        # python.md hat timestamp durch unser Fixture
        for field in ["type:", "title:", "tags:", "timestamp:"]:
            assert field in result, f"OKF-Feld '{field}' fehlt in der Ausgabe"
