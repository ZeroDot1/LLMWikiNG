"""LLMWikiNG – Page Versioning / History (date-based, no git required).

Stores versions of wiki pages in .history/<slug>/ directories.
Each version is a full-page snapshot with a UTC timestamp filename.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.config import wiki_path

MAX_VERSIONS = 30


def history_dir(wiki: str, slug: str) -> Path:
    d = wiki_path(wiki) / ".history" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_version(wiki: str, slug: str, content: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = history_dir(wiki, slug) / f"{ts}.md"
    target.write_text(content, encoding="utf-8")
    versions = sorted(history_dir(wiki, slug).glob("*.md"), reverse=True)
    for old in versions[MAX_VERSIONS:]:
        old.unlink(missing_ok=True)
    return target


def list_versions(wiki: str, slug: str) -> list[dict]:
    files = sorted(history_dir(wiki, slug).glob("*.md"), reverse=True)
    return [
        {
            "id": f.stem,
            "timestamp": f.stem,
            "size": f.stat().st_size,
        }
        for f in files
    ]


def get_version(wiki: str, slug: str, version_id: str) -> str | None:
    p = history_dir(wiki, slug) / f"{version_id}.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None
