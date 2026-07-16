# Changelog

Alle wichtigen Änderungen an LLMWikiNG werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
LLMWikiNG folgt [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.4.3] – 2026-07-16

### WebUI-Server-Neustart & Robusterer Daten-Erhalt bei Updates

#### Added
- **Webserver-Neustart in WebUI**: Nach einem Update wird im Log-Bereich der Settings ein Button angezeigt, mit dem der Webserver direkt aus der GUI heraus neu gestartet werden kann (beendet den Python-Prozess sauber; im Docker-Container führt `restart: always` zum automatischen Booten).

#### Fixed
- **Robusterer Daten-Erhalt bei Updates**: Die Benutzer-Datenbanken (`data/users.json`, `data/api_keys.json`) und die `config.json` werden nun vor Git-Operationen im Update-Skript explizit in das Backup gesichert und danach wiederhergestellt, um Datenverlust beim Überschreiben oder Stashen vollkommen auszuschließen.

---

## [2.4.2] – 2026-07-16

### Custom Scrollbars & Erweiterte Netzwerk-Ingest Dokumentation

#### Added
- **Custom Scrollbar Styling**: CSS-Scrollbars wurden global für das gesamte Web-Interface (inklusive Codeblöcken und Pre-Elementen) hinzugefügt, um ein einheitliches Tokyo-Night/Blue-Violet Design über alle Browser (Chrome, Safari, Firefox) hinweg zu gewährleisten.
- **Erweiterte Ingest-Dokumentation**: README.md, about.html und about_de.html wurden um detaillierte Erklärungen zum direkten Netzwerk-Ingest über die HTTP-API (mit curl-Beispiel) und der sicheren API-Key-Recovery-Modalitäten erweitert.

---

## [2.4.1] – 2026-07-16

### Lizenz-Refactoring & API-Key Recovery unter Settings

#### Added
- **API-Key nachträglich anzeigen**: Administratoren können ab jetzt ihre generierten API-Schlüssel direkt unter *Einstellungen* -> *API-Keys* einsehen. Zum Schutz der Keys ist dies nur nach Verifizierung des eigenen Passworts (Argon2) über ein sicheres Overlay-Modal möglich.
- **Verschlüsselte Key-Speicherung**: Generierte API-Schlüssel werden ab jetzt zusätzlich umkehrbar verschlüsselt (`encrypted_key` in `api_keys.json`) via `itsdangerous` mit dem System-Secret gesichert, um eine spätere Anzeige nach Passworteingabe zu ermöglichen. Der SHA-256-Hash bleibt für schnelle API-Validierungen erhalten.
- **Kopier-Fallback (HTTP/HTTPS)**: Ein robuster Zwischenablage-Fallback mit einem unsichtbaren Textarea-Element wurde für den API-Key-Kopiervorgang implementiert. Dies stellt sicher, dass das Kopieren des API-Schlüssels auch in unsicheren Netzwerk-Kontexten (HTTP) fehlerfrei funktioniert, wenn die moderne `navigator.clipboard`-API vom Browser blockiert wird.
- **Hilfsskript für Geheimnisse (`change_secret.sh`)**: Neues Tool zur einfachen, automatischen Generierung eines neuen kryptografischen Secrets (`LLMWIKI_SECRET`) in der `docker-compose.yml`, um Standard-Credentials leicht anpassen zu können.


#### Changed
- **Lizenzmodell auf AGPL-3.0 umgestellt**: Das gesamte Projekt (inkl. der neu geschriebenen Canvas-Graph-Engine) wurde vollständig unter die **GNU Affero General Public License v3.0 (AGPL-3.0)** gestellt. Alle Lizenzerklärungen (`LICENSE`, `README.md`, Übersetzungstabellen sowie die Über-Seiten `about.html` / `about_de.html`) wurden entsprechend aktualisiert.

---

## [2.4.0] – 2026-07-16

### Wissensgraph: vis-network durch eigene Vanilla-JS Canvas-Engine ersetzt (−632 KB)


