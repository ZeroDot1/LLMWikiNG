"""LLMWikiNG – Safe Path Helpers.

Prevents Path-Traversal attacks by validating that wiki roots and file paths
remain strictly within allowed directory bounds.
"""

from __future__ import annotations

import re
from pathlib import Path
from core.config import WIKIS_ROOT, slugify_wiki


class UnsafePathError(ValueError):
    """Raised when a path leaves allowed root boundaries or contains path traversal."""
    pass


def safe_wiki_root(wiki: str) -> Path:
    """Returns resolved wiki root directory, guaranteed to be inside WIKIS_ROOT."""
    from core.config import WIKIS_ROOT, wiki_path
    root = wiki_path(wiki).resolve()
    base = WIKIS_ROOT.resolve()
    if not str(root).startswith(str(base)):
        raise UnsafePathError(f"Ungültiger Wiki-Pfad: {wiki}")
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_page_path(wiki: str, slug: str) -> Path:
    """Returns resolved markdown page path under wiki root without path traversal."""
    root = safe_wiki_root(wiki)
    clean_slug = re.sub(r"\.md$", "", slug.strip())
    if ".." in clean_slug.split("/") or ".." in clean_slug.split("\\"):
        raise UnsafePathError(f"Path-Traversal blockiert: {slug}")
    safe_name = slugify_wiki(clean_slug.replace("/", "-"))
    if not safe_name or safe_name in ("index", "log", "ingestlater"):
        raise UnsafePathError(f"Ungültiger Seiten-Slug: {slug}")
    if len(safe_name) > 120:
        raise UnsafePathError(f"Seiten-Slug zu lang (max. 120 Zeichen): {slug}")
    path = (root / f"{safe_name}.md").resolve()
    if not str(path).startswith(str(root)):
        raise UnsafePathError(f"Path-Traversal blockiert: {slug}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
