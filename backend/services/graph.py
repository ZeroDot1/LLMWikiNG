"""LLMWikiNG – Wissensgraph-Daten für vis.js.

Portiert aus llmWiki.py.
"""

from __future__ import annotations

import re

from core.config import WIKI_DIR, BASE_PATH, wiki_path
from services.wiki import get_all_wiki_pages


def build_graph_data(wiki: str = "main") -> dict:
    """Liefert Knoten und Kanten des Wikis für vis.js."""
    nodes: list[dict] = []
    edges: list[dict] = []

    wiki_pages = get_all_wiki_pages(wiki)
    wiki_slugs = {page["slug"]: page["title"] for page in wiki_pages}
    root = wiki_path(wiki)

    for page in wiki_pages:
        slug = page["slug"]
        title = page["title"]

        group = "page"
        tags: list[str] = []

        filepath = root / f"{slug}.md"
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("tags:"):
                            t_line = line.split(":", 1)[1].strip()
                            t_line = t_line.strip("[]").replace('"', '').replace("'", "")
                            tags = [t.strip() for t in t_line.split(",") if t.strip()]
                        elif line.startswith("source:"):
                            group = "source"

                seen = set()
                for m in re.finditer(r"\[.*?\]\((/.*?\.md|\./.*?\.md|.*?\.md|[^#:\s\)]+)\)", content):
                    clean_target = re.sub(r"^\.+/", "", m.group(1))
                    target = clean_target.lstrip("/").replace(".md", "")
                    t_slug = target.lower().replace(" ", "-").replace("_", "-")

                    line_start = content.rfind("\n", 0, m.start()) + 1
                    line_end = content.find("\n", m.start())
                    if line_end == -1:
                        line_end = len(content)
                    line_content = content[line_start:line_end].lower()

                    is_contradiction = any(
                        w in line_content for w in ("contradict", "widerspricht", "widerspruch", "tension", "spannung")
                    )

                    if t_slug in wiki_slugs and t_slug != slug:
                        if t_slug not in seen:
                            seen.add(t_slug)
                            edge = {"from": slug, "to": t_slug}
                            if is_contradiction:
                                edge["color"] = "#f56c6c"
                                edge["dashes"] = True
                                edge["title"] = "Widerspruch / Tension"
                            edges.append(edge)
            except Exception:
                pass

        if slug in ("index", "log", "ingestlater"):
            group = "system"
        elif tags:
            group = f"tag-{tags[0]}"

        nodes.append({"id": slug, "label": title, "group": group, "url": f"{BASE_PATH}/wiki/{wiki}/{slug}"})

    return {"nodes": nodes, "edges": edges}
