"""LLMWikiNG – MCP-Server (Model Context Protocol) mit OKF v0.1.

Stellt einen SSE-basierten MCP-Server bereit, der KI-Agenten (Cursor,
Windsurf, Claude Code etc.) erlaubt, das Wiki im Open Knowledge Format
(OKF v0.1) zu lesen, zu schreiben und zu durchsuchen.

Sicherheit: Alle MCP-Endpunkte werden ueber den konfigurierbaren
``LLMWIKING_MCP_KEY`` geschuetzt (via Middleware in main.py).

Verfuegbare MCP-Tools (31):
  Wiki-Verwaltung:
    okf_list_wikis, okf_create_wiki, okf_update_wiki, okf_delete_wiki

  Seiten-Verwaltung:
    okf_list_pages, okf_read_concept, okf_write_concept, okf_delete_page
    okf_export_page, okf_list_pending, okf_process_pending, okf_ingest_text

  Suche & Analyse:
    okf_search, okf_wiki_stats, okf_graph, okf_lint

  Rohquellen:
    okf_read_raw, okf_list_raw

  System:
    okf_system_status, okf_system_sync, okf_audit_logs
    okf_cache_stats, okf_cache_clear

  Benutzer-Verwaltung:
    okf_list_users, okf_create_user, okf_delete_user

  API-Key-Verwaltung:
    okf_list_api_keys, okf_create_api_key, okf_delete_api_key

  Update:
    okf_check_update, okf_run_update
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import subprocess

from core.config import (
    BASE_PATH,
    RAW_DIR,
    EXPORT_DIR,
    PROJECT_ROOT,
    DATA_DIR,
    WIKIS_ROOT,
    wiki_path,
    slugify_wiki,
    list_wikis,
    save_wiki_meta,
    delete_wiki,
    load_app_config,
    APP_VERSION,
    ENABLE_MCP_SERVER,
)
from services.wiki import (
    get_all_wiki_pages,
    read_wiki_file,
    extract_links_from_content,
    get_wiki_stats,
    slugify_german,
    run_sync_async,
)
from services.search import local_search
from services.sync import do_sync, append_okf_log, request_sync_background
from services.lint import run_lint
from services.graph import build_graph_data

import frontmatter

# ═══════════════════════════════════════════════════════════════════════════════
# FastMCP-Server Initialisierung
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from mcp.server.fastmcp import FastMCP
    
    kwargs = {}
    try:
        from mcp.server.transport_security import TransportSecuritySettings
        kwargs["transport_security"] = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
    except ImportError:
        pass

    mcp_server = FastMCP(
        "LLMWikiNG-OKF",
        instructions=(
            "LLMWikiNG MCP-Server - Open Knowledge Format (OKF v0.1). "
            "Lies und schreibe Wiki-Konzepte als standardisiertes Markdown "
            "mit YAML-Frontmatter. Alle Dokumente sind menschenlesbar und "
            "maschineninterpretierbar."
        ),
        **kwargs
    )
    _MCP_AVAILABLE = True
except ImportError:
    mcp_server = None  # type: ignore[assignment]
    _MCP_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
# Hilfsfunktionen
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_wiki_exists(wiki: str) -> str | None:
    """Prueft ob ein Wiki existiert. Gibt Fehlermeldung zurueck oder None."""
    slug = slugify_wiki(wiki)
    root = wiki_path(slug)
    if not root.exists():
        return f"Wiki '{wiki}' nicht gefunden."
    return None


def _format_size(size_bytes: int) -> str:
    """Formatiert Byte-Groesse in menschenlesbare Form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


# ═══════════════════════════════════════════════════════════════════════════════
# A. Wiki-Verwaltung (4 Tools)
# ═══════════════════════════════════════════════════════════════════════════════

