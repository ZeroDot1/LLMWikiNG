#!/usr/bin/env python3
"""
OKF v0.1-Migrationstool für LLMWikiNG.
Konvertiert alle Wiki-Markdown-Dateien in das OKF-Format:
- Fügt fehlendes YAML-Frontmatter mit type-Feld hinzu
- Konvertiert [[WikiLinks]] in Standard-Markdown-Links
- Normalisiert created → timestamp, source → resource
- Überspringt reservierte Dateien (index.md, log.md)
"""
import os
import re
import sys
import yaml
from datetime import datetime, date
from pathlib import Path

# Projektstamm ermitteln (relativ zum Skript oder aus Umgebungsvariable)
SCRIPT_DIR = Path(__file__).resolve().parent.parent
WIKI_DIR = Path(os.environ.get("LLMWIKI_WIKI_DIR", SCRIPT_DIR / "wiki"))
RESERVED_FILES = {"index.md", "log.md"}


def convert_links(content: str, bundle_relative: bool = True) -> str:
    """Konvertiert [[seite.md]] → Bundle-relative Markdown-Links [Titel](/seite.md)."""
    def repl(match):
        link = match.group(1).strip()
        # Dateiendung normalisieren
        if not link.endswith(".md"):
            link += ".md"
        display_name = link.replace(".md", "").replace("-", " ").title()
        if bundle_relative:
            return f"[{display_name}](/{link})"
        return f"[{display_name}]({link})"
    return re.sub(r"\[\[(.*?)\]\]", repl, content)


def ensure_okf_frontmatter(text: str, filename: str) -> str:
    """Stellt OKF-konformes Frontmatter mit type-Feld sicher.
    Ergänzt fehlende Felder. Überspringt reservierte Dateien.
    """
    if filename in RESERVED_FILES:
        return text

    lines = text.splitlines()
    has_frontmatter = lines and lines[0].strip() == "---"

    if has_frontmatter:
        try:
            end_idx = lines.index("---", 1)
        except ValueError:
            has_frontmatter = False
            body = text
        else:
            fm_text = "\n".join(lines[1:end_idx])
            body = "\n".join(lines[end_idx + 1:])
            try:
                fm = yaml.safe_load(fm_text) or {}
            except yaml.YAMLError:
                fm = {}
    else:
        fm = {}
        body = text

    changed = False

    # type-Feld ergänzen (Pflicht)
    if 'type' not in fm:
        fm['type'] = 'Concept'
        changed = True

    # title ergänzen falls fehlend
    if 'title' not in fm:
        fm['title'] = filename.replace(".md", "").replace("-", " ").title()
        changed = True

    # description ergänzen
    if 'description' not in fm:
        fm['description'] = ""
        changed = True

    # created → timestamp normalisieren
    if 'created' in fm and 'timestamp' not in fm:
        fm['timestamp'] = f"{fm['created']}T00:00:00Z"
        del fm['created']
        changed = True

    # source → resource normalisieren
    if 'source' in fm and 'resource' not in fm:
        fm['resource'] = f"file://raw/{fm['source']}"
        del fm['source']
        changed = True

    # timestamp ergänzen falls ganz fehlend
    if 'timestamp' not in fm:
        today = date.today().isoformat()
        fm['timestamp'] = f"{today}T00:00:00Z"
        changed = True

    # Links im Body konvertieren
    new_body = convert_links(body, bundle_relative=True)
    if new_body != body:
        changed = True

    if changed:
        new_fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        return f"---\n{new_fm_text}\n---\n\n{new_body}"
    return text


def migrate_file(filepath: Path) -> bool:
    """Migriert eine einzelne Datei ins OKF-Format. Gibt True zurück wenn geändert."""
    filename = filepath.name
    if filename in RESERVED_FILES:
        return False

    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Fehler beim Lesen von {filepath}: {e}")
        return False

    new_text = ensure_okf_frontmatter(text, filename)
    if new_text != text:
        filepath.write_text(new_text, encoding="utf-8")
        print(f"✅ Migriert: {filepath}")
        return True

    return False


def main():
    print("=" * 60)
    print("  OKF v0.1 Migration – LLMWikiNG")
    print("=" * 60)
    print(f"  Wiki-Verzeichnis: {WIKI_DIR}")
    print(f"  Übersprungene Dateien: {', '.join(sorted(RESERVED_FILES))}")
    print()

    if not WIKI_DIR.exists():
        print(f"❌ Wiki-Verzeichnis nicht gefunden: {WIKI_DIR}")
        sys.exit(1)

    count = 0
    for md_file in sorted(WIKI_DIR.glob("*.md")):
        if migrate_file(md_file):
            count += 1

    print()
    if count > 0:
        print(f"✅ {count} Datei(en) migriert.")
    else:
        print("ℹ️  Alle Dateien bereits OKF-konform – keine Änderungen nötig.")


if __name__ == "__main__":
    main()
