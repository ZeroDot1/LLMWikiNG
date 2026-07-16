"""LLMWikiNG – Markdown-Rendering mit OKF-Wikilink-Erweiterung.

Portiert aus llmWiki.py: transformiert lokale Markdown-Links zu /wiki/<slug>
und markiert fehlende Ziele als 'wikilink-missing'.
"""

from __future__ import annotations

import os
import re

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from core.config import WIKI_DIR, BASE_PATH, wiki_path

MD_EXTENSIONS = [
    "extra",
    "codehilite",
    "sane_lists",
    "smarty",
    "toc",
    "fenced_code",
]


class OKFLinkTreeprocessor(Treeprocessor):
    def __init__(self, md, page_cache, page_name=None, wiki="main"):
        super().__init__(md)
        self.page_cache = page_cache
        self.page_name = page_name
        self.wiki = wiki

    def run(self, root):
        parent_slug = ""
        if self.page_name:
            parts = self.page_name.split("/")
            if len(parts) > 1:
                parent_slug = "/".join(parts[:-1])

        for el in root.iter("a"):
            href = el.get("href", "")
            if href.startswith(("http://", "https://", "mailto:", "#")):
                continue

            if not href.startswith("/") and parent_slug:
                resolved_path = f"{parent_slug}/{href}"
            else:
                resolved_path = href

            clean_href = resolved_path.lstrip("/")
            clean_href = re.sub(r"\.md$", "", clean_href)
            clean_href = os.path.normpath(clean_href)
            slug = clean_href.lower().replace("\\", "/").replace(" ", "-").replace("_", "-")

            exists = slug in self.page_cache
            css_class = "wikilink" if exists else "wikilink-missing"

            el.set("href", f"{BASE_PATH}/wiki/{self.wiki}/{slug}")
            el.set("class", css_class)
        return root


class LLMWikiLinkExtension(Extension):
    """Wandelt lokale Markdown-Links um und prüft ihre Existenz."""

    def __init__(self, page_name=None, wiki="main"):
        super().__init__()
        self.page_name = page_name
        self.wiki = wiki

    def extendMarkdown(self, md):
        page_cache = set()
        root = wiki_path(self.wiki)
        if root.exists():
            for f in root.rglob("*.md"):
                if f.stem not in ("index", "log", "ingestlater"):
                    rel_path = f.relative_to(root)
                    slug = str(rel_path.with_suffix("")).lower().replace("\\", "/").replace(" ", "-").replace("_", "-")
                    page_cache.add(slug)
        md.treeprocessors.register(OKFLinkTreeprocessor(md, page_cache, self.page_name, self.wiki), "okf_links", 15)


def render_markdown(text: str, page_name: str | None = None, wiki: str = "main") -> str:
    """Wandelt Markdown in HTML um, mit angepassten Wikilinks."""
    text = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"\*\*Quelle:\*\*\s*`([^`]+)`", r"**Quelle:** [\1](/raw/\1)", text)

    ext = LLMWikiLinkExtension(page_name, wiki)

    html = markdown.markdown(
        text,
        extensions=MD_EXTENSIONS + [ext],
        extension_configs={
            "toc": {
                "marker": "[TOC]",
                "permalink": True,
            },
        },
    )

    html = re.sub(r"<p>\s*</p>", "", html)
    return html


def render_markdown_preview(text: str) -> str:
    """Vorschau-Rendering ohne Wikilink-Umschreibung (für Editor-Preview)."""
    text = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)
    return markdown.markdown(
        text,
        extensions=["toc", "tables", "fenced_code", "codehilite"],
        extension_configs={
            "toc": {
                "marker": "[TOC]",
                "permalink": True,
            },
        },
    )
