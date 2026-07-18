---
name: llmwiki-api
description: Interaktive Fernbedienung zur Steuerung der LLMWikiNG-API. Enthält alle API-Endpunkte, OKF-Richtlinien und anpassbare Konfigurationsvariablen.
---

# LLMWikiNG API-Fernbedienung

Dieses Dokument dient als direkte Fernbedienung zur Steuerung der LLMWikiNG-Plattform. **Passe die Werte im folgenden Konfigurationsblock an**, um die cURL-Befehle direkt kopieren und ausführen zu können.

---

## ⚙️ 1. Konfiguration (Vom Nutzer anpassbar)

Verwende diese Variablen in deinen Skripten oder passe sie hier direkt an:

```bash
# Basis-URL des Servers (z.B. Port 8080 oder 8081, oder externe Domain)
SERVER_URL="http://localhost:8081/LLMWikiNG"

# API-Key (erzeugt unter /settings -> API-Schlüssel)
API_KEY="llmw_dein_api_key_hier"

# Optionales Passwort (NUR nötig, wenn 'require_password' für diesen Key in der WebUI erzwungen wird. Ansonsten leer lassen!)
API_PASSWORD=""

# Ziel-Wiki (Da es mehrere Wikis gibt, z. B. 'main', 'wiki1', 'wiki2'. Jedes Wiki hat seine eigene Ordnerstruktur unter wikis/)
WIKI_NAME="main"
```

---

## 📦 2. Open Knowledge Format (OKF v0.1) Richtlinien

Wenn du Seiten via API erstellst oder aktualisierst, muss der Inhalt folgende Struktur aufweisen:

### YAML-Frontmatter (Pflicht):
```yaml
---
type: Concept         # Typ: Concept, Playbook, Reference, Table, Dataset
title: "Titel der Seite"
description: "Kurze Beschreibung des Inhalts"
resource: "file://raw/original_quelle.md" # Referenz auf Originaldatei
tags: [tag1, tag2]
timestamp: 2026-07-14T21:44:00Z
---
# Titel der Seite
Inhalt im Standard-Markdown...
```

*   **Verlinkungen:** Verwende nur native Markdown-Links: `[Link-Text](/concepts/ziel-seite.md)`. Obsidian-Wikilinks (`[[Ziel]]`) sind unzulässig.

---

## 🎛️ 3. API-Endpunkte (Die Fernbedienung)

Ersetze in den Beispielen die Variablen `$SERVER_URL`, `$API_KEY`, `$API_PASSWORD` und `$WIKI_NAME` durch deine oben konfigurierten Werte.

> [!NOTE]
> **API-Passwort Header:** Falls für deinen API-Key **kein** Passwort erzwungen wird, kannst du die Zeile `-H "X-API-Password: $API_PASSWORD"` in allen cURL-Befehlen einfach weglassen.

### A. Direktes Wiki-Management (Multi-Wiki Support)

#### 1. Direkter Ingest (Datei, URL oder Text in spezifisches Wiki hochladen & sofort verarbeiten)
Lädt Daten hoch und führt direkt das LLM-Ingest-Skript für dieses spezifische Wiki aus.

**a) Datei-Upload:**
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "X-API-Password: $API_PASSWORD" \
  -F "file=@/pfad/zu/deiner/datei.md" \
  -F "title=Optionale Dateibezeichnung" \
  "$SERVER_URL/wiki/$WIKI_NAME/api/ingest"
```

**b) URL-Ingest (Lädt URL herunter, konvertiert in Markdown und ingestiert):**
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "X-API-Password: $API_PASSWORD" \
  -F "url=https://example.com/artikellink" \
  -F "title=Mein URL Ingest" \
  "$SERVER_URL/wiki/$WIKI_NAME/api/ingest"
```

**c) Reiner Text-Ingest (Text-Paste):**
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "X-API-Password: $API_PASSWORD" \
  -F "text=# Überschrift\nInhalt des kopierten Texts..." \
  -F "title=Text-Paste-Titel" \
  "$SERVER_URL/wiki/$WIKI_NAME/api/ingest"
