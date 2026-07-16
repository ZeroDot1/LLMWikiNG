"""LLMWikiNG – Wiki-Analytik (Hubs, Sackgassen, Tags, Brücken).

Portiert aus llmWikiNG (get_wiki_analytics).
"""

from __future__ import annotations

import re

from core.config import WIKI_DIR, wiki_path
from services.wiki import get_all_wiki_pages, extract_links_from_content, SYSTEM_PAGES


def _parse_tags(line: str) -> list[str]:
    tags_line = line.split(":", 1)[1].strip()
    tags_line = tags_line.strip("[]").replace('"', '').replace("'", "")
    return [t.strip() for t in tags_line.split(",") if t.strip()]


def get_wiki_analytics(wiki: str = "main") -> dict:
    wiki_pages = get_all_wiki_pages(wiki)
    root = wiki_path(wiki)

    inbound_links = {page["slug"]: 0 for page in wiki_pages}
    outbound_count = {page["slug"]: 0 for page in wiki_pages}
    tag_counts: dict[str, int] = {}

    for page in wiki_pages:
        slug = page["slug"]
        filepath = root / f"{slug}.md"
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("tags:"):
                            for tag in _parse_tags(line):
                                tag_counts[tag] = tag_counts.get(tag, 0) + 1

                matches = extract_links_from_content(content)
                for t_slug in matches:
                    if t_slug in inbound_links:
                        inbound_links[t_slug] += 1
                        outbound_count[slug] += 1
            except Exception:
                pass

    hubs = []
    for page in wiki_pages:
        slug = page["slug"]
        count = inbound_links.get(slug, 0)
        if count > 0:
            hubs.append({"slug": slug, "title": page["title"], "links": count})
    hubs.sort(key=lambda x: x["links"], reverse=True)

    dead_ends = [page for page in wiki_pages if outbound_count.get(page["slug"], 0) == 0]
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    # Brücken-Seiten: verlinkte Nachbarn mit größter Tag-Vielfalt
    slug_tags: dict[str, set] = {}
    for page in wiki_pages:
        slug = page["slug"]
        slug_tags[slug] = set()
        filepath = root / f"{slug}.md"
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("tags:"):
                            slug_tags[slug] = set(_parse_tags(line))
            except Exception:
                pass

    bridges = []
    for page in wiki_pages:
        slug = page["slug"]
        filepath = root / f"{slug}.md"
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                matches = extract_links_from_content(content)
                seen_tags: set = set()
                for t_slug in matches:
                    if t_slug in slug_tags:
                        seen_tags.update(slug_tags[t_slug])
                if len(seen_tags) > 1:
                    bridges.append({
                        "slug": slug,
                        "title": page["title"],
                        "tags_count": len(seen_tags),
                        "connected_tags": sorted(list(seen_tags)),
                    })
            except Exception:
                pass
    bridges.sort(key=lambda x: x["tags_count"], reverse=True)

    return {
        "hubs": hubs[:8],
        "dead_ends": dead_ends[:8],
        "top_tags": top_tags,
        "bridges": bridges[:5],
    }
