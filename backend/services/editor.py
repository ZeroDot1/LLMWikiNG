"""LLMWikiNG – Editor-Helfer (OKF-Frontmatter-Sicherstellung).

Portiert aus editor.py.
"""

from __future__ import annotations

import re
from datetime import date

import yaml


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
    new_fm = (
        f"---\n"
        f"type: Concept\n"
        f'title: "{page_title}"\n'
        f'description: ""\n'
        f'resource: ""\n'
        f"tags: []\n"
        f"timestamp: {today}T00:00:00Z\n"
        f"---\n\n"
    )
    return new_fm + body.lstrip("\n")