#### Changed
- **Wissensgraph vollständig neu implementiert**: Die externe `vis-network`-Bibliothek (632 KB, Apache-2.0/MIT) wurde komplett entfernt und durch eine eigene, abhängigkeitsfreie Canvas-Graph-Engine in reinem JavaScript ersetzt. Das Seitengewicht der Graph-Seite sinkt um **über 95 %**.
- **`static/js/graph-engine.js`** (neu): Vollständige `GraphEngine`-Klasse mit Force-Directed-Simulation (Repulsion O(n²), Federkraft, Zentralkraft), Canvas-2D-Rendering, O(1)-Node-Lookup via `Map`, korrekter Pfeilspitzen-Geometrie an Node-Rändern und `ctx.roundRect()`-Support.
- **`static/js/graph.js`** (überarbeitet): Nutzt nun `import { GraphEngine }` statt globales `vis`-Objekt; enthält Fehlerbehandlung und zeigt Lademeldung bei Netzwerkfehler.
- **`templates/graph.html`**: `<div id="network">` durch `<canvas id="network">` ersetzt; `vis-network.min.js`-Script-Tag entfernt.
- **`lang/de.json` / `lang/en.json`**: `graph.credit` und `vis_network_*`-Schlüssel auf eigene Engine aktualisiert.
- **`templates/about.html` / `about_de.html`**: Feature-Beschreibung, Projektstruktur-Baum und Drittanbieter-Lizenzabschnitt auf Canvas-Engine aktualisiert.

#### Added (Engine-Features gegenüber vis-network)
- **Pointer Events** (statt `mousedown`/`touchstart`) → voller Touch- & Stylus-Support ohne weitere Anpassungen
- **`ResizeObserver`** → Canvas-Auflösung passt sich automatisch an HiDPI-Displays und Fenstergrößenänderungen an (Device Pixel Ratio)
- **HTML-Tooltip-Div** mit Glassmorphism-Stil (absolut positioniert, kein DOM-Overhead pro Knoten)
- **Spiralen-Startlayout** verhindert initiale Knoten-Überlagerungen
- **`destroy()`-Methode** zum sauberen Freigeben von `requestAnimationFrame` und `ResizeObserver`
- **Fehlerbehandlung** in `graph.js`: Bei API-Fehlern wird eine Fehlermeldung im Ladebereich angezeigt

#### Removed
- **`static/vis-network.min.js`** (632 KB) – vollständig gelöscht

---

## [2.3.0] – 2026-07-15

### Backup & Restore, Docker-Optimierungen, private Updates & i18n

#### Added
- **Backup & Restore System**: Vollständig integriertes Sicherungssystem im Settings-Tab (`/settings?tab=backup`). Erzeugt komprimierte `.tar.xz`-Archive (XZ-Format) mit allen Wikis, Rohquellen, Benutzerkonten und Einstellungen und erlaubt deren Wiederherstellung direkt über die WebUI.
- **Docker-Optimierungen**: Dockerfile auf `python:3-slim` (immer aktuellste Python-Version) aktualisiert und docker-compose.yml zur vollständigen Kapselung aller Daten innerhalb des Containers vorkonfiguriert (keine Host-Dateimounts nötig).
- **Private Repository-Unterstützung**: Das Update-Skript (`update.sh`) unterstützt nun die Authentifizierung über `GITHUB_TOKEN` (Personal Access Tokens), um Updates auch für unveröffentlichte/private Repositories via WebUI oder Terminal zu ermöglichen.
- **Vollständige i18n-Lokalisierung**: Das Registrierungssystem, die Erfolgsseite und alle Sicherheitseinstellungen wurden komplett für Deutsch und Englisch lokalisiert.
- **Zweisprachige Dokumentation**: Über-Seite (`/about`) und Dokumentation (`/docs`) liegen nun in separaten, sprachabhängigen Versionen vor (`about_de.html`/`docs_de.html` und `about.html`/`docs.html`).