```

#### 2. Direktes Syncen
Synchronisiert Vektor-Embeddings und den Suchindex des Wikis.
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "X-API-Password: $API_PASSWORD" \
  "$SERVER_URL/wiki/$WIKI_NAME/api/sync"
```

---

### B. Standard API v1 (Daten-Routen)

#### 3. Wikis auflisten
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/wikis"
```

#### 4. Alle Seiten eines Wikis auflisten
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/wikis/$WIKI_NAME/pages"
```

#### 5. Inhalt einer Wiki-Seite abrufen
```bash
# Beispiel für Seite 'llm-wiki'
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/wikis/$WIKI_NAME/pages/llm-wiki"
```

#### 6. Neue Seite anlegen (Erfordert Scope: write)
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"slug": "test-seite", "content": "---\ntype: Concept\ntitle: Test-Seite\ntimestamp: 2026-07-14T21:44:00Z\n---\n# Test-Seite\nInhalt hier."}' \
  "$SERVER_URL/api/v1/wikis/$WIKI_NAME/pages"
```

#### 7. Seite exportieren
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  "$SERVER_URL/api/v1/wikis/$WIKI_NAME/pages/llm-wiki/export"
```

#### 8. Rohdatei ins Archiv hochladen (ohne sofortige Ingest-Verarbeitung)
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  -F "file=@/pfad/zu/raw_datei.txt" \
  "$SERVER_URL/api/v1/wikis/$WIKI_NAME/ingest"
```

#### 9. Ausstehende Ingests anzeigen
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/wikis/$WIKI_NAME/pending"
```

#### 10. Ausstehende Ingests verarbeiten (Startet Hintergrundprozess)
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  "$SERVER_URL/api/v1/wikis/$WIKI_NAME/ingest/process"
```

#### 11. Volltextsuche (Unterstützt Cross-Wiki-Suche via wiki=all)
```bash
# Suche in einem bestimmten Wiki:
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/search?q=Suchbegriff&wiki=$WIKI_NAME"

# Cross-Wiki-Suche (alle Wikis durchsuchen):
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/search?q=Suchbegriff&wiki=all"
```

#### 12. Wissensgraph-Daten abrufen (Gesamter Graph)
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/wikis/$WIKI_NAME/graph"
```

#### 13. Wissensgraph-Daten paginiert abrufen (Für große Wikis)
```bash
# Holt Seite 0 mit max. 200 Knoten, optional gefiltert nach einem Tag
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/wikis/$WIKI_NAME/graph/paginated?page=0&page_size=200&tag=Concept"
```

#### 14. Wiki-Statistiken abrufen
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/wikis/$WIKI_NAME/stats"
```

#### 15. Linter ausführen
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/wikis/$WIKI_NAME/lint"
```

---

### C. System-, Admin- & Cache-Routen (Nur für Admin-Keys)

#### 16. Server-Status abrufen
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/status"
```

#### 17. Systemstatus & Traffic abrufen
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/system/status"
```

#### 18. Alle Wikis synchronisieren
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  "$SERVER_URL/api/v1/system/sync"
```

#### 19. Audit-Logs abrufen (Admin-API-Key erforderlich)
```bash
# Neueste 50 Einträge abrufen:
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/system/audit"

# Mit Filtern (action, username, start_date, end_date):
curl -H "X-API-Key: $API_KEY" \
  "$SERVER_URL/api/v1/system/audit?action=login_failed&limit=100"

# Zeitraum-Filter:
curl -H "X-API-Key: $API_KEY" \
  "$SERVER_URL/api/v1/system/audit?start_date=2026-07-01&end_date=2026-07-31"
