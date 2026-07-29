"""LLMWikiNG – Editor-Helfer (OKF-Frontmatter-Sicherstellung).

Portiert aus editor.py.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

import yaml


def _compute_content_hash(text: str) -> str:
    """Berechnet einen SHA-256-Hash des Hauptinhalts (Body ohne Frontmatter)."""
    body = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)
    return hashlib.sha256(body.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def ensure_okf_frontmatter(content: str, title: str | None = None) -> str:
    """Stellt sicher, dass der Inhalt OKF-konformes YAML-Frontmatter mit type-Feld hat."""
    fm_match = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*\n", content, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        try:
            fm_data = yaml.safe_load(fm_text)
            if isinstance(fm_data, dict) and "type" in fm_data:
                return content  # Bereits OKF-konform
        except yaml.YAMLError:
            pass
        body = content[fm_match.end():]
    else:
        body = content

    today = date.today().isoformat()
    page_title = title or "Neue Seite"
    content_hash = _compute_content_hash(content)
    new_fm = (
        f"---\n"
        f"type: Concept\n"
        f'title: "{page_title}"\n'
        f'description: ""\n'
        f'resource: ""\n'
        f"tags: []\n"
        f"content_hash: {content_hash}\n"
        f"timestamp: {today}T00:00:00Z\n"
        f"---\n\n"
    )
    return new_fm + body.lstrip("\n")


def detect_conflict(wiki: str, slug: str, incoming_content: str) -> dict | None:
    """Prüft auf Bearbeitungskonflikt.
    
    Vergleicht den ``content_hash`` des letzten gespeicherten Frontmatters
    mit einem Hash des aktuellen Speicherstands. Bei Abweichung liegt ein
    Konflikt vor.
    
    Args:
        wiki: Wiki-Slug.
        slug: Seiten-Slug.
        incoming_content: Der neu eingehende Inhalt (mit Frontmatter).
    
    Returns:
        Dict mit Konflikt-Details oder None, wenn kein Konflikt.
    """
    from core.config import wiki_path as _wp
    from pathlib import Path as _P
    fp = _wp(wiki) / f"{slug}.md"
    if not fp.exists():
        return None
    current_text = fp.read_text(encoding="utf-8", errors="replace")
    incoming_hash = _compute_content_hash(incoming_content)
    fm = re.search(r"^---\s*\n(.*?)\n---", current_text, re.DOTALL)
    if not fm:
        return None
    for line in fm.group(1).split("\n"):
        if line.startswith("content_hash:"):
            stored_hash = line.split(":", 1)[1].strip().strip('"').strip("'")
            if stored_hash and stored_hash != incoming_hash:
                return {
                    "slug": slug,
                    "wiki": wiki,
                    "stored_hash": stored_hash,
                    "incoming_hash": incoming_hash,
                    "detail": "Seite wurde seit dem letzten Laden extern bearbeitet.",
                }
    return None
