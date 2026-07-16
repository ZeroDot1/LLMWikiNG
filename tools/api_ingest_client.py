#!/usr/bin/env python3
"""LLMWikiNG API Ingest Client.

Ermöglicht den schnellen, interaktiven Ingest von Dateien, URLs oder Texten
über die JSON-API in ein vom Nutzer ausgewähltes Wiki.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

# Konfigurations-Fallbacks
DEFAULT_SERVER = "http://localhost:8081/LLMWikiNG"
CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"


def load_config():
    """Lädt Zugangsdaten aus Umgebungsvariablen oder config.json."""
    config = {
        "server_url": os.environ.get("LLMWIKI_SERVER_URL", DEFAULT_SERVER),
        "api_key": os.environ.get("LLMWIKI_API_KEY", ""),
        "api_password": os.environ.get("LLMWIKI_API_PASSWORD", "")
    }
    
    # Versuche lokale config.json zu lesen (falls lokal ausgeführt)
    if not config["api_key"] and CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # Suche nach dem ersten aktiven API-Key in data/api_keys.json falls möglich
            keys_file = Path(__file__).resolve().parent.parent / "data" / "api_keys.json"
            if keys_file.exists():
                keys = json.loads(keys_file.read_text(encoding="utf-8"))
                active_keys = [k for k in keys if k.get("active", True)]
                if active_keys:
                    # Hinweis: Da wir den rohen Key nicht aus dem Hash rekonstruieren können,
                    # muss der User diesen einmalig eingeben oder als Env exportieren.
                    pass
        except Exception:
            pass
            
    return config


def make_api_request(url, method="GET", headers=None, data=None, is_multipart=False):
    """Führt eine HTTP-Anfrage an die API aus."""
    if headers is None:
        headers = {}
        
    req = urllib.request.Request(url, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
        
    try:
        if is_multipart:
            # Für Multipart (File Upload) müssen wir die Daten als bytes übergeben
            with urllib.request.urlopen(req, data=data, timeout=120) as response:
                return json.loads(response.read().decode('utf-8')), response.status
        else:
            # Normales JSON oder Urlencoded
            encoded_data = None
            if data:
                if isinstance(data, dict):
                    encoded_data = urllib.parse.urlencode(data).encode('utf-8')
                    req.add_header("Content-Type", "application/x-www-form-urlencoded")
                elif isinstance(data, str):
                    encoded_data = data.encode('utf-8')
                    req.add_header("Content-Type", "application/json")
                    
            with urllib.request.urlopen(req, data=encoded_data, timeout=120) as response:
                return json.loads(response.read().decode('utf-8')), response.status
    except urllib.error.HTTPError as e:
        try:
            err_detail = json.loads(e.read().decode('utf-8'))
            return err_detail, e.code
        except Exception:
            return {"detail": e.reason}, e.code
    except Exception as e:
        return {"detail": str(e)}, 500


def encode_multipart_formdata(fields, files):
    """Hilfsfunktion zum Encodieren von Multipart Formular-Daten ohne externe Libs."""
    boundary = b'Boundary-' + os.urandom(16)
    body = []
    
    for k, v in fields.items():
        body.append(b'--' + boundary)
        body.append(f'Content-Disposition: form-data; name="{k}"'.encode('utf-8'))
        body.append(b'')
        body.append(str(v).encode('utf-8'))
        
    for k, filename, file_bytes in files:
        body.append(b'--' + boundary)
        body.append(f'Content-Disposition: form-data; name="{k}"; filename="{filename}"'.encode('utf-8'))
        # Einfache MIME-Typ Bestimmung
        mime = "application/octet-stream"
        if filename.endswith(".txt"): mime = "text/plain"
        elif filename.endswith(".md"): mime = "text/markdown"
        body.append(f'Content-Type: {mime}'.encode('utf-8'))
        body.append(b'')
        body.append(file_bytes)
        
    body.append(b'--' + boundary + b'--')
    body.append(b'')
    
    return boundary, b'\r\n'.join(body)


def main():
    print("=" * 60)
    print("  🚀 LLMWikiNG API Ingest Client")
    print("=" * 60)
    
    config = load_config()
    
    # 1. API-Key Setup checken
    if not config["api_key"]:
        print("  ⚠ Kein API-Key in Umgebungsvariablen gefunden (LLMWIKI_API_KEY).")
        config["api_key"] = input("  Bitte gib deinen API-Key ein: ").strip()
        if not config["api_key"]:
            print("  ❌ API-Key ist erforderlich. Abbruch.")
            sys.exit(1)
            
    # 2. Server-URL checken
    server_input = input(f"  Server-URL [{config['server_url']}]: ").strip()
    if server_input:
        config["server_url"] = server_input.rstrip("/")
        
    headers = {
        "X-API-Key": config["api_key"]
    }
    if config["api_password"]:
        headers["X-API-Password"] = config["api_password"]
        
    # 3. Wikis abrufen
    print("\n  🔍 Lade Liste der verfügbaren Wikis...")
    wikis_data, status = make_api_request(f"{config['server_url']}/api/v1/wikis", headers=headers)
    
    if status != 200:
        print(f"  ❌ Fehler beim Laden der Wikis (Status {status}): {wikis_data.get('detail', 'Unbekannt')}")
        # Falls Passwort gefordert wird
        if status == 401 and "password" in str(wikis_data).lower():
            config["api_password"] = input("  API verlangt Passwort. Bitte eingeben: ").strip()
            headers["X-API-Password"] = config["api_password"]
            wikis_data, status = make_api_request(f"{config['server_url']}/api/v1/wikis", headers=headers)
            if status != 200:
                print("  ❌ Erneuter Login-Fehler. Abbruch.")
                sys.exit(1)
        else:
            sys.exit(1)
            
    wikis = wikis_data.get("wikis", [])
    if not wikis:
        print("  ❌ Keine Wikis auf dem Server vorhanden.")
        sys.exit(1)
        
    # 4. Wiki auswählen lassen
    print("  Verfügbare Wikis:")
    for idx, w in enumerate(wikis, 1):
        print(f"    [{idx}] {w['name']} ({w.get('description', 'Keine Beschreibung')})")
        
    wiki_choice = input(f"  Bitte wähle ein Wiki aus [1-{len(wikis)}]: ").strip()
    try:
        wiki_idx = int(wiki_choice) - 1
        if wiki_idx < 0 or wiki_idx >= len(wikis):
            raise ValueError()
        selected_wiki = wikis[wiki_idx]["name"]
    except ValueError:
        print("  ⚠ Ungültige Auswahl. Nutze Standard-Wiki 'main'.")
        selected_wiki = "main"
        
    print(f"  👉 Ausgewähltes Wiki: {selected_wiki}")
    
    # 5. Aktion wählen (Ingest oder Suche)
    print("\n  Was möchtest du tun?")
    print("    [1] Inhalt Ingestieren (Datei, URL oder Text)")
    print("    [2] Volltextsuche im Wiki ausführen")
    
    action_choice = input("  Auswahl [1-2]: ").strip()
    
    if action_choice == "2":
        # Volltextsuche
        query = input("\n  Suchbegriff eingeben: ").strip()
        if not query:
            print("  ❌ Suchbegriff darf nicht leer sein. Abbruch.")
            sys.exit(1)
            
        print(f"  🔍 Suche nach '{query}' in Wiki '{selected_wiki}'...")
        search_url = f"{config['server_url']}/api/v1/search?q={urllib.parse.quote(query)}&wiki={selected_wiki}"
        res, status = make_api_request(search_url, method="GET", headers=headers)
        
        if status == 200:
            results = res.get("results", [])
            print(f"\n  Found {len(results)} Result(s):")
            print("=" * 60)
            for idx, r in enumerate(results, 1):
                print(f"  [{idx}] {r.get('title')} (Score: {r.get('score')})")
                print(f"      Pfad: {r.get('path')}")
                full_view_url = config["server_url"].replace("/LLMWikiNG", "") + r.get("url")
                print(f"      Link: {full_view_url}")
                # HTML-Entities im Snippet säubern
                snippet = r.get("snippet", "")
                snippet = snippet.replace("<mark class=\"search-highlight\">", "\033[1;33m").replace("</mark>", "\033[0m")
                print(f"      Snippet: {snippet[:300]}...")
                print("-" * 60)
        else:
            print(f"  ❌ Fehler bei der Suche (Status {status}): {res.get('detail')}")
        sys.exit(0)

    # 6. Ingest-Typ wählen
    print("\n  Was möchtest du ingestieren?")
    print("    [1] Lokale Datei (Markdown, Text, Dokument, Bild)")
    print("    [2] Web-URL")
    print("    [3] Reinen Text eingeben (Paste)")
    
    type_choice = input("  Auswahl [1-3]: ").strip()
    
    fields = {}
    files_to_upload = []
    
    title = input("  Titel für die Wiki-Seite (optional): ").strip()
    if title:
        fields["title"] = title
        
    if type_choice == "1":
        filepath_str = input("  Pfad zur lokalen Datei: ").strip()
        filepath = Path(filepath_str)
        if not filepath.exists() or not filepath.is_file():
            print(f"  ❌ Datei '{filepath_str}' existiert nicht. Abbruch.")
            sys.exit(1)
        try:
            file_bytes = filepath.read_bytes()
            files_to_upload.append(("file", filepath.name, file_bytes))
            print(f"  📁 Datei geladen: {filepath.name} ({len(file_bytes)} Bytes)")
        except Exception as e:
            print(f"  ❌ Fehler beim Lesen der Datei: {e}")
            sys.exit(1)
            
    elif type_choice == "2":
        url = input("  URL zum Ingestieren: ").strip()
        if not url.startswith(("http://", "https://")):
            print("  ❌ Ungültige URL. Abbruch.")
            sys.exit(1)
        fields["url"] = url
        
    elif type_choice == "3":
        print("  Gib deinen Text ein (Strg+D / Strg+Z + Enter zum Beenden):")
        text_lines = []
        try:
            for line in sys.stdin:
                text_lines.append(line)
        except KeyboardInterrupt:
            pass
        text_content = "".join(text_lines)
        if not text_content.strip():
            print("  ❌ Kein Text eingegeben. Abbruch.")
            sys.exit(1)
        fields["text"] = text_content
        
    else:
        print("  ❌ Ungültige Ingest-Auswahl. Abbruch.")
        sys.exit(1)
        
    # 7. Ingest abschicken
    print(f"\n  🚀 Sende Ingest-Request an Wiki '{selected_wiki}'...")
    
    ingest_url = f"{config['server_url']}/wiki/{selected_wiki}/api/ingest"
    
    # Wenn wir eine Datei hochladen, nutzen wir multipart
    if files_to_upload:
        boundary, post_data = encode_multipart_formdata(fields, files_to_upload)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary.decode('utf-8')}"
        is_multipart = True
    else:
        post_data = fields
        is_multipart = False
        
    res, status = make_api_request(ingest_url, method="POST", headers=headers, data=post_data, is_multipart=is_multipart)
    
    # 8. Ergebnis anzeigen
    if status == 200 and res.get("ok"):
        print("\n  ✅ Ingest erfolgreich abgeschlossen!")
        print(f"    Wiki: {res.get('wiki')}")
        print(f"    Verarbeitet: {', '.join(res.get('processed', []))}")
        
        view_urls = res.get("view_urls", [])
        if view_urls:
            print("\n  🔗 Neue Wiki-Seite(n) direkt ansehen:")
            for vu in view_urls:
                # Baue absolute URL zum Browser
                full_view_url = config["server_url"].replace("/LLMWikiNG", "") + vu
                print(f"    👉 {full_view_url}")
        else:
            print("  (Keine neuen Seiten generiert, eventuell im Hintergrund verarbeitet)")
    else:
        print(f"\n  ❌ Fehler beim Ingest (Status {status}):")
        print(f"    {res.get('detail') or res.get('errors') or res}")


if __name__ == "__main__":
    main()