```

Query-Parameter:
- `limit` (default: 50) – Maximale Anzahl Einträge
- `offset` (default: 0) – Pagination-Offset
- `action` – Filter auf Aktionstyp (z.B. `login`, `login_failed`, `page_delete`, `search`, `ingest`)
- `category` – Filter auf Kategorie (z.B. `auth`, `pages`, `search`, `ingest`, `system`)
- `username` – Filter auf bestimmten Benutzernamen
- `start_date` – Startzeit (ISO-Format: `YYYY-MM-DD`)
- `end_date` – Endzeit (ISO-Format: `YYYY-MM-DD`)
- `search` – Volltextsuche in Details, Username, IP und Aktion

#### 20. Update-Verfügbarkeit prüfen (Admin-API-Key erforderlich)
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/system/update/check"
```
Antwort:
```json
{
  "ok": true,
  "local_version": "2.11.0",
  "remote_version": "2.12.0",
  "update_available": true,
  "up_to_date": false
}
```

#### 21. Update ausführen (Admin-API-Key erforderlich)
```bash
curl -X POST -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/system/update/run"
```
Antwort:
```json
{
  "ok": true,
  "old_version": "2.11.0",
  "new_version": "2.12.0",
  "updated": true,
  "output": "... Update-Log ..."
}
```
**Hinweis:** Das Update-Skript sichert Benutzerdaten, führt `git reset --hard origin/main` aus und installiert Python-Abhängigkeiten. Timeout: 300 Sekunden.

#### 22. Cache-Statistiken abrufen
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/cache/stats"
```

#### 23. In-Memory Cache leeren
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  "$SERVER_URL/api/v1/cache/clear"
```

#### 24. Benutzer auflisten
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/users"
```

#### 25. Neuen Benutzer anlegen
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"username": "neuer_nutzer", "password": "sicheres_passwort", "role": "editor"}' \
  "$SERVER_URL/api/v1/users"
```

#### 26. Benutzer löschen
```bash
# Ersetze USER_ID durch die ID aus der Benutzerliste
curl -X DELETE \
  -H "X-API-Key: $API_KEY" \
  "$SERVER_URL/api/v1/users/USER_ID"
```

#### 27. API-Keys auflisten
```bash
curl -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/api-keys"
```

#### 28. Neuen API-Key generieren
```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Mein Skript Key", "require_password": true, "scopes": ["read", "write"]}' \
  "$SERVER_URL/api/v1/api-keys"
```

#### 29. API-Key löschen/widerrufen
```bash
# Ersetze KEY_ID durch die ID aus der API-Key-Liste
curl -X DELETE \
  -H "X-API-Key: $API_KEY" \
  "$SERVER_URL/api/v1/api-keys/KEY_ID"
```

---

## 💻 4. Interaktiver CLI Ingest-Client (`tools/api_ingest_client.py`)

Für die komfortable Interaktion aus der Konsole steht das Skript `tools/api_ingest_client.py` bereit. Es fungiert als Fernbedienung mit automatischer Wiki-Auswahl:

### Ablauf:
1.  **Starten:** `./tools/api_ingest_client.py`
2.  **Wiki-Auswahl:** Das Skript ruft via API die Liste aller verfügbaren Wikis ab. Gib die Nummer deines gewünschten Wikis ein.
3.  **Aktion wählen:**
    - `[1]` Inhalt Ingestieren (Datei, URL oder Text)
    - `[2]` Volltextsuche im Wiki ausführen
4.  **Bei Ingest:** Wähle den Typ (Datei, URL, Text) und gib den Inhalt an. Du erhältst direkt einen **klickbaren Link** zur neuen Seite.
5.  **Bei Suche:** Gib deinen Suchbegriff ein. Die Treffer werden direkt im Terminal mit Score, Pfad, Link und farblich hervorgehobenem Textausschnitt (Snippet) ausgegeben.

### Konfiguration (Umgebungsvariablen):
Du kannst die Zugangsdaten direkt in deine Shell exportieren, damit das Skript ohne Nachfragen läuft:
```bash
export LLMWIKI_API_KEY="llmw_dein_schluessel"
export LLMWIKI_SERVER_URL="http://localhost:8081/LLMWikiNG"
export LLMWIKI_API_PASSWORD="optionales_passwort"
```
