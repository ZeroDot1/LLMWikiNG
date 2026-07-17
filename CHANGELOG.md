# Changelog

Alle wichtigen Änderungen an LLMWikiNG werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
LLMWikiNG folgt [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.5.1] – 2026-07-17

### Dokumentation: Vorgehensweise nach Änderung des System-Secrets

#### Changed
- **`README.md`**: Detaillierte Schritt-für-Schritt-Anleitung ergänzt, was nach einer Geheimnis-Rotation (Secret-Wechsel) oder bei der Migration von Bestands-Installationen mit altem Secret aus `docker-compose.yml` zu beachten und auszuführen ist (Re-Login, Löschung alter Keys, Aktualisierung von Skripten).

---

## [2.5.0] – 2026-07-17


### Security: Vollständige Migration des System-Secrets in die Config-Struktur

#### Removed
- **Geheimnis-Skript (`change_secret.sh`)**: Skript vollständig gelöscht, da die Rotation des Secrets nun sicher und direkt über die Weboberfläche in den Einstellungen gesteuert wird.
- **Docker-Compose Secret Variable**: Umgebungsvariable `LLMWIKI_SECRET` in der `docker-compose.yml` gelöscht. Das Geheimnis wird nicht mehr über Umgebungsvariablen an Container übergeben, sondern ausschließlich über die persistenten App-Daten verwaltet.

#### Changed
- **Dokumentation (Changelog, README, Über)**: Alle Verweise auf `change_secret.sh` und docker-basierte Secret-Konfigurationen gelöscht und durch die neue Web-Steuerung und config-basierte Persistenz unter Einstellungen ➜ Backup & Restore ersetzt.

---

## [2.4.9] – 2026-07-17


### Security: Persistierung & Steuerung des System-Secrets (LLMWIKI_SECRET)

#### Added
- **System-Secret-Management im Einstellungs-Menü (`templates/settings.html`)**: Neue Steuerungs-Karte im "Backup & Restore"-Tab. Ermöglicht nach Eingabe des Administratorpassworts das Anzeigen oder das sichere Neugenerieren des System-Geheimnisses direkt über die Web-Oberfläche.
- **System-Secret Endpoints (`backend/api/routes/auth.py`)**: Endpunkte `/system-secret/reveal` und `/system-secret/regenerate` unter Administrator-Berechtigungsschutz hinzugefügt.

#### Changed
- **Persistierung in `config.json` (`backend/core/security.py`)**: Das kryptografische System-Secret (`LLMWIKI_SECRET`) wird nun prioritär aus der persistenten `config.json` (Schlüssel `secret_key`) geladen und dort bei Erstgenerierung sicher abgelegt. Dies verhindert jeglichen Daten- und Entschlüsselungsverlust bei Updates über die Weboberfläche (Git Pulls).

---

## [2.4.8] – 2026-07-17


### Fixes: API-Key Reveal Passwort-Validierung & UI Einstellungs-Tabs

#### Fixed
- **API-Key Reveal Decryption Error Handling (`backend/api/routes/auth.py`)**: Fehlermeldungen bei der Passwort-Verifizierung für API-Keys verfeinert. Tritt ein Fehler bei der Schlüssel-Entschlüsselung auf (z.B. durch Rotation des System-Secrets `LLMWIKI_SECRET`), wird nun eine präzise Fehlermeldung ausgegeben, anstatt fälschlicherweise "Ungültiges Passwort" anzuzeigen.

#### Changed
- **Einstellungsseiten (`templates/settings.html`)**: Layouts für *Benutzerverwaltung* und *API-Schlüssel* überarbeitet. Tabellen haben nun abgerundete Ecken, Statuselemente nutzen farbige Badges (Erfolgreich/Inaktiv/Admin/Editor) und Actions verwenden ansprechendere Symbole. Duplikate im HTML-Markup wurden bereinigt.

---

## [2.4.7] – 2026-07-17


### WebUI: Optimierung der Registrierungsseite & Verifizierung des Update-Backups

#### Changed
- **Registrierungserfolgseite (`templates/register_success.html`)**: Layout-Design überarbeitet mit besseren Grid-Spalten, klarem Warnbereich und modernem Card-Shadow.
- **Lokalisierungstexte (`lang/de.json` / `lang/en.json`)**: Erklärungstext aktualisiert um den Hinweis, dass der API-Key jederzeit nachträglich in den Einstellungen nach Eingabe des Benutzerpassworts sichtbar gemacht werden kann.
- **Sicherheitsprüfung Update-Skript (`update.sh`)**: Das Update-Skript sichert das komplette Projektverzeichnis (inkl. Configs und Nutzer-DBs unter `data/`) vor einem Git-Reset in ein timestamp-basiertes Verzeichnis unter `/tmp` und stellt diese Daten danach automatisch wieder her. Dies gewährleistet, dass keine Dateien durch Git-Updates verloren gehen.

