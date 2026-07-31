#!/usr/bin/env python3
"""Cleanup: löscht ~188 duplizierte Raw-Dateien auf dem Remote-Server via REST API.

Nach Ausführung des Updates (commit 10ef3e4) auf dem Remote-Server
stehen DELETE /api/v1/raw/{filename} und POST /api/v1/raw/delete zur Verfügung.

Dieses Skript:
  1. Listet alle Raw-Dateien via GET /api/v1/raw
  2. Identifiziert Duplikate (date-prefixed Varianten)
  3. Löscht sie via POST /api/v1/raw/delete (Batch)

Nutzt den bekannten API-Key: llmw_6pezWzHUlKrR4IK7aZ1U2mt6o_wJZUz1kLoPOj3K2e8
"""

import json
import re
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE_URL = "http://192.168.2.247:44419/LLMWikiNG/api/v1"
API_KEY = "llmw_6pezWzHUlKrR4IK7aZ1U2mt6o_wJZUz1kLoPOj3K2e8"
HEADERS = {
    "X-API-Key": API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")


def api_get(path):
    url = f"{BASE_URL}{path}"
    req = Request(url, headers=HEADERS, method="GET")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def api_post(path, data):
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode()
    req = Request(url, data=body, headers=HEADERS, method="POST")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def is_duplicate(filename):
    """Erkennt Duplikat-Dateinamen mit wiederholten Datums-Präfixen.
    
    Die Originals haben KEIN Datums-Präfix.
    Duplikate haben 1+ Datums-Präfixe: YYYY-MM-DD-originalname.md
    """
    basename = filename.split("/")[-1]
    # Prüfe ob der Dateiname mit einem Datum beginnt
    if DATE_PREFIX.match(basename):
        # Entferne Datums-Präfix und prüfe, ob der Rest auch ein Datum hat
        rest = DATE_PREFIX.sub("", basename)
        # Alles mit Datums-Präfix ist ein Duplikat
        return True
    return False


def main():
    print("=" * 60)
    print("Raw-Datei Cleanup: 192.168.2.247")
    print("=" * 60)

    # Step 1: Liste alle Raw-Dateien
    print("\n[1/3] Liste Raw-Dateien...")
    try:
        data = api_get("/raw")
    except HTTPError as e:
        body = e.read().decode()
        print(f"  FEHLER: HTTP {e.code} - {body}")
        if e.code == 404:
            print("  → Der /raw-Endpunkt existiert nicht. Wurde das Update installiert?")
        sys.exit(1)
    except URLError as e:
        print(f"  FEHLER: {e.reason}")
        sys.exit(1)

    all_files = data.get("raw_files", [])
    print(f"  {len(all_files)} Dateien gefunden.")

    # Step 2: Identifiziere Duplikate
    print("\n[2/3] Identifiziere Duplikate...")
    # Gruppiere nach Basisname (ohne Datums-Präfix)
    groups = {}
    for f in all_files:
        basename = f.split("/")[-1]
        # Entferne ALLE Datums-Präfixe
        short = basename
        while DATE_PREFIX.match(short):
            short = DATE_PREFIX.sub("", short, count=1)
        if short not in groups:
            groups[short] = []
        groups[short].append(f)

    keep = {}  # short → original filename
    duplicates = {}
    for short, files in sorted(groups.items()):
        # Unterscheide: Datei OHNE Datums-Präfix = Original
        originals = [f for f in files if not DATE_PREFIX.match(f.split("/")[-1])]
        dupes = [f for f in files if DATE_PREFIX.match(f.split("/")[-1])]
        if originals:
            keep[short] = originals[0]
        if dupes:
            duplicates[short] = {"originals": originals, "dupes": dupes}

    print(f"  Einzigartige Basis-Dateien: {len(groups)}")
    print(f"  Davon mit Original(en):     {len(keep)}")
    print(f"  Davon mit Duplikaten:       {len(duplicates)}")

    all_dupes = []
    for short, info in sorted(duplicates.items()):
        all_dupes.extend(info["dupes"])
        orig = info["originals"][0] if info["originals"] else "(kein Original)"
        print(f"  {short}: {len(info['dupes'])} Duplikat(e) (Original: {orig})")

    print(f"\n  → {len(all_dupes)} Duplikat-Dateien zur Löschung markiert.")

    if not all_dupes:
        print("\n  Keine Duplikate gefunden. Nichts zu tun.")
        return

    # Step 3: Lösche Duplikate (Batch)
    print(f"\n[3/3] Lösche {len(all_dupes)} Duplikate...")

    # Batch-Löschung (empfohlen)
    try:
        result = api_post("/raw/delete", {"filenames": all_dupes})
        deleted = result.get("deleted", [])
        errors = result.get("errors", [])
        print(f"  Gelöscht: {len(deleted)}")
        if errors:
            print(f"  Fehler: {len(errors)}")
            for e in errors[:10]:
                print(f"    - {e}")
            if len(errors) > 10:
                print(f"    ... und {len(errors) - 10} weitere")
    except HTTPError as e:
        body = e.read().decode()
        print(f"  FEHLER bei Batch-Löschung: HTTP {e.code} - {body}")
        print(f"  → Versuche Einzellöschungen...")
        # Fallback: Einzellöschungen
        deleted = 0
        errors = []
        for f in all_dupes:
            try:
                url = f"{BASE_URL}/raw/{f}"
                req = Request(url, headers=HEADERS, method="DELETE")
                with urlopen(req, timeout=10) as resp:
                    deleted += 1
                    if deleted % 20 == 0:
                        print(f"    {deleted}/{len(all_dupes)} gelöscht...")
            except HTTPError as e2:
                errors.append(f"{f}: {e2.code}")
            except URLError as e2:
                errors.append(f"{f}: {e2.reason}")
        print(f"  Gelöscht (Einzelfallback): {deleted}")
        if errors:
            print(f"  Fehler: {len(errors)}")
            for e in errors[:5]:
                print(f"    - {e}")

    print("\n" + "=" * 60)
    print("Cleanup abgeschlossen!")
    print("=" * 60)

    # Zusammenfassung
    remaining = api_get("/raw") if len(all_dupes) > 0 else data
    remaining_count = len(remaining.get("raw_files", []))
    print(f"\nVerbleibende Raw-Dateien: {remaining_count}")
    print(f"Entfernt: {len(all_dupes) - remaining_count}")


if __name__ == "__main__":
    main()
