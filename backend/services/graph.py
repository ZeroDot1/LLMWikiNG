"""LLMWikiNG – Wissensgraph-Daten für vis.js.

Portiert aus llmWiki.py. Jetzt mit In-Memory-Cache:
- build_graph_data() cached das komplette Graph-Dict pro Wiki.
- Invalidierung via mtime-Fingerabdruck des Wiki-Verzeichnisses.
- Separate paginated API für große Wikis (>500 Knoten).
"""

from __future__ import annotations

import re

from core.config import WIKI_DIR, BASE_PATH, wiki_path, list_wikis
from services.wiki import get_all_wiki_pages
from services.cache import get_cache


def build_graph_data(wiki: str = "main") -> dict:
    """Liefert Knoten und Kanten des Wikis für vis.js.

    Ergebnis wird in-memory gecached. Cache wird bei Datei-Änderungen
    automatisch invalidiert (mtime-basiert).
    """
    cache = get_cache()
    root = wiki_path(wiki)
    cache_key = f"graph:{wiki}"

    cached = cache.get(cache_key, root)
    if cached is not None:
        return cached

    result = _build_graph_uncached(wiki)
    cache.set(cache_key, result, root)
    return result


def build_graph_data_paginated(
    wiki: str = "main",
    page: int = 0,
    page_size: int = 200,
    tag_filter: str | None = None,
) -> dict:
    """Gibt einen paginierten Ausschnitt des Graphen zurück.

    Für große Wikis (>500 Knoten) kann das Frontend schrittweise
    nachladen. Gibt immer alle Kanten zurück, aber nur die Knoten
    des aktuellen Segments (damit Kanten-Rendering korrekt bleibt).

    Args:
        wiki: Wiki-Name.
        page: Null-basierter Seitenindex.
        page_size: Anzahl Knoten pro Seite.
        tag_filter: Wenn gesetzt, nur Knoten mit diesem Tag.

    Returns:
        Dict mit ``nodes``, ``edges``, ``total_nodes``, ``page``,
        ``page_size``, ``total_pages``.
    """
    if wiki == "__all__":
        full = build_graph_data_all()
    else:
        full = build_graph_data(wiki)
    all_nodes: list[dict] = full["nodes"]
    all_edges: list[dict] = full["edges"]

    # Optionaler Tag-Filter
    if tag_filter:
        prefix = f"tag-{tag_filter.lower()}"
        all_nodes = [n for n in all_nodes if n.get("group", "").startswith(prefix)]
        visible_ids = {n["id"] for n in all_nodes}
        all_edges = [e for e in all_edges if e["from"] in visible_ids or e["to"] in visible_ids]

    total = len(all_nodes)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_nodes = all_nodes[start : start + page_size]

    # Nur Kanten zurückgeben, bei denen mindestens ein Endpunkt in der
    # aktuellen Seite liegt (sonst sehr viele irrelevante Kanten)
    page_ids = {n["id"] for n in page_nodes}
    page_edges = [e for e in all_edges if e["from"] in page_ids or e["to"] in page_ids]

    return {
        "nodes": page_nodes,
        "edges": page_edges,
        "total_nodes": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def _build_graph_uncached(wiki: str) -> dict:
    """Interne Funktion – baut Graph-Daten ohne Cache."""
    nodes: list[dict] = []
    edges: list[dict] = []
    page_tags: dict[str, list[str]] = {}

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
                            page_tags[slug] = tags
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

    # Tag-basierte Kanten hinzufügen (Verknüpfung von Seiten mit gemeinsamen Tags)
    existing_edges = {(e["from"], e["to"]) for e in edges}
    existing_edges.update({(e["to"], e["from"]) for e in edges})

    for i in range(len(wiki_pages)):
        for j in range(i + 1, len(wiki_pages)):
            slug1 = wiki_pages[i]["slug"]
            slug2 = wiki_pages[j]["slug"]
            tags1 = page_tags.get(slug1, [])
            tags2 = page_tags.get(slug2, [])
            shared_tags = set(tags1).intersection(tags2)
            if shared_tags and (slug1, slug2) not in existing_edges and (slug2, slug1) not in existing_edges:
                edges.append({
                    "from": slug1,
                    "to": slug2,
                    "color": "#a0c0f0",
                    "dashes": True,
                    "title": f"Gemeinsame Tags: {', '.join(shared_tags)}"
                })
                existing_edges.add((slug1, slug2))

    return {"nodes": nodes, "edges": edges}


def build_graph_data_all() -> dict:
    """Kombinierter Graph über ALLE Wikis.

    Node-IDs werden mit dem Wiki-Slug praefixiert (``wiki::slug``), damit
    es keine Kollisionen zwischen verschiedenen Wikis gibt.
    Die URL zeigt weiterhin auf das korrekte Wiki.
    """
    cache = get_cache()
    cache_key = "graph:__all__"
    # Kein einzelnes root für Cache-Invalidierung – wir geben None
    cached = cache.get(cache_key, None)
    if cached is not None:
        return cached

    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    known_ids: set[str] = set()

    for w in list_wikis():
        wiki_name = w["name"]
        wiki_slug = w["slug"]

        try:
            full = _build_graph_uncached(wiki_name)
        except Exception:
            continue

        # Prefix nodes with wiki slug
        for n in full.get("nodes", []):
            orig_id = n["id"]
            prefixed = f"{wiki_slug}::{orig_id}"
            n["id"] = prefixed
            n["wiki"] = wiki_name
            n["original_id"] = orig_id
            # Update URL to keep it working
            if orig_id in n.get("url", ""):
                n["url"] = f"{BASE_PATH}/wiki/{wiki_name}/{orig_id}"
            all_nodes.append(n)
            known_ids.add(prefixed)

        # Prefix edges
        for e in full.get("edges", []):
            e["from"] = f"{wiki_slug}::{e['from']}" if e.get("from") else e.get("from")
            e["to"] = f"{wiki_slug}::{e['to']}" if e.get("to") else e.get("to")
            all_edges.append(e)

    result = {"nodes": all_nodes, "edges": all_edges}
    cache.set(cache_key, result, None)
    return result
