# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Editor-Helfer (OKF-Frontmatter-Sicherstellung).

Portiert aus editor.py.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone

import yaml


def _compute_content_hash(text: str) -> str:
    """Berechnet einen SHA-256-Hash des Hauptinhalts (Body ohne Frontmatter)."""
    body = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)
    return hashlib.sha256(body.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def update_content_hash(content: str, updated_by: str = "web") -> str:
    """Aktualisiert ``content_hash``, ``updated`` und ``updated_by`` in
    existierendem Frontmatter, ohne andere Felder zu verändern.

    Wird bei jedem Speichern einer bestehenden OKF-Seite aufgerufen, damit
    Conflict-Detection beim nächsten Laden korrekte Hashes vorfindet.

    Args:
        content: Vollständiger Seiteninhalt mit Frontmatter.
        updated_by: Quelle der Änderung (``"web"``, ``"mcp"``, ``"cli"``).
    """
    fm_match = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*\n", content, re.DOTALL)
    if not fm_match:
        return content

    fm_text = fm_match.group(1)
    fm_data = yaml.safe_load(fm_text) or {}

    fm_data["content_hash"] = _compute_content_hash(content)
    fm_data["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fm_data["updated_by"] = updated_by

    new_fm = yaml.dump(fm_data, sort_keys=False, allow_unicode=True)
    body = content[fm_match.end():]
    return f"---\n{new_fm}---\n{body}"


def ensure_okf_frontmatter(content: str, title: str | None = None, tags: list[str] | None = None, updated_by: str = "web") -> str:
    """Stellt sicher, dass der Inhalt OKF-konformes YAML-Frontmatter mit type-Feld hat."""
    fm_match = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*\n", content, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        try:
            fm_data = yaml.safe_load(fm_text)
            if isinstance(fm_data, dict) and "type" in fm_data:
                return update_content_hash(content, updated_by=updated_by)
        except yaml.YAMLError:
            pass
        body = content[fm_match.end():]
    else:
        body = content

    today = date.today().isoformat()
    page_title = title or "Neue Seite"
    content_hash = _compute_content_hash(content)
    
    if not tags:
        from services.tags import extract_tags, auto_generate_tags_for_content
        tags = extract_tags(content)
        if not tags:
            tags = auto_generate_tags_for_content(content, title=page_title)

    tags_str = ", ".join(f'"{t}"' for t in tags) if tags else ""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_fm = (
        f"---\n"
        f"type: Concept\n"
        f'title: "{page_title}"\n'
        f'description: ""\n'
        f'resource: ""\n'
        f"tags: [{tags_str}]\n"
        f"content_hash: {content_hash}\n"
        f"timestamp: {today}T00:00:00Z\n"
        f"updated: {now_iso}\n"
        f"updated_by: {updated_by}\n"
        f"---\n\n"
    )
    return new_fm + body.lstrip("\n")


def detect_conflict(wiki: str, slug: str, incoming_content: str, client_loaded_hash: str | None = None) -> dict | None:
    """Prüft auf Bearbeitungskonflikt.
    
    Vergleicht den ``client_loaded_hash`` (den Hash den der Client beim Laden
    gesehen hat) mit dem aktuell gespeicherten ``content_hash`` im Frontmatter auf Disk.
    Wenn kein ``client_loaded_hash`` übergeben wird oder dieser übereinstimmt, liegt kein Konflikt vor.
    
    Args:
        wiki: Wiki-Slug.
        slug: Seiten-Slug.
        incoming_content: Der neu eingehende Inhalt (mit Frontmatter).
        client_loaded_hash: Hash des Inhalts zum Zeitpunkt des Ladens.
    
    Returns:
        Dict mit Konflikt-Details oder None, wenn kein Konflikt.
    """
    if not client_loaded_hash:
        return None

    from core.config import wiki_path as _wp
    fp = _wp(wiki) / f"{slug}.md"
    if not fp.exists():
        return None
    current_text = fp.read_text(encoding="utf-8", errors="replace")
    fm = re.search(r"^---\s*\n(.*?)\n---", current_text, re.DOTALL)
    if not fm:
        return None
    for line in fm.group(1).split("\n"):
        if line.startswith("content_hash:"):
            stored_hash = line.split(":", 1)[1].strip().strip('"').strip("'")
            if stored_hash and stored_hash != client_loaded_hash:
                return {
                    "slug": slug,
                    "wiki": wiki,
                    "stored_hash": stored_hash,
                    "client_hash": client_loaded_hash,
                    "detail": "Seite wurde seit dem letzten Laden extern bearbeitet.",
                }
    return None