if _MCP_AVAILABLE:

    # --- A1: List Wikis ---
    @mcp_server.tool()
    def okf_list_wikis() -> str:
        """Listet alle verfuegbaren Wikis mit Metadaten auf.

        Returns:
            Eine geordnete Liste aller Wikis mit slug, name, Seitenanzahl und Groesse.
        """
        wikis = list_wikis()
        if not wikis:
            return "Keine Wikis vorhanden."
        lines = ["# Verfuegbare Wikis\n"]
        for w in wikis:
            lines.append(
                f"- **{w.get('name', w['slug'])}** (slug: `{w['slug']}`) "
                f"- {w.get('page_count', '?')} Seiten, "
                f"{w.get('file_count', '?')} Dateien, "
                f"{_format_size(w.get('size', 0))}"
            )
        return "\n".join(lines)

    # --- A2: Create Wiki ---
    @mcp_server.tool()
    def okf_create_wiki(
        name: str,
        slug: str = "",
        description: str = "",
    ) -> str:
        """Erstellt ein neues Wiki.

        Args:
            name: Anzeigename des Wikis (z.B. 'Hoerspiele').
            slug: URL-sicherer Bezeichner (auto-generiert wenn leer).
            description: Kurzbeschreibung des Wikis.

        Returns:
            Bestaetigung mit Slug des neuen Wikis.
        """
        if not slug:
            slug = slugify_wiki(name)
        else:
            slug = slugify_wiki(slug)

        if not slug or slug == "main":
            # main-Verzeichnis pruefen
            root = wiki_path("main")
        else:
            root = wiki_path(slug)

        if root.exists():
            return f"Wiki mit Slug '{slug}' existiert bereits."

        try:
            root.mkdir(parents=True, exist_ok=True)
            save_wiki_meta(slug, name, description)
            # Index.md erstellen
            index_content = f"""---
type: System
title: "Index"
---
# {name}

Willkommen im Wiki **{name}**.
"""
            (root / "index.md").write_text(index_content, encoding="utf-8")
            try:
                from services.audit import log_action
                log_action(
                    action="mcp_create_wiki",
                    details=f"Wiki '{name}' (slug: {slug}) via MCP erstellt",
                    username="mcp-agent"
                )
            except Exception:
                pass
            return (
                f"Wiki '{name}' erfolgreich erstellt.\n"
                f"Slug: `{slug}`\n"
                f"Pfad: wikis/{slug}/"
            )
        except Exception as e:
            return f"Fehler beim Erstellen des Wikis: {e}"

    # --- A3: Update Wiki ---
    @mcp_server.tool()
    def okf_update_wiki(
        wiki: str,
        name: str = "",
        description: str = "",
        new_slug: str = "",
    ) -> str:
        """Bearbeitet die Metadaten eines bestehenden Wikis.

        Args:
            wiki: Aktueller Slug des Wikis.
            name: Neuer Name (leer = unveraendert).
            description: Neue Beschreibung (leer = unveraendert).
            new_slug: Neuer Slug (leer = unveraendert, fuehrte zur Umbenennung).

        Returns:
            Bestaetigung der Aenderung.
        """
        slug = slugify_wiki(wiki)
        root = wiki_path(slug)
        if not root.exists():
            return f"Wiki '{wiki}' nicht gefunden."

        # Metadaten aus wiki.json lesen
        meta_file = root / "wiki.json"
        current_meta = {}
        if meta_file.exists():
            try:
                current_meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        new_name = name or current_meta.get("name", slug)
        new_desc = description if description != "" else current_meta.get("description", "")

        target_slug = slugify_wiki(new_slug) if new_slug else slug

        if target_slug != slug:
            new_root = wiki_path(target_slug)
            if new_root.exists():
                return f"Wiki mit Slug '{target_slug}' existiert bereits."
            try:
                root.rename(new_root)
            except Exception as e:
                return f"Fehler beim Umbenennen: {e}"
            slug = target_slug

        try:
            save_wiki_meta(slug, new_name, new_desc)
            return (
                f"Wiki erfolgreich aktualisiert.\n"
                f"Slug: `{slug}`\n"
                f"Name: {new_name}\n"
                f"Beschreibung: {new_desc or '(keine)'}"
            )
        except Exception as e:
            return f"Fehler beim Aktualisieren: {e}"

    # --- A4: Delete Wiki ---
    @mcp_server.tool()
    def okf_delete_wiki(wiki: str) -> str:
        """Loescht ein Wiki und alle zugehoerigen Dateien.

        ACHTUNG: Standard-Wiki 'main' kann nicht geloescht werden!

        Args:
            wiki: Slug des Wikis.

        Returns:
            Bestaetigung der Loeschung.
        """
        slug = slugify_wiki(wiki)
        if slug == "main":
            return "Das Standard-Wiki 'main' kann nicht geloescht werden."
        root = wiki_path(slug)
        if not root.exists():
            return f"Wiki '{wiki}' nicht gefunden."
        try:
            delete_wiki(slug)
            try:
                from services.audit import log_action
                log_action(
                    action="mcp_delete_wiki",
                    details=f"Wiki '{wiki}' (slug: `{slug}`) via MCP gelöscht",
                    username="mcp-agent"
                )
            except Exception:
                pass
            return f"Wiki '{wiki}' (slug: `{slug}`) erfolgreich geloescht."
        except Exception as e:
            return f"Fehler beim Loeschen: {e}"

    # --- A5: List Pages ---
    @mcp_server.tool()
    def okf_list_pages(wiki: str = "main") -> str:
        """Listet alle Seiten eines Wikis auf (ohne Systemseiten).

        Args:
            wiki: Slug des Wikis (z.B. 'main', 'hoerspiele').

        Returns:
            Eine geordnete Liste aller Seiten mit Titel, Typ und Slug.
        """
        slug = slugify_wiki(wiki)
        root = wiki_path(slug)
        if not root.exists():
            return f"Wiki '{wiki}' nicht gefunden."
        pages = get_all_wiki_pages(slug)
        if not pages:
            return f"Keine Seiten im Wiki '{wiki}'."
        lines = [f"# Seiten im Wiki '{wiki}'\n"]
        for p in pages:
            lines.append(
                f"- [{p['title']}](./{p['slug']}.md) - "
                f"Typ: `{p.get('type', 'concept')}`"
            )
        return "\n".join(lines)

    # --- A6: Read Concept ---
    @mcp_server.tool()
    def okf_read_concept(slug: str, wiki: str = "main") -> str:
        """Liest eine Wiki-Seite im Open Knowledge Format (OKF v0.1).

        Liefert das vollstaendige YAML-Frontmatter (Metadaten) und den
        menschenlesbaren Markdown-Inhalt.

        Args:
            slug: Dateiname/Slug der Seite (z.B. 'mcp-architektur').
            wiki: Slug des Wikis (Default: 'main').

        Returns:
            Der vollstaendige OKF-Inhalt der Seite.
        """
        wiki_slug = slugify_wiki(wiki)
        raw_slug = re.sub(r"\.md$", "", slug)
        data = read_wiki_file(f"{raw_slug}.md", wiki_slug)
        if not data:
            return f"Seite '{slug}' in Wiki '{wiki}' nicht gefunden."
        content = data.get("content", "")
        # Frontmatter parsen fuer saubere Ausgabe
        post = frontmatter.loads(content)
        # Strukturierte Ausgabe
        lines = [f"# OKF-Concept: {raw_slug}\n"]
        lines.append("## Metadaten (YAML-Frontmatter)\n")
        for key in [
            "type", "title", "description", "tags",
            "timestamp", "author", "status",
        ]:
            val = post.get(key)
            if val is not None:
                lines.append(f"- **{key}:** `{val}`")
        lines.append("")
        lines.append("## Inhalt (Markdown)\n")
        lines.append(post.content.strip())
        # Verlinkungen
        links = extract_links_from_content(content)
        if links:
            lines.append("\n## Verknuepfte Seiten\n")
            for link in links:
                lines.append(f"- [{link}](./{link}.md)")
        return "\n".join(lines)

    # --- A7: Write Concept ---
    @mcp_server.tool()
    def okf_write_concept(
        slug: str,
        title: str,
        content: str,
        wiki: str = "main",
        description: str = "",
        tags: list[str] | None = None,
        concept_type: str = "Concept",
        agent_name: str = "MCP-Agent",
    ) -> str:
        """Erstellt oder aktualisiert eine Wiki-Seite nach OKF v0.1 Standard.

        Die Seite erhaelt automatisch ein gueltiges YAML-Frontmatter mit
        dem Pflichtfeld 'type' gemaess Open Knowledge Format.

        Args:
            slug: Eindeutiger Dateiname/Slug (z.B. 'sicherheitskonzept').
            title: Human-readable Ueberschrift.
            content: Der eigentliche Inhalt in sauberem Markdown.
            wiki: Slug des Wikis (Default: 'main').
            description: Einzeilige Zusammenfassung.
            tags: Liste von Kategorie-Tags.
            concept_type: OKF-Typ (Concept, Playbook, API-Doc, Reference).
            agent_name: Name des schreibenden Agenten/Systems.

        Returns:
            Bestaetigung mit Pfad zur geschriebenen Datei.
        """
        wiki_slug = slugify_wiki(wiki)
        root = wiki_path(wiki_slug)
        if not root.exists():
            return f"Wiki '{wiki}' nicht gefunden."

        raw_slug = re.sub(r"\.md$", "", slug)
        filepath = root / f"{raw_slug}.md"

        # Pruefe ob Seite bereits existiert
        existed = filepath.exists()

        # OKF v0.1 Frontmatter erstellen
        now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        post = frontmatter.Post(
            content=f"\n# {title}\n\n{content}",
            type=concept_type,
            title=title,
            description=description,
            tags=tags or [],
            timestamp=now_iso,
            author=f"Agent ({agent_name})",
            status="AI-Generated",
        )
        okf_content = frontmatter.dumps(post)

        # Schreibe die Datei
        filepath.write_text(okf_content, encoding="utf-8")

        # OKF-Log aktualisieren
        action = "update" if existed else "create"
        try:
            append_okf_log(
                action, f"{raw_slug}.md",
                f"Via MCP ({agent_name})", wiki_slug,
            )
        except Exception:
            pass

        # Sync ausfuehren
        try:
            request_sync_background(wiki_slug)
        except Exception:
            pass

        try:
            from services.audit import log_action
            log_action(
                action="mcp_write_concept",
                details=f"Concept '{title}' ({raw_slug}.md) in Wiki '{wiki_slug}' via MCP geschrieben ({action})",
                username=f"mcp-agent ({agent_name})"
            )
        except Exception:
            pass

        status = "aktualisiert" if existed else "erstellt"
        return (
            f"OKF-Concept '{title}' erfolgreich {status}.\n"
            f"Pfad: wikis/{wiki_slug}/{raw_slug}.md\n"
            f"Typ: {concept_type}\n"
            f"OKF v0.1 konform: Ja"
        )

    # --- A8: Delete Page ---
    @mcp_server.tool()
    def okf_delete_page(slug: str, wiki: str = "main") -> str:
        """Loescht eine Wiki-Seite.

        ACHTUNG: Systemseiten (index, log, ingestlater) koennen nicht
        geloescht werden.

        Args:
            slug: Dateiname/Slug der Seite (ohne .md).
            wiki: Slug des Wikis (Default: 'main').

        Returns:
            Bestaetigung der Loeschung.
        """
        wiki_slug = slugify_wiki(wiki)
        err = _ensure_wiki_exists(wiki)
        if err:
            return err

        raw_slug = re.sub(r"\.md$", "", slug)
        if raw_slug in ("index", "log", "ingestlater"):
            return f"System-Seite '{raw_slug}' kann nicht geloescht werden."

        filepath = wiki_path(wiki_slug) / f"{raw_slug}.md"
        if not filepath.exists():
            return f"Seite '{raw_slug}' in Wiki '{wiki}' nicht gefunden."

        try:
            filepath.unlink()
            try:
                append_okf_log("delete", f"{raw_slug}.md", "Via MCP geloescht", wiki_slug)
            except Exception:
                pass
            try:
                request_sync_background(wiki_slug)
            except Exception:
                pass
            try:
                from services.audit import log_action
                log_action(
                    action="mcp_delete_page",
                    details=f"Seite '{raw_slug}' aus Wiki '{wiki_slug}' via MCP gelöscht",
                    username="mcp-agent"
                )
            except Exception:
                pass
            return (
                f"Seite '{raw_slug}' aus Wiki '{wiki}' geloescht.\n"
                f"Sync wurde ausgefuehrt."
            )
        except Exception as e:
            return f"Fehler beim Loeschen: {e}"

    # --- A9: Export Page ---
    @mcp_server.tool()
    def okf_export_page(slug: str, wiki: str = "main") -> str:
        """Exportiert eine Wiki-Seite in das output_docs/ Verzeichnis.

        Args:
            slug: Dateiname/Slug der Seite (ohne .md).
            wiki: Slug des Wikis (Default: 'main').

        Returns:
            Pfad zur exportierten Datei.
        """
        wiki_slug = slugify_wiki(wiki)
        err = _ensure_wiki_exists(wiki)
        if err:
            return err

        raw_slug = re.sub(r"\.md$", "", slug)
        src = wiki_path(wiki_slug) / f"{raw_slug}.md"
        if not src.exists():
            return f"Seite '{raw_slug}' in Wiki '{wiki}' nicht gefunden."

        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        dest = EXPORT_DIR / f"{wiki_slug}__{raw_slug}.md"
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return (
            f"Seite '{raw_slug}' exportiert.\n"
            f"Ziel: output_docs/{wiki_slug}__{raw_slug}.md"
        )

    # --- A10: List Pending ---
    @mcp_server.tool()
    def okf_list_pending(wiki: str = "main") -> str:
        """Listet Rohquellen-Dateien auf, die auf Ingest warten.

        Args:
            wiki: Slug des Wikis (Default: 'main').

        Returns:
            Liste der ausstehenden Dateien.
        """
        from services.wiki import get_pending_files
        pending = get_pending_files()
        if not pending:
            return "Keine ausstehenden Dateien."
        lines = ["# Ausstehende Dateien (raw/)\n"]
        for item in pending:
            name = item.get("name", "?")
            size = item.get("size", 0)
            lines.append(f"- `{name}` ({_format_size(size)})")
        return "\n".join(lines)

    # --- A11: Process Pending ---
    @mcp_server.tool()
    def okf_process_pending(wiki: str = "main") -> str:
        """Verarbeitet alle ausstehenden Rohquellen-Dateien (Ingest).

        Fuehrt den automatisierten Ingest-Prozess fuer alle Dateien
        im raw/ Verzeichnis aus.

        WICHTIG: FastMCP ruft Tools synchron auf. Daher ist diese Funktion
        ein regulaeres ``def``. Die blockierenden Subprozesse (Ingest, Sync)
        werden ueber ``subprocess.run`` direkt ausgefuehrt, da der MCP-Server
        die Tools ohnehin synchron aufruft.

        Args:
            wiki: Slug des Wikis (Default: 'main').

        Returns:
            Ergebnis des Ingest-Prozesses.
        """
        slug = slugify_wiki(wiki)
        from services.wiki import get_pending_files
        pending = get_pending_files()
        if not pending:
            return "Keine ausstehenden Dateien zum Verarbeiten."

        processed = []
        errors = []
        backend = os.environ.get("LLM_BACKEND", "ollama")
        cfg = load_app_config()
        env = os.environ.copy()
        env["LLM_BACKEND"] = backend
        env["OLLAMA_HOST"] = cfg.get("ollama_host", "http://localhost:11434")
        env["OLLAMA_MODEL"] = cfg.get("ollama_model", "llama3.2:3b")
        env["WIKI_DIR"] = str(wiki_path(slug))
        env["RAW_DIR"] = str(RAW_DIR)

        for item in pending:
            filepath = RAW_DIR / item["name"]
            if not filepath.exists():
                continue
            try:
                result = subprocess.run(
                    ["./wiki.sh", "ingest", str(filepath)],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(PROJECT_ROOT), env=env,
                )
                if result.returncode == 0:
                    processed.append(item["name"])
                else:
                    errors.append(f"{item['name']}: {result.stderr.strip() or 'Fehler'}")
            except Exception as e:
                errors.append(f"{item['name']}: {str(e)}")

        try:
            request_sync_background(slug)
        except Exception:
            pass

        lines = [f"# Ingest-Ergebnis fuer Wiki '{wiki}'\n"]
        lines.append(f"- Verarbeitet: {len(processed)}")
        lines.append(f"- Fehler: {len(errors)}")
        if errors:
            lines.append("\n## Fehler\n")
            for e in errors:
                lines.append(f"- {e}")
        return "\n".join(lines)

    # --- A12: Ingest Text ---
    @mcp_server.tool()
    def okf_ingest_text(
        text: str,
        wiki: str = "main",
        title: str = "",
    ) -> str:
        """Ingest von reinem Text in ein Wiki.

        Speichert den Text als Markdown-Datei und fuehrt den Ingest-Prozess aus.

        WICHTIG: FastMCP ruft Tools synchron auf. Daher ist diese Funktion
        ein regulaeres ``def``. Die blockierenden Subprozesse (Ingest, Sync)
        werden ueber ``subprocess.run`` direkt ausgefuehrt, da der MCP-Server
        die Tools ohnehin synchron aufruft.

        Args:
            text: Der einzulesende Text (wird als Markdown behandelt).
            wiki: Slug des Wikis (Default: 'main').
            title: Titel der Seite (wird als Ueberschrift verwendet).

        Returns:
            Bestaetigung mit neuem Slug.
        """
        slug = slugify_wiki(wiki)
        root = wiki_path(slug)
        if not root.exists():
            return f"Wiki '{wiki}' nicht gefunden."

        if not title:
            title = "Paste"

        safe_title = slugify_german(title) or "paste"
        if not text.startswith("#"):
            text = f"# {title}\n\n{text}"

        temp_dir = RAW_DIR
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / f"{safe_title}.md"
        temp_file.write_text(text, encoding="utf-8")

        cfg = load_app_config()
        env = os.environ.copy()
        env["WIKI_DIR"] = str(root)
        env["RAW_DIR"] = str(RAW_DIR)

        try:
            result = subprocess.run(
                ["./wiki.sh", "ingest", str(temp_file)],
                capture_output=True, text=True, timeout=120,
                cwd=str(PROJECT_ROOT), env=env,
            )
            if result.returncode == 0:
                try:
                    request_sync_background(slug)
                except Exception:
                    pass
                return (
                    f"Text erfolgreich ingesti.\n"
                    f"Wiki: {wiki}\n"
                    f"Slug: `{safe_title}`\n"
                    f"Titel: {title}"
                )
            else:
                return f"Fehler beim Ingest: {result.stderr.strip()}"
        except Exception as e:
            return f"Fehler beim Ingest: {e}"

    # --- A13: Search ---
    @mcp_server.tool()
    def okf_search(query: str, wiki: str = "main") -> str:
        """Durchsucht das Wiki nach Begriffen (Volltextsuche).

        Args:
            query: Suchbegriff.
            wiki: Slug des Wikis oder 'all' fuer Cross-Wiki-Suche.

        Returns:
            Suchergebnisse mit Titel, Slug und Vorschau.
        """
        if not query or not query.strip():
            return "Bitte einen Suchbegriff angeben."
        result = local_search(query.strip(), wiki)
        results = result.get("results", [])
        if not results:
            return f"Keine Ergebnisse fuer '{query}' in Wiki '{wiki}'."
        lines = [f"# Suchergebnisse fuer '{query}' (Wiki: {wiki})\n"]
        for i, r in enumerate(results[:20], 1):
            lines.append(
                f"**{i}. [{r['title']}](./{r['slug']}.md)** "
                f"(Wiki: {r.get('wiki', wiki)})\n"
                f"   {r.get('snippet', '')[:150]}...\n"
            )
        return "\n".join(lines)

    # --- A14: Wiki Stats ---
    @mcp_server.tool()
    def okf_wiki_stats(wiki: str = "main") -> str:
        """Zeigt Statistiken fuer ein Wiki (Seiten, Woerter, Dateien).

        Args:
            wiki: Slug des Wikis (Default: 'main').

        Returns:
            Detaillierte Statistiken des Wikis.
        """
        slug = slugify_wiki(wiki)
        err = _ensure_wiki_exists(wiki)
        if err:
            return err
        stats = get_wiki_stats(slug)
        pages = get_all_wiki_pages(slug)
        types: dict[str, int] = {}
        for p in pages:
            t = p.get("type", "concept")
            types[t] = types.get(t, 0) + 1
        lines = [f"# Statistiken fuer Wiki '{wiki}'\n"]
        lines.append(f"- **Seiten:** {stats['page_count']}")
        lines.append(f"- **Woerter gesamt:** {stats['word_count']}")
        lines.append(f"- **Rohquellen:** {stats['raw_count']}")
        lines.append(f"- **Exporte:** {stats['export_count']}")
        if types:
            lines.append("\n## Seiten nach Typ\n")
            for t, count in sorted(types.items()):
                lines.append(f"- `{t}`: {count}")
        return "\n".join(lines)

    # --- A15: Graph ---
    @mcp_server.tool()
    def okf_graph(wiki: str = "main") -> str:
        """Gibt die Wissensgraph-Daten eines Wikis zurueck.

        Zeigt Knoten (Seiten) und Kanten (Verknuepfungen) als strukturierte
        Uebersicht.

        Args:
            wiki: Slug des Wikis (Default: 'main').

        Returns:
            Graph-Daten als Markdown-Liste.
        """
        slug = slugify_wiki(wiki)
        err = _ensure_wiki_exists(wiki)
        if err:
            return err
        graph = build_graph_data(slug)
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        lines = [f"# Wissensgraph fuer Wiki '{wiki}'\n"]
        lines.append(f"- **Knoten:** {len(nodes)}")
        lines.append(f"- **Kanten:** {len(edges)}")
        if nodes:
            lines.append("\n## Knoten (Seiten)\n")
            for n in nodes:
                ntype = n.get("type", "?")
                lines.append(f"- [{n['label']}](./{n['id']}.md) (Typ: `{ntype}`)")
        if edges:
            lines.append("\n## Kanten (Verknuepfungen)\n")
            for e in edges:
                lines.append(f"- {e.get('source', '?')} → {e.get('target', '?')}")
        return "\n".join(lines)

    # --- A16: Lint ---
    @mcp_server.tool()
    def okf_lint(wiki: str = "main") -> str:
        """Fuehrt eine Gesundheitspruefung des Wikis durch (Lint).

        Findet verwaiste Seiten, fehlende Verknuepfungen, tote Links etc.

        Args:
            wiki: Slug des Wikis (Default: 'main').

        Returns:
            Detaillierten Lint-Bericht.
        """
        slug = slugify_wiki(wiki)
        err = _ensure_wiki_exists(wiki)
        if err:
            return err
        result = run_lint(slug)
        lines = [f"# Lint-Bericht fuer Wiki '{wiki}'\n"]

        orphans = result.get("orphans", [])
        if orphans:
            lines.append(f"## Verwaiste Seiten ({len(orphans)})\n")
            for o in orphans:
                lines.append(f"- `{o}`")

        missing = result.get("missing", [])
        if missing:
            lines.append(f"\n## Fehlende Verknuepfungen ({len(missing)})\n")
            for m in missing:
                lines.append(f"- `{m}`")

        broken = result.get("broken", [])
        if broken:
            lines.append(f"\n## Tote Links ({len(broken)})\n")
            for b in broken:
                lines.append(f"- `{b}`")

        if not orphans and not missing and not broken:
            lines.append("Alle Pruefungen bestanden. Keine Probleme gefunden.")

        return "\n".join(lines)

    # --- A17: Read Raw ---
    @mcp_server.tool()
    def okf_read_raw(filename: str) -> str:
        """Liest eine Rohquellen-Datei aus dem raw/-Verzeichnis.

        Args:
            filename: Name der Rohquellen-Datei (z.B. 'artikel.txt').

        Returns:
            Der Inhalt der Rohquellen-Datei.
        """
        if not RAW_DIR.exists():
            return "Rohquellen-Verzeichnis (raw/) nicht vorhanden."
        filepath = RAW_DIR / filename
        if not filepath.exists() or not filepath.is_file():
            return f"Rohquelle '{filename}' nicht gefunden."
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            size = filepath.stat().st_size
            return (
                f"# Rohquelle: {filename}\n"
                f"Groesse: {_format_size(size)}\n\n"
                f"```\n{content[:10000]}\n```"
            )
        except Exception as e:
            return f"Fehler beim Lesen: {e}"

    # --- A18: List Raw ---
    @mcp_server.tool()
    def okf_list_raw() -> str:
        """Listet alle Rohquellen-Dateien im raw/-Verzeichnis auf.

        Returns:
            Eine Liste aller verfuegbaren Rohquellen.
        """
        if not RAW_DIR.exists():
            return "Rohquellen-Verzeichnis (raw/) nicht vorhanden."
        files = sorted(RAW_DIR.iterdir()) if RAW_DIR.exists() else []
        files = [f for f in files if f.is_file()]
        if not files:
            return "Keine Rohquellen vorhanden."
        lines = ["# Rohquellen (raw/)\n"]
        for f in files:
            size = f.stat().st_size
            lines.append(f"- `{f.name}` ({_format_size(size)})")
        return "\n".join(lines)

    # --- A19: System Status ---
    @mcp_server.tool()
    def okf_system_status() -> str:
        """Zeigt den Systemstatus von LLMWikiNG an.

        Returns:
            Systeminformationen wie Version, Wikis, Benutzer und API-Keys.
        """
        from core.storage import list_users, list_keys
        wikis = list_wikis()
        users = list_users()
        keys = list_keys()
        lines = ["# LLMWikiNG Systemstatus\n"]
        lines.append(f"- **Version:** {APP_VERSION}")
        lines.append(f"- **Wikis:** {len(wikis)}")
        lines.append(f"- **Benutzer:** {len(users)}")
        lines.append(f"- **API-Keys:** {len(keys)}")
        if wikis:
            lines.append("\n## Wikis\n")
            for w in wikis:
                lines.append(f"- {w.get('name', w['slug'])} (`{w['slug']}`)")
        return "\n".join(lines)

    # --- A20: System Sync ---
    @mcp_server.tool()
    def okf_system_sync(wiki: str = "") -> str:
        """Synchronisiert ein Wiki oder alle Wikis (Embedding-Updates).

        Args:
            wiki: Slug des Wikis (leer = alle Wikis synchronisieren).

        Returns:
            Ergebnis der Synchronisation.
        """
        if wiki:
            slug = slugify_wiki(wiki)
            err = _ensure_wiki_exists(wiki)
            if err:
                return err
            try:
                do_sync(slug, force=True)
                return f"Wiki '{wiki}' erfolgreich synchronisiert."
            except Exception as e:
                return f"Fehler bei der Synchronisation: {e}"
        else:
            results = {}
            for w in list_wikis():
                try:
                    do_sync(w["slug"], force=True)
                    results[w["slug"]] = "ok"
                except Exception as e:
                    results[w["slug"]] = f"fehler: {e}"
            lines = ["# Synchronisation aller Wikis\n"]
            for slug_name, status in results.items():
                lines.append(f"- `{slug_name}`: {status}")
            return "\n".join(lines)

    # --- A21: Audit Logs ---
    @mcp_server.tool()
    def okf_audit_logs(
        limit: int = 20,
        action: str = "",
        username: str = "",
    ) -> str:
        """Zeigt die letzten Audit-Protokolle an.

        Args:
            limit: Maximale Anzahl Eintraege (Default: 20).
            action: Filter nach Aktionstyp (z.B. 'login', 'create').
            username: Filter nach Benutzername.

        Returns:
            Die letzten Audit-Eintraege.
        """
        from services.audit import get_logs
        logs, total = get_logs(
            limit=min(limit, 100),
            action=action or None,
            username=username or None,
        )
        if not logs:
            return "Keine Audit-Eintraege vorhanden."
        lines = [f"# Audit-Protokoll ({total} Eintraege, zeige {len(logs)})\n"]
        for log in logs:
            ts = log.get("timestamp", "?")
            act = log.get("action", "?")
            user = log.get("username", "?")
            details = log.get("details", "")[:100]
            lines.append(f"- **{ts}** | `{act}` | {user} | {details}")
        return "\n".join(lines)

    # --- A22: Cache Stats ---
    @mcp_server.tool()
    def okf_cache_stats() -> str:
        """Zeigt aktuelle Cache-Statistiken an.

        Returns:
            Detaillierte Cache-Statistiken.
        """
        from services.cache import get_cache
        stats = get_cache().stats()
        lines = ["# Cache-Statistiken\n"]
        for key, value in stats.items():
            lines.append(f"- **{key}:** {value}")
        return "\n".join(lines)

    # --- A23: Cache Clear ---
    @mcp_server.tool()
    def okf_cache_clear() -> str:
        """Leert den gesamten In-Memory-Cache.

        Returns:
            Bestaetigung.
        """
        from services.cache import get_cache
        get_cache().clear()
        return "Cache erfolgreich geleert."

    # --- A24: List Users ---
    @mcp_server.tool()
    def okf_list_users() -> str:
        """Listet alle Benutzer auf.

        Returns:
            Eine Liste aller registrierten Benutzer mit Rollen.
        """
        from core.storage import list_users
        users = list_users()
        if not users:
            return "Keine Benutzer vorhanden."
        lines = ["# Benutzer\n"]
        for u in users:
            status = "aktiv" if u.get("active", True) else "deaktiviert"
            lines.append(
                f"- **{u['username']}** (Rolle: `{u['role']}`, {status})"
            )
        return "\n".join(lines)

    # --- A25: Create User ---
    @mcp_server.tool()
    def okf_create_user(
        username: str,
        password: str,
        role: str = "editor",
    ) -> str:
        """Erstellt einen neuen Benutzer.

        Args:
            username: Benutzername.
            password: Passwort.
            role: Rolle ('admin' oder 'editor').

        Returns:
            Bestaetigung der Erstellung.
        """
        from core.storage import create_user
        try:
            create_user(username, password, role=role)
            return (
                f"Benutzer '{username}' erfolgreich erstellt.\n"
                f"Rolle: {role}"
            )
        except ValueError as e:
            return f"Fehler: {e}"

    # --- A26: Delete User ---
    @mcp_server.tool()
    def okf_delete_user(username: str) -> str:
        """Loescht einen Benutzer.

        Args:
            username: Benutzername.

        Returns:
            Bestaetigung der Loeschung.
        """
        from core.storage import list_users, delete_user
        users = list_users()
        target = None
        for u in users:
            if u["username"] == username:
                target = u
                break
        if not target:
            return f"Benutzer '{username}' nicht gefunden."
        try:
            delete_user(target["id"])
            return f"Benutzer '{username}' erfolgreich geloescht."
        except Exception as e:
            return f"Fehler beim Loeschen: {e}"

    # --- A27: List API Keys ---
    @mcp_server.tool()
    def okf_list_api_keys() -> str:
        """Listet alle API-Keys auf.

        Returns:
            Eine Liste aller API-Keys (ohne die geheimen Schluessel).
        """
        from core.storage import list_keys
        keys = list_keys()
        if not keys:
            return "Keine API-Keys vorhanden."
        lines = ["# API-Keys\n"]
        for k in keys:
            status = "aktiv" if k.get("active", True) else "deaktiviert"
            pw = " + Passwort" if k.get("require_password") else ""
            lines.append(
                f"- **{k['name']}** (ID: `{k['id'][:8]}...`, "
                f"{status}{pw})"
            )
        return "\n".join(lines)

    # --- A28: Create API Key ---
    @mcp_server.tool()
    def okf_create_api_key(
        name: str,
        require_password: bool = False,
        scopes: list[str] | None = None,
    ) -> str:
        """Erstellt einen neuen API-Key.

        Args:
            name: Bezeichnung fuer den Key.
            require_password: Passwort-Zusatz erforderlich.
            scopes: Bereiche (Default: read, write).

        Returns:
            Der vollstaendige API-Key (einmalig angezeigt!).
        """
        from core.storage import create_key
        key_obj, raw = create_key(
            user_id="mcp-agent",
            name=name,
            require_password=require_password,
            scopes=scopes or ["read", "write"],
        )
        return (
            f"API-Key '{name}' erfolgreich erstellt.\n\n"
            f"**API-Key (einmalig angezeigt - aufbewahren!):**\n"
            f"`{raw}`\n\n"
            f"ID: {key_obj['id'][:8]}...\n"
            f"Scopes: {', '.join(scopes or ['read', 'write'])}"
        )

    # --- A29: Delete API Key ---
    @mcp_server.tool()
    def okf_delete_api_key(key_id: str) -> str:
        """Loescht einen API-Key.

        Args:
            key_id: ID oder Beginn des API-Keys.

        Returns:
            Bestaetigung der Loeschung.
        """
        from core.storage import list_keys, delete_key
        keys = list_keys()
        target = None
        for k in keys:
            if k["id"] == key_id or k["id"].startswith(key_id):
                target = k
                break
        if not target:
            return f"API-Key '{key_id}' nicht gefunden."
        try:
            delete_key(target["id"])
            return f"API-Key '{target['name']}' (ID: `{target['id'][:8]}...`) erfolgreich geloescht."
        except Exception as e:
            return f"Fehler beim Loeschen: {e}"

    # --- A30: Check Update ---
    @mcp_server.tool()
    def okf_check_update() -> str:
        """Prueft, ob ein Update auf GitHub verfuegbar ist.

        Vergleicht die lokale VERSION-Datei mit origin/main.

        Returns:
            Versionsinformationen und Update-Status.
        """
        version_file = PROJECT_ROOT / "VERSION"
        local_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unbekannt"

        try:
            subprocess.run(
                ["git", "fetch", "origin"],
                capture_output=True, text=True, timeout=30,
                cwd=str(PROJECT_ROOT),
            )
            proc = subprocess.run(
                ["git", "show", "origin/main:VERSION"],
                capture_output=True, text=True, timeout=15,
                cwd=str(PROJECT_ROOT),
            )
            remote_version = proc.stdout.strip() if proc.returncode == 0 else None
        except Exception:
            remote_version = None

        lines = ["# Update-Status\n"]
        lines.append(f"- **Lokale Version:** {local_version}")
        if remote_version:
            lines.append(f"- **Remote-Version:** {remote_version}")
            if local_version == remote_version:
                lines.append("- **Status:** Auf dem neuesten Stand.")
            else:
                lines.append("- **Status:** Update verfuegbar!")
        else:
            lines.append("- **Remote-Version:** Konnte nicht abgerufen werden.")
            lines.append("- **Status:** Unbekannt (Git-Fehler).")
        return "\n".join(lines)

    # --- A31: Run Update ---
    @mcp_server.tool()
    def okf_run_update() -> str:
        """Fuehrt das System-Update aus (via update.sh).

        ACHTUNG: Dieses Tool fuehrt ein `git reset --hard origin/main`
        aus und installiert Python-Abhaengigkeiten neu.

        Returns:
            Ergebnis des Updates mit Versionsinformationen.
        """
        update_script = PROJECT_ROOT / "update.sh"
        if not update_script.exists():
            return "update.sh nicht gefunden. Manuelles Update erforderlich."

        version_file = PROJECT_ROOT / "VERSION"
        old_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unbekannt"

        try:
            proc = subprocess.run(
                [str(update_script)],
                capture_output=True, text=True, timeout=300,
                cwd=str(PROJECT_ROOT),
            )
            raw_output = proc.stdout + proc.stderr
            clean_output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw_output)
            new_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unbekannt"

            from services.audit import log_action
            log_action(
                action="mcp_update",
                details=f"MCP: Update von {old_version} nach {new_version}",
                username="mcp-agent"
            )

            lines = ["# Update-Ergebnis\n"]
            lines.append(f"- **Alte Version:** {old_version}")
            lines.append(f"- **Neue Version:** {new_version}")
            lines.append(f"- **Update ausgefuehrt:** {'Ja' if old_version != new_version else 'Keine Aenderung'}")
            if clean_output.strip():
                lines.append(f"\n## Output\n\n```\n{clean_output[:5000]}\n```")
            return "\n".join(lines)
        except subprocess.TimeoutExpired:
            return "Update-Skript hat 300 Sekunden ueberschritten."
        except Exception as e:
            return f"Update fehlgeschlagen: {e}"


def get_mcp_sse_app():
    """Gibt die Starlette SSE-App des MCP-Servers zurueck (oder None)."""
    if _MCP_AVAILABLE and mcp_server is not None:
        return mcp_server.sse_app()
    return None