---

## [2.2.0] – 2026-07-14

### Registrierungssystem, Setup-Redirection, Auto-API-Key & Settings

#### Added
- **Benutzerregistrierung** (`/register`): Komplett neues Registrierungssystem inklusive Template (`templates/register.html`) für die Ersteinrichtung und optionale weitere Registrierungen.
- **Auto-API-Key Generierung**: Bei erfolgreicher Registrierung wird für den Benutzer vollautomatisch ein Standard-API-Key erzeugt und einmalig im Klartext auf der Erfolgsseite (`templates/register_success.html`) präsentiert.
- **Deaktivierbare Registrierung**: Administratoren können die Benutzerregistrierung in den Einstellungen (`/settings` -> Checkbox „Registrierung neuer Benutzer erlauben“) aktivieren/deaktivieren. Der Wert wird in `config.json` gesichert.
- **Sicherheits-Automatik**: Nach der Registrierung des ersten Benutzers (der automatisch als `admin` angelegt wird) schaltet das System die Registrierung in der Config automatisch ab, um unbefugten Zugriff zu verhindern.

#### Fixed
- **Setup-Umleitung**: Wenn noch keine Benutzer in der Datenbank existieren, wird jeder Aufruf der Login-Seiten oder passwortgeschützten Pfade nun intelligent direkt auf die Registrierungsseite geleitet.

---

## [2.1.0] – 2026-07-14

### CLI-Ingest-Client, Direkte Wiki-APIs, Link-Bugfixes & Spenden-Button

#### Added
- **Interaktiver CLI Ingest- & Such-Client** (`tools/api_ingest_client.py`): Ein mächtiges CLI-Skript, das als Fernbedienung dient, um interaktiv Wikis auszuwählen und Dateien, URLs oder Texte direkt über die API einzuspielen oder zu durchsuchen.
- **Direkte Wiki-API-Endpunkte** (`/wiki/{wiki_name}/api/ingest` & `/wiki/{wiki_name}/api/sync`): Unterstützt direkte Datei-Uploads, URL-Downloads und Text-Eingaben für spezifische Wikis.
- **Release-Bereinigungs-Skript** (`clean_release.sh`): Skript zum automatischen Löschen aller Testdaten (Exporte, Test-Wikis, Nutzer und API-Keys zurücksetzen) vor Pushs auf GitHub.
- **Unterstützungshinweis & Donate-Button**: Gelber Donate-Button oben rechts sowie Support-Aufruf im README und der Über-Seite.

#### Fixed
- **Link-Parsing Bugfix**: Relative Link-Präfixe wie `./` und `../` werden im Link-Extractor nun korrekt abgeschnitten, sodass Kanten im Wissensgraphen gezeichnet und Links vom Linter richtig verarbeitet werden.
- **API-Key Performance**: Das Aktualisieren von `last_used` bei API-Zugriffen erfolgt nun blockierungsfrei im Hintergrund (FastAPI BackgroundTasks).
- **Fehlerseiten-Konflikt**: API-Fehlermeldungen werden nun stets als strukturiertes JSON statt als gerenderte HTML-Seite zurückgegeben.

---

## [2.0.0] – 2026-07-14

### Vollständiger FastAPI-Rewrite, Multi-Wiki, Auth & Tailwind v4

