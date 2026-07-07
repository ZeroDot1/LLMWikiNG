# Changelog

Alle wichtigen Änderungen an LLMWikiNG werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
LLMWikiNG folgt [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.4.0] – 2026-07-07

### Browser-basierter Rohquellen-Editor

#### Added
- **Browser-Editor Modul** (`raw_editor.py`): Ermöglicht das Verfassen und Bearbeiten von Dokumenten direkt im Browser.
- **Dual-Editor Design** (`raw_editor.html`): Umschaltbar zwischen einem ablenkungsfreien WYSIWYG-Modus (mit Echtzeit-Vorschau) und einem rohen Markdown-Editor.
- **Vanilla-JavaScript**: Absolut freie Implementierung ohne externe JS-Bibliotheken zur Einhaltung maximaler Performance und Ladezeiten.
- **Sidebar-Link**: Direkte Verlinkung über das Hauptmenü als „Rohquellen-Editor“.
- **Sprachunterstützung**: Lokalisierte Texte für den Editor in Deutsch und Englisch (`de.json`, `en.json`).

## [1.3.0] – 2026-07-07

### Open Knowledge Format (OKF) Support

#### Added
- **OKF-Unterstützung**: Vollständige Einhaltung der OKF v0.1 Spezifikation für Wiki-Seiten, Inhaltsverzeichnis (`index.md`) und Änderungslog (`log.md`).
- **Standard Markdown Links**: Interne Links werden als native Markdown-Links (`[Text](/slug.md)`) anstelle von Obsidian-Wikilinks (`[[Link]]`) gepflegt.
- **Hierarchische Konzepte**: Unterstützung von tiefen und strukturierten Ordnerhierarchien im Wiki.
- **Migrationswerkzeug** (`tools/migrate_to_okf.py`): Python-Skript zur automatischen Konvertierung bestehender Wikis.

#### Changed
- **Linter & Links**: CLI und Web-Linter prüfen nun rekursiv und erkennen standardmäßige Markdown-Links anstelle der alten Wikilinks.
- **Wissensgraph**: Der 2D-Wissensgraph extrahiert Verbindungen nun aus nativem Markdown.
- **System-Prompt**: `prompts/system.md` dahingehend aktualisiert, dass neue Seiten nur noch im OKF-Standard verfasst werden.

## [1.2.0] – 2026-07-06

### Git-basierte Update-Funktion

#### Changed
- **Update-Mechanismus**: Von curl+unzip auf Git umgestellt (`git fetch origin && git reset --hard origin/main`)
- **Versionsprüfung**: Nutzt jetzt `git fetch` + `git show origin/main:VERSION` statt curl
- **update.sh**: Komplett überarbeitet – prüft auf Git-Verfügbarkeit, erstellt Backup, stasht lokale Änderungen, führt `git reset --hard origin/main` aus

#### Removed
- Abhängigkeit von `curl` und `unzip` für Updates (weiterhin für andere Funktionen verfügbar)

---

## [1.1.0] – 2026-07-06

### Mehrsprachigkeit & Einstellungs-Seite

#### Added
- **Mehrsprachigkeit**: Vollständige Internationalisierung (DE/EN) mit Sprachumschaltung via Cookie (`?lang=de|en`)
- **Einstellungs-Seite** (`/settings`): Tab-basierte Oberfläche mit Sprache, SMTP-Konfiguration, Gesundheitscheck und Update
- **Sprach-Parameter** für Server-Start: `--lang/-l` (CLI), `"language"` in `config.json`
- **Drittanbieter-Credits**: vis-network Lizenzhinweise in README, about.html und graph.html
- **Übersetzung**: Alle 17 HTML-Templates nutzen `{{ _('key') }}`-Funktion, 435 Strings in `lang/de.json` und `lang/en.json`

#### Changed
- **Update-Funktion**: Von eigener Seite (`/admin/update`) in Einstellungs-Tab verschoben
- **Sidebar**: Aufgeräumt – Lint, Config und Update nur noch über Einstellungen erreichbar
- **README & about.html**: Vollständige Server-Parameter-Dokumentation

#### Removed
- Separate `/admin/update`-Seite (weitergeleitet zu `/settings?tab=update`)
- Separate `/lint`- und `/config`-Menüpunkte in der Sidebar
- Sprachwechsler aus der Sidebar (jetzt in Einstellungen)

---

## [1.0.0] – 2026-07-06

### Erster stabiler Release

Dies ist der erste vollständige Release von LLMWikiNG – einer persönlichen
Wissensdatenbank, die mittels lokaler LLMs und des Karpathy-Wiki-Patterns
betrieben wird.

#### Highlights

- **CLI-Tool (`wiki.sh`)** mit init, ingest, search, export, lint, sync,
  reindex, list, status, config – alles über ein einziges Shell-Skript
- **Web-Interface (`llmWiki.py`)** mit Flask/Uvicorn im Tokyo-Night-Design
- **Interaktiver Wissensgraph** via vis-network.js (offline, farbcodiert)
- **Wochenberichte & E-Mail-Briefings** mit SMTP-Presets für Gmail,
  ProtonMail Bridge und Mail.ru
- **BM25-Volltextsuche** mit Term-Highlighting in Wiki, Rohquellen und Exporten
- **Web-Linter** für verwaiste Seiten, Staleness, defekte Quellen-Referenzen
- **Web-Ingest** mit Upload, Text-Paste und URL-Merkzettel

#### Features im Detail

- init: Ordnerstruktur, index.md, log.md, qmd-Collection
- ingest: Quelle nach raw/ archivieren, Wiki-Seite mit YAML-Frontmatter,
  LLM-Zusammenfassung, index+log update, qmd sync
- search: Hybrid-Suche (BM25 + Vektor) via qmd, JSON-Ausgabe
- lint: Orphan-Seiten, fehlende Links, fehlende Seiten, Statistiken
- export: Wiki-Seite nach output_docs/ kopieren
- list: Alle Wiki-Dokumente anzeigen
- reindex: index.md neu aufbauen
- status: Wiki-Statistiken + Tool-Verfügbarkeit
- config: Aktuelle Konfiguration anzeigen
- Dashboard (/), Wiki-Ansicht (/wiki/&lt;page&gt;), Suche (/search),
  Web-Ingest (/ingest), Wissensgraph (/graph), Linter (/lint),
  Status (/status), Briefings (/briefings), SMTP-Config (/config),
  Rohquellen (/raw), Exporte (/export)

#### Technik

- LLM-Backends: ollama (Standard), agy, opencode
- Suchmaschine: qmd (BM25 + Vektor)
- Webserver: Flask + Uvicorn (ASGI)
- Templates: Jinja2 mit Tokyo-Night Dark Theme
- Lizenz: Unlicense (Public Domain)

---

## [0.1.0] – 2026-07-06

### Initialer Commit

Erste Version des Projekts mit grundlegender Struktur:
- README.md, Lizenz, Git-Ignore
- .agy.yaml mit Agenten-Konfiguration
- wiki.sh (CLI) und llmWiki.py (Web-Interface)
- prompts/system.md (erster System-Prompt)
- Templates, Styles, Wiki-Seiten
- start.sh, email_sender.py
- tools/: qmd_search.sh, read_and_export.sh

---

## Template

<!--
  Format für neue Einträge:

## [VERSION] – YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Deprecated
- ...

### Removed
- ...

### Fixed
- ...

### Security
- ...
-->