---

## [2.4.6] – 2026-07-17


### Knowledge Graph – CSS Modularisierung & Layout-Optimierung

#### Added
- **`static/css/graph.css` (neu)**: Alle Stile für die Wissensgraph-Seite wurden in eine eigene CSS-Datei ausgelagert. Dies umfasst feste Layouts für Header, Toolbar, Wiki-Switcher, Suche, Tag-Filter, Canvas-Container, Zoom-Controls, Stats-Overlay und das Knoten-Detail-Panel.
- **Emoji- & Icon-Sizing**: Feste Größen und Layout-Regeln für alle SVGs und Emojis, um übergroße Symbole und UI-Verschiebungen zu verhindern.

#### Changed
- **`templates/base.html`**: `{% block head %}` hinzugefügt, damit einzelne Seiten spezifische Stylesheets vor dem Body laden können.
- **`templates/graph.html`**: Komplett bereinigt von Tailwind-Utility-Klassen und inline-Style-Anweisungen. Nutzt nun die semantischen Klassen aus `graph.css`.
- **`static/js/graph.js`**: Element-Klasseninteraktionen angepasst, um die Zustände (`is-visible`, `is-active`, `is-hidden`) der neuen `graph.css` statt inline/Tailwind-Klassen zu steuern.

---

## [2.4.5] – 2026-07-17


### Knowledge Graph – vollständig überarbeitete Seite

#### Added
- **Wiki-Switcher im Graph**: Dropdown in der Graph-Toolbar erlaubt direkten Wiki-Wechsel, ohne die Seite zu verlassen. Die URL wird aktualisiert und der Graph für das neue Wiki geladen.
- **Knoten-Suche**: Neues Suchfeld in der Toolbar – tippt man einen Begriff, springt die Ansicht sofort zum passenden Knoten, markiert ihn und öffnet das Detail-Panel. `Escape` setzt die Suche zurück.
- **Tag-Filter-Leiste**: Unter der Toolbar erscheint automatisch eine Leiste mit allen im Wiki vorhandenen Tags als Pill-Buttons. Klick auf einen Tag filtert den Graph auf Seiten dieses Tags; „Alle" zeigt wieder den vollständigen Graphen.
- **Knoten-Detail-Panel**: Seitliches Slide-in-Panel nach Klick auf einen Knoten – zeigt Titel, Gruppe, Anzahl direkter Verbindungen und einen direkten „Seite öffnen"-Link.
- **Stats-Overlay**: Kleines transparentes Panel oben links zeigt laufend die Anzahl der Knoten, Kanten und – bei Selektion – den Namen des gewählten Knotens.
- **Zoom-Buttons**: Zwei Zoom-In/Zoom-Out-Buttons unten links im Canvas ermöglichen Zoomen per Mausklick (ergänzend zum Mausrad).
- **Vollbild-Modus**: Neuer Button öffnet den Graph-Container im Browser-Vollbild (`requestFullscreen`); Icon wechselt zwischen Expand/Compress; Layout passt sich automatisch an.
- **Aufklappbare Bedienungshinweise**: Der Instruktionsblock ist jetzt ein `<details>`-Element – standardmäßig zugeklappt, damit der Graph mehr Platz hat. Zwei neue Hinweise für Suche und Tag-Filter ergänzt.
- **Neue i18n-Schlüssel** (`de.json` / `en.json`): `wiki_select_label`, `search_placeholder`, `fullscreen_button`, `tag_filter_label`, `filter_label`, `filter_all`, `canvas_aria`, `stat_nodes`, `stat_edges`, `stat_selected`, `detail_connections`, `detail_open`, `zoom_in`, `zoom_out`, `double_click_hint_inline`, `instruction_search`, `instruction_tag`.