#### Added
- **Komplett auf FastAPI umgestellt**: Der Flask-Webserver `llmWiki.py` (samt `editor.py`, `email_sender.py`) wurde vollständig entfernt. Alle Routen, Services und Template-Helfer wurden 1:1 nach FastAPI portiert; die bestehenden Jinja2-Templates werden weiterverwendet.
- **Mehrere Wikis (Multi-Wiki)**: Jedes Wiki liegt unter `wikis/<name>/` mit eigenem `index.md`/`log.md`. Das ursprüngliche `wiki/` wird beim ersten Start automatisch nach `wikis/main/` migriert.
- **Authentifizierung**: Login mit Benutzername + Passwort (Argon2-Hashes, signierte Sessions). Beim ersten Start wird über `/login` automatisch der erste Admin angelegt. Benutzer- und API-Key-Verwaltung unter `/users` bzw. `/api-keys` (nur Admin).
- **JSON-API** unter `/LLMWikiNG/api/v1` (Key-geschützt via `X-API-Key`, optional mit `X-API-Password`). Endpunkte für Wikis, Seiten, Suche, Graph, Stats, Lint, Status.
- **Theme nur in den Einstellungen**: Das Erscheinungsbild (Dark/Light) wird ausschließlich in `Einstellungen → Erscheinungsbild` geändert und persistent in `config.json` gespeichert (`"theme"`). Dark Mode ist Standard und wird server-seitig aus `config.json` geladen (keine FOUC, keine Toggle-Buttons in der Sidebar/Header).
- **Dokumentationsseite** `/docs` (Sidebar-Link, Übersicht zu Erste Schritte, Multi-Wiki, Auth, API, Frontend, Web-Routen).
- **Einstellungs-Tabs erweitert**: Die Settings-Seite enthält nun zusätzliche Tabs **Benutzerverwaltung** (`/users`) und **API-Schlüssel** (`/api-keys`) mit Anlegen/Löschen direkt in der WebUI. Das Dashboard zeigt Wiki-Anzahl und per-Wiki-Statistiken.

#### Fixed
- **Fehlende Übersetzungen in Einstellungen**: `users.*`- und `apikeys.*`-Schlüssel sowie `users.create_hint` ergänzt (DE/EN) – Tab-Inhalte renderten zuvor teils als Roh-Keys.
- **Theme-Persistenz**: Alle Einstellungen (Theme, Sprache, SMTP) werden ausschließlich in `config.json` gespeichert und server-seitig geladen; das Erscheinungsbild ist Dark-Standard, ohne Umschalter in der Sidebar.
- **Dashboard überarbeitet**: Zeigt nun Wiki-Anzahl, gesamt- und pro-Wiki-Statistiken (Seiten, Rohquellen, Exporte) sowie eine Wiki-Übersicht mit Direktlinks.
- **Einstellungen erweitert**: Benutzer- und API-Key-Verwaltung sind jetzt als Tabs (`Benutzer`, `API-Keys`) in den Einstellungen integriert (neue Raw-Key-Anzeige inklusive).
- **JSON-API paritätisch erweitert** (`/api/v1`): User- & API-Key-CRUD (Admin), Ingest-Upload/-Pending/-Process, Seiten-Export, `system/status` und `system/sync`.
- **API-Exception-Handling korrigiert**: HTTP-Fehler bei API-Anfragen (`/api/v1/...`) liefern nun korrekte JSON-Fehlermeldungen statt einer HTML-Seite.
- **API-Key Performance optimiert**: Aktualisierung des `last_used` Felds wird jetzt asynchron über FastAPI-BackgroundTasks abgewickelt, um I/O-Blockaden der API zu verhindern.

#### Changed
- **Frontend auf Tailwind CSS v4**: CSS-First-Pipeline (`@theme` mit oklch-Design-Tokens, Dark Mode, responsiv). Build via `frontend/` → `static/css/tailwind-build.css`.
- **JavaScript externalisiert**: Alle Inline-Skripte wurden in ES-Module ausgelagert (`static/js/`: app, navigation, auth, graph, editor, settings, presets, update, page, ingest). Nur der `window.BASE_PATH`-Schalter verbleibt inline.
- **Routen unter Basis-Pfad** `/LLMWikiNG` (konfigurierbar via `LLMWIKI_BASE_PATH`).
- **Konfiguration** zentral in `config.json` (Sprache, Theme, SMTP, `LLMWIKI_*`-Umgebungsvariablen für Secret/Basis-Pfad).

