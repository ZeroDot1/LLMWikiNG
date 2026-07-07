# LLMWikiNG (OKF Edition)

Ein vollständiges Pattern zum Aufbau und zur Pflege einer persönlichen Wissensdatenbank (Wiki) nach dem standardisierten [Open Knowledge Format (OKF) v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) (entwickelt von Google Cloud) mithilfe von lokalen LLMs und Agenten. Inspiriert durch das LLM-Wiki-Pattern von Andrej Karpathy.

**Autor:** ZeroDot1

*Ein großes Dankeschön an [tevsa](https://github.com/tevsa) für die großartige Idee und Unterstützung!*

Statt Dokumente bei jeder Abfrage ad-hoc per RAG (Retrieval-Augmented Generation) neu zu durchsuchen und Wissen jedes Mal von Grund auf neu zu generieren, kompiliert dieses System Informationen **einmalig** in ein strukturiertes, querverlinktes Markdown-Wiki. Bei neuen Quellen aktualisiert das LLM bestehende Seiten, zieht Querverweise und dokumentiert Widersprüche. Das Wissen wächst und verfeinert sich kontinuierlich.

---

## 🏗️ Architektur

Das Projekt basiert auf drei Ebenen:

1. **Rohquellen (`raw/`)**: Unveränderliche Originaldokumente (Artikel, PDFs, Notizen), die als Informationsbasis dienen.
2. **Das Wiki (`wiki/`)**: Eine Sammlung vom LLM gepflegter, untereinander verlinkter Markdown-Dateien mit einem zentralen Index (`index.md`) und einem chronologischen Log (`log.md`).
3. **Die CLI & Konfiguration**: Das Steuerungsskript `wiki.sh` und die Agentenkonfiguration `.agy.yaml` definieren die Arbeitsweise und Regeln für den LLM-Agenten.

---

## 🛠️ Funktionen & Befehle (`wiki.sh`)

Das CLI-Skript `wiki.sh` bündelt alle Operationen zur Verwaltung des Wikis:

*   `./wiki.sh init` – Initialisiert die Ordnerstruktur und legt die `index.md` sowie `log.md` an. Erstellt zudem eine `qmd`-Such-Collection.
*   `./wiki.sh ingest <quelldatei>` – Liest eine neue Quelle ein, archiviert sie in `raw/`, generiert eine KI-Zusammenfassung, erstellt/aktualisiert die Wiki-Seite, verlinkt sie im Index und trägt sie im Log ein.
*   `./wiki.sh search "<suchbegriff>"` – Führt eine token-sparende Hybrid-Suche (BM25 + Vektor) via `qmd` durch (JSON-Ausgabe für Agenten).
*   `./wiki.sh lint` – Führt einen Gesundheitscheck durch (sucht verwaiste Seiten, fehlende Verlinkungen, unvollständige Seiten).
*   `./wiki.sh sync` – Aktualisiert die Such-Embeddings für die lokale Suche und baut den Index neu.
*   `./wiki.sh export <seite>` – Exportiert eine Seite zur Weitergabe nach `output_docs/`.
*   `./wiki.sh list` – Listet alle aktuellen Wiki-Seiten auf.
*   `./wiki.sh status` – Zeigt Statistiken zum Wiki, den Rohquellen und dem LLM-Backend an.
*   `./wiki.sh config` – Zeigt die aktuelle Konfiguration an.
*   `./wiki.sh update` – Führt ein Selbstupdate via GitHub durch (`git fetch origin && git reset --hard origin/main`).
*   `./wiki.sh reindex` – Baut den BM25-Suchindex neu auf.
*   `./wiki.sh help` – Zeigt die Hilfe-Seite mit allen Befehlen an.
*   `./wiki.sh --version` – Gibt die aktuelle Versionsnummer aus.

---

## 🌐 Web-Interface (`llmWiki.py`)

Zusätzlich zur CLI bietet das Projekt ein voll ausgestattetes, extrem performantes Web-Interface im modernen **Tokyo-Night/Newsroom-Design**:

*   **🏠 Dashboard & Navigation**: Übersicht über alle aktuellen Wiki-Seiten, Statistiken und den Systemzustand.
*   **✍️ Universeller Editor (WYSIWYG & Markdown)**: Integrierter Dual-Mode-Editor zum Erstellen und Bearbeiten von Wiki-Seiten und Rohquellen direkt im Browser – mit WYSIWYG-Formatierung (Fett, Kursiv, Listen, Zitate, Code, Links, Bilder) und rohem Markdown-Quellcode-Modus inklusive YAML-Frontmatter.
*   **🕸️ Interaktiver Wissensgraph**: Visualisiert alle Beziehungen deiner Seiten in einem farbcodierten, dynamischen 2D-Netzwerk (offline betrieben über `vis-network.min.js`). Widersprüche/Konflikte werden rot-gestrichelt dargestellt.
*   **📰 Wochenberichte & E-Mail-Briefings**: Aggregiere wöchentliche Änderungen, generiere neue Briefing-Dateien im Wiki und versende diese sicher über den integrierten SMTP-Client an deine Empfänger. Die Konfiguration erfolgt über die Weboberfläche (gespeichert in `config.json`) mit integrierten Schnell-Presets für **Gmail**, **ProtonMail Bridge** und **Mail.ru**.
*   **⏳ Ausstehender Ingest**: Zeigt un-ingestierte Dateien in `raw/` an und ermöglicht das Einspielen einzeln oder als Stapel („Ingest All“) über die Web-Oberfläche.
*   **📥 Web-Ingest & Später einspielen**: Komfortabler Upload und Text-Paste, sowie das Merken von URLs und Notizen in `ingestlater.md`.
*   **📤 Export-Verwaltung**: Sieh alle exportierten Dokumente im Browser ein, lies sie gerendert oder lade sie direkt herunter.
*   **🔍 Suche mit Term-Highlighting**: Blitzschnelle BM25-Suche im gesamten Wiki, in den Rohdateien sowie den Exporten mit farblichen Markierungen im Text.
*   **🏥 Web-Linter**: Zeigt verwaiste Seiten, veraltete Seiten (Staleness), defekte Rohquellen-Referenzen (Raw File Refs) und offene Link-Verweise sortiert nach ihrer Wichtigkeit (Häufigkeit) an.
*   **⬇️ Selbstupdate**: Integrierte Update-Funktion – prüft auf neue GitHub-Versionen und aktualisiert sich selbst per Klick. Schützt Wiki-Seiten, Rohquellen und Konfiguration.
*   **⚙️ Einstellungen (Settings)**: Zentrale Konfigurationsseite mit Tabs für Sprachauswahl, SMTP-E-Mail-Konfiguration, Gesundheitscheck und Update-Funktion.

### Web-Interface starten:
Der Webserver läuft standardmäßig auf einem modernen **Uvicorn ASGI-Server** (Standard post-2026 für maximale Performance und Konkurrenzfähigkeit).

Starte den Server einfach über das Starter-Skript:
```bash
./start.sh
```
*   *Entwicklungsmodus mit Live-Reload:* `./start.sh -d`
*   *Spezifischer Port:* `./start.sh 9090`
*   *Startsprache festlegen:* `./start.sh --lang en`

Öffne danach `http://localhost:8081` (oder den zugewiesenen Port) in deinem Browser.

### Server-Parameter

Der Webserver (`llmWiki.py`) kann direkt oder via `start.sh` mit folgenden Parametern gestartet werden:

| Parameter | Via start.sh | Beschreibung |
|-----------|--------------|-------------|
| `--port, -p PORT` | `./start.sh 9090` | Port (Standard: 8080). `start.sh` sucht automatisch den nächsten freien Port. |
| `--host, -H HOST` | — (immer `0.0.0.0`) | Binde-Adresse (Standard: `0.0.0.0`) |
| `--debug, -d` | `./start.sh -d` | Debug-Modus (Flask-interner Server statt Uvicorn, Live-Reload) |
| `--lang, -l CODE` | `./start.sh --lang en` | Startsprache (z. B. `de`, `en`). Überschreibt den Wert aus `config.json`. |
| `--reset` | `./start.sh --reset` | **Server zurücksetzen:** Löscht unwiderruflich alle Wiki-Seiten, Rohquellen und Exporte. Setzt das Wiki auf den Werkszustand zurück. |
| `--reset -y` | `./start.sh --reset -y` | Reset non-interaktiv (ohne Nachfrage) ausführen. |

Alle Parameter können auch direkt an `llmWiki.py` übergeben werden:
```bash
python3 llmWiki.py --port 9090 --lang en -d
```

Die Standard-Sprache wird in `config.json` unter dem Schlüssel `"language"` gespeichert:
```json
{
  "language": "de"
}
```
Wird kein `--lang`-Parameter übergeben, verwendet der Server den Wert aus `config.json`. Fehlt auch dort die Angabe, wird Deutsch (`de`) als Fallback genutzt.

### 🌐 Web-Endpunkte (Routen)
Das Web-Interface stellt folgende Routen bereit:

*   `/` – Cockpit (Startseite) mit allen Artikeln, Pfaden, Zeitstrahlen und der Aktivitäts-Timeline.
*   `/wiki/<page_name>` – Gerenderte Markdown-Ansicht einer Wiki-Seite mit Backlink-Vorschau und Trail-Navigation.
*   `/wiki/<page_name>/export` – Kopiert den Wiki-Beitrag nach `output_docs/`.
*   `/wiki/<page_name>/delete` – Löscht die Seite und bereinigt den Suchindex.
*   `/admin/clear-log` – Leert das Aktivitätslogbuch.
*   `/search` – BM25-Volltextsuche in Wiki-Seiten, Rohquellen und Exporten mit Treffer-Hervorhebung.
*   `/lint` – Linter-Übersicht (verwaiste, fehlende und veraltete Seiten).
*   `/status` – Dashboard mit Tool-Verfügbarkeit, Konfiguration und Brücken-Seiten-Analytik.
*   `/briefings` – Wochenberichte generieren und per E-Mail versenden.
*   `/config` – Sichere SMTP-Konfiguration (gespeichert in `config.json`).
*   `/ingest` – Ingest-Center für Uploads, URL-Notizen (Merkzettel) und Stapelverarbeitung.
*   `/ingest/all` – Ingest aller ausstehenden Rohdateien in `raw/` durchführen.
*   `/admin/sync` – Stößt eine manuelle Index-Synchronisation an.
*   `/settings` – ⚙️ Einstellungen (Sprache, SMTP-Konfiguration, Gesundheitscheck, Update).
*   `/admin/update/check` – Prüft auf neue GitHub-Versionen (JSON-API für AJAX).
*   `/graph` – Interaktiver Wissensgraph (vis-network) aller Wiki-Seiten-Verknüpfungen.
*   `/graph/data` – Liefert die Graph-Daten als JSON.
*   `/pending` – Zeigt ausstehende Ingests aus dem Merkzettel an.
*   `/export` – Verwaltung aller exportierten Dokumente.
*   `/export/<filename>` – Lädt ein exportiertes Dokument herunter.
*   `/raw` – Übersicht aller archivierten Rohquellen.
*   `/raw/<filename>` – Zeigt eine Rohquelle an.
*   `/edit` – ✍️ Universeller Editor (WYSIWYG & Markdown-Dualmodus für Wiki-Seiten und Rohquellen).
*   `/about` – Über-Seite mit Version und Projektinformationen.

### ✍️ Integrierter Editor
Der Webserver besitzt einen integrierten, zweigeteilten Editor:
*   **WYSIWYG-Modus**: Ermöglicht komfortables Schreiben mit direkter visueller Formatierung (Fett, Kursiv, Listen, Zitate, Trennlinien, Links, Bilder, inline-Code) komplett ohne externe JS-Bibliotheken (reines HTML5 ContentEditable).
*   **Markdown-Modus**: Bietet die Möglichkeit, den Markdown-Quelltext inklusive YAML-Frontmatter direkt zu bearbeiten.
*   **Ordner-Weiche**: Der Editor lädt und speichert Dateien automatisch im passenden Verzeichnis (entweder `wiki/` für aktive Seiten oder `raw/` für Entwürfe), basierend auf dem aktuellen Modus.

---

## 🚀 Erste Schritte

### 1. Voraussetzungen installieren
Stelle sicher, dass die folgenden Tools auf deinem System installiert sind:
*   `bash`, `ripgrep` (`rg`), `jq`
*   [qmd](https://github.com/tobi/qmd) (für die lokale Hybrid-Suche)
*   [Ollama](https://ollama.com/) (für lokale Zusammenfassungen, standardmäßig mit `llama3.2:3b`)

### 2. Wiki initialisieren
Führe im Projektverzeichnis folgenden Befehl aus:
```bash
chmod +x wiki.sh
./wiki.sh init
```

### 3. Eine Quelle hinzufügen (Ingest)
```bash
./wiki.sh ingest pfad/zu/deiner/notiz.md
```

### 4. Server & Workspace zurücksetzen (Werkszustand)
Um das gesamte Wiki in den Auslieferungszustand zurückzusetzen und alle persönlichen Seiten, Rohdaten sowie Exporte unwiderruflich zu löschen:

**Via CLI (wiki.sh):**
```bash
./wiki.sh reset              # Erfordert die manuelle Eingabe von 'RESET' zur Bestätigung
./wiki.sh reset --yes        # Führt das Zurücksetzen non-interaktiv (ohne Nachfrage) durch
```

**Via Server-Starter (start.sh):**
```bash
./start.sh --reset           # Erfordert die manuelle Eingabe von 'RESET' zur Bestätigung
./start.sh --reset -y        # Führt das Zurücksetzen non-interaktiv (ohne Nachfrage) durch
```

Der Reset löscht alle Dateien in `wiki/`, `raw/` und `output_docs/` und legt `index.md` sowie `log.md` OKF-konform neu an. Die qmd-Such-Collection wird ebenfalls zurückgesetzt.

---

## ⚙️ Konfiguration

Die Einstellungen des LLM-Backends können über Umgebungsvariablen gesteuert oder direkt in der Konfiguration `.agy.yaml` hinterlegt werden:

```bash
# Beispiel: Anderes Modell oder Backend verwenden
LLM_BACKEND=ollama OLLAMA_MODEL=llama3:8b ./wiki.sh ingest datei.md
```

*   `LLM_BACKEND`: `ollama`, `agy` oder `opencode` (Standard: `ollama`)
*   `OLLAMA_MODEL`: Das zu verwendende Modell (Standard: `llama3.2:3b`)

### 📦 Selbstupdate

Das Projekt enthält eine integrierte Update-Funktion:

```bash
./update.sh            # Vollständiges Selbstupdate von GitHub
./update.sh --check    # Nur prüfen, ob ein Update verfügbar ist
./wiki.sh update       # Update via CLI
```

Das Update-Skript (Git-basiert):
- Erstellt ein **automatisches Backup** vor dem Update
- Führt `git fetch origin` aus und setzt auf `origin/main` zurück (`git reset --hard`)
- Stasht lokale Änderungen automatisch (bei Bedarf: `git stash pop`)
- Schützt **Wiki-Seiten (`wiki/`), Rohquellen (`raw/`), Exporte (`output_docs/`), SMTP-Konfiguration (`config.json`) und LLM-Einstellungen (`.agy.yaml`)**
- Zeigt den gesamten Update-Verlauf im Log an

---

## ⚖️ Lizenz (License)

Dieses Projekt wurde von **ZeroDot1** erstellt und ist unter der **Unlicense** veröffentlicht, wodurch es vollständig gemeinfrei (Public Domain) ist. Du kannst den Code kopieren, verändern, verbreiten und kommerziell nutzen, ohne irgendwelche Bedingungen erfüllen zu müssen.

Ein besonderer Dank geht an [tevsa](https://github.com/tevsa) für die großartige Idee und Unterstützung bei der Realisierung dieses Projekts. Weitere Details findest du in der [LICENSE](LICENSE)-Datei.

### Drittanbieter-Komponenten / Third-Party Components

#### vis-network (Wissensgraph)
Dieses Projekt verwendet [vis-network](https://visjs.github.io/vis-network/) v10.1.0, eine dynamische, browser-basierte Visualisierungsbibliothek für den interaktiven Wissensgraphen.

- **Copyright**: (c) 2011–2017 Almende B.V, http://almende.com · (c) 2017–2019 visjs contributors, https://github.com/visjs
- **Lizenz**: Dual-lizenziert unter Apache 2.0 (http://www.apache.org/licenses/LICENSE-2.0) und MIT (http://opensource.org/licenses/MIT). Vis.js darf unter einer der beiden Lizenzen verteilt werden.