#### Changed
- **`templates/graph.html`**: Vollständig neu aufgebaut – Toolbar mit Wiki-Switcher, Suche, Reset, Fullscreen; Tag-Filter-Leiste; Stats-Overlay; Zoom-Controls; Knoten-Detail-Panel; Credit + Inline-Hinweis unter dem Canvas.
- **`static/js/graph.js`**: Modularisiert in `initWikiSwitcher()`, `initSearch()`, `initZoomButtons()`, `initFullscreen()`, `buildTagBar()`, `applyTagFilter()`, `openDetailPanel()`, `closeDetailPanel()`, `updateStatsOverlay()`; vollständige Node-/Edge-Listen (`_allNodes`, `_allEdges`) für clientseitige Filter ohne Netzwerk-Requests.

---

## [2.4.4] – 2026-07-17


### Performance: Lazy Loading im Graph & Index-Caching für große Wikis

#### Added
- **In-Memory-Cache (`services/cache.py`)**: Neues zentrales Cache-Modul `WikiCache` – thread-sicher (RLock), mit mtime-Fingerabdruck-Invalidierung aller `.md`-Dateien (nur `stat()`, kein Datei-Read). Globale Singleton-Instanz, kein externer Cache-Server nötig. TTL-Fallback (300 s) als Sicherheitsnetz.
- **Index-Caching (`services/wiki.py`)**: `get_all_wiki_pages()` ist jetzt gecacht. Bei 1.000 Seiten spart das ca. 500 ms Disk-I/O pro API-Request. Disk-Read-Logik ausgelagert in `_get_all_wiki_pages_uncached()`.
- **Graph-Caching (`services/graph.py`)**: `build_graph_data()` ist jetzt gecacht (Key `graph:<wiki>`). Neue Funktion `build_graph_data_paginated()` liefert paginierte Graph-Daten (Seiten à max. 1.000 Knoten, optional mit Tag-Filter).
- **Paginierter Graph-Endpunkt**: Neuer Route `GET /graph/data/paginated?wiki=&page=&page_size=&tag=` in `pages.py` sowie `GET /api/v1/wikis/{wiki}/graph/paginated` in `api.py`.
- **Cache-Admin-Endpunkte (`api.py`)**: `GET /api/v1/cache/stats` und `POST /api/v1/cache/clear` (jeweils nur für Admin-Keys) zur Überwachung und manuellen Invalidierung des In-Memory-Caches.
- **Lazy Loading im Knowledge Graph (Frontend)**: `graph.js` lädt die ersten 200 Knoten sofort (Graph ist sofort sichtbar), alle weiteren Seiten werden asynchron im Hintergrund nachgeladen. Ein Progress-Badge zeigt „X / Y Knoten geladen" an und blendet sich nach Abschluss aus.
- **Barnes-Hut Quadtree (`graph-engine.js`)**: Physik-Simulation wechselt bei mehr als 100 Knoten von O(n²) auf O(n log n) Barnes-Hut-Approximation (konfigurierbar via `barnesHutThreshold`). Massive Geschwindigkeitsverbesserung bei 500+ Knoten.
- **Viewport Culling (`graph-engine.js`)**: Knoten und Kanten außerhalb des sichtbaren Bereichs werden übersprungen – kein unnötiges Rendern bei großen Graphen und kleinem Zoom.
- **Level-of-Detail / LOD (`graph-engine.js`)**: Drei Render-Stufen je nach Zoom-Faktor: Voll (Labels + Rechtecke), Medium (Rechtecke ohne Labels), Ultra-LOD (einfache Punkte). Hält die FPS auch bei 1.000+ Knoten stabil.
- **Lazy-Render / Dirty-Flag (`graph-engine.js`)**: `requestAnimationFrame`-Schleife rendert nur noch, wenn Simulation aktiv, Interaktion stattfindet oder das `_dirty`-Flag gesetzt ist. Kein unnötiges Rendern im Ruhezustand.
- **Kanten-Batching (`graph-engine.js`)**: Gleichfarbige Standardkanten werden in einem einzigen `ctx.beginPath()`/`ctx.stroke()`-Block gezeichnet – deutlich weniger Canvas-State-Wechsel.
- **Fade-in für nachgeladene Knoten (`graph-engine.js`)**: Neu hinzugeladene Knoten (via `appendData()`) blenden sanft ein statt abrupt zu erscheinen.

#### Changed
- **Cache-Invalidierung nach Sync (`services/sync.py`)**: `do_sync()` invalidiert zu Beginn sofort die Cache-Einträge `pages:<wiki>` und `graph:<wiki>`, damit nach einem Sync keine veralteten Daten ausgeliefert werden.
- **`graph-engine.js`**: Neue öffentliche Methode `appendData(data)` zum inkrementellen Hinzufügen von Knoten und Kanten ohne Neustart der Simulation.

---

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