#### Removed
- Flask-Abhängigkeit und `llmWiki.py`/`editor.py`/`email_sender.py`.
- Theme-Toggle-Buttons aus Header und Sidebar (nur noch über Einstellungen).
- Redundante Artefakte: `frontend/static`, `frontend/templates`, `backend/scratch`, alte Scaffold-Reste, `tree.txt`, verwaistes `wiki/`.

---

## [1.8.0] – 2026-07-07

### Server-Reset, vollständige Dokumentation & Editor-Feature

#### Added
- **Server-Reset über `start.sh`**: Neuer `--reset`-Parameter für `start.sh` zum Zurücksetzen des Servers auf Werkseinstellungen. Löscht unwiderruflich alle Wiki-Seiten (`wiki/`), Rohquellen (`raw/`) und Exporte (`output_docs/`). Legt `index.md` und `log.md` OKF-konform neu an und setzt die qmd-Such-Collection zurück.
- **Non-interaktiver Reset**: `./start.sh --reset -y` bzw. `./start.sh --reset --yes` führt den Reset ohne manuelle Bestätigung aus.
- **Dokumentation vervollständigt (README & Über-Seite)**: Fehlende Features (Editor, Einstellungen) in den Feature-Listen ergänzt. `--reset` in Server-Parametern dokumentiert. CLI-Befehlsreferenz auf der Über-Seite komplettiert (init, list, status, config, update, version, reset mit start.sh).

#### Changed
- **Version auf 1.8.0 angehoben** (VERSION, wiki.sh)
- **start.sh-Banner**: Version wird nun dynamisch aus der `VERSION`-Datei gelesen

## [1.7.0] – 2026-07-07

### Editor-Bearbeitungs-Buttons & Universeller Editor

#### Added
- **Bearbeiten-Buttons**: Jede Wiki-Seite und jede Rohquelle hat jetzt einen „Bearbeiten“-Button, der die Seite direkt im Editor öffnet.
- **Universeller Editor**: Der Rohquellen-Editor wurde in einen allgemeinen Editor umbenannt (`editor.py` / `editor.html`) und unterstützt nun sowohl Wiki-Seiten (`wiki/`) als auch Rohquellen (`raw/`).
- **Ordner-Weiche**: Automatische Erkennung des Zielverzeichnisses basierend auf dem gewählten Modus.

## [1.6.0] – 2026-07-07

### Universeller Editor & Bearbeitungs-Buttons

#### Added
- **Universeller Editor** (`editor.py` / `editor.html`): Der Rohquellen-Editor wurde in einen allgemeinen, mächtigen „Editor“ umbenannt und erweitert.
- **Wiki-Seiten bearbeiten**: Jede Wiki-Seite hat jetzt einen „Bearbeiten“-Button erhalten, welcher die Seite direkt im Editor öffnet.
- **Rohquellen bearbeiten**: Jede Text-Rohquelle besitzt einen „Bearbeiten“-Button, um sie im Browser zu verändern, bevor sie eingespielt wird.
- **Ordner-Weiche**: Der Editor lädt und speichert Dokumente dynamisch im korrekten Verzeichnis (`wiki/` oder `raw/`), basierend auf dem Modus.
- **Aktualisierte Lokalisierung**: Alle Begriffe wurden von „Rohquellen-Editor“ auf „Editor“ vereinheitlicht und angepasst.

## [1.5.0] – 2026-07-07

### Erweiterter WYSIWYG Rohquellen-Editor

#### Added
- **Markdown-Formatierungen im WYSIWYG-Editor**: Unterstützung für Links (Prompt-Eingabe), Bilder (Prompt-Eingabe), Inline-Code (`<code>`), Blockquotes (`<blockquote>`), Trennlinien (`<hr>`) und Durchstreichen (`~~`).
- **Erweiterte Toolbar**: Neue interaktive Symbole und Buttons zur schnellen Formatierung.
- **Optimierte HTML-to-Markdown-Konvertierung**: Clientseitiges Scripting wurde erweitert, um all diese neuen Tags nativ in korrektes Markdown umzuwandeln.

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
