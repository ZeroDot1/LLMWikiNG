# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Lint / Gesundheitscheck des Wikis.

Portiert aus llmWiki.py (lint_dashboard + settings health check). Liefert
eine strukturierte Ergebnismenge, die sowohl in /lint als auch in /settings
angezeigt wird.
"""

from __future__ import annotations

import re

from core.config import WIKI_DIR, RAW_DIR, wiki_path
from services.wiki import (
    get_all_wiki_pages,
    extract_links_from_content,
    SYSTEM_PAGES,
)


def run_lint(wiki: str = "main") -> dict:
    orphans: list[dict] = []
    missing_pages: list[dict] = []
    stale_pages: list[dict] = []
    missing_raw_files: list[dict] = []
    changed_raw_sources: list[dict] = []
    missing_type: list[dict] = []
    broken_links: list[dict] = []
    no_tags: list[dict] = []
    short_pages: list[dict] = []
    link_suggestions: list[dict] = []
    issue_count = 0

    root = wiki_path(wiki)
    if not root.exists():
        return {
            "orphans": orphans,
            "missing": missing_pages,
            "stale": stale_pages,
            "missing_raw": missing_raw_files,
            "changed_sources": changed_raw_sources,
            "missing_type": missing_type,
            "broken_links": broken_links,
            "no_tags": no_tags,
            "short_pages": short_pages,
            "link_suggestions": link_suggestions,
            "issue_count": issue_count,
        }

    pages = get_all_wiki_pages(wiki)
    all_slugs = {p["slug"] for p in pages}
    contents: dict[str, str] = {}
    for page in pages:
        try:
            contents[page["slug"]] = (root / f"{page['slug']}.md").read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            continue

    # 1. Orphans (keine Rückverweise).  Build the backlink set once instead
    # of rescanning every page for every candidate orphan.
    backlinks: set[str] = set()
    for source in pages:
        try:
            for target in extract_links_from_content(contents.get(source["slug"], "")):
                if target != source["slug"]:
                    backlinks.add(target)
        except OSError:
            continue

    for p in pages:
        if p["slug"] in SYSTEM_PAGES:
            continue
        if p["slug"] not in backlinks:
            orphans.append(p)
            issue_count += 1

    # 2. Fehlende verlinkte Seiten
    missing_map: dict[str, dict] = {}
    for p in pages:
        try:
            content = contents[p["slug"]]
            refs = extract_links_from_content(content)
            for target_slug in refs:
                if target_slug and target_slug not in all_slugs and target_slug not in SYSTEM_PAGES:
                    if target_slug not in missing_map:
                        missing_map[target_slug] = {
                            "title": target_slug.replace("-", " ").title(),
                            "sources": set(),
                        }
                    missing_map[target_slug]["sources"].add((p["title"], p["slug"]))
        except KeyError:
            continue

    for ref_slug, info in missing_map.items():
        sources_list = sorted(list(info["sources"]))
        missing_pages.append({
            "slug": ref_slug,
            "title": info["title"],
            "sources": sources_list,
            "count": len(sources_list),
        })
        issue_count += 1

    # 3. Veraltete Seiten (Top 5 älteste)
    for p in pages:
        if p["slug"] in SYSTEM_PAGES:
            continue
        file_path = root / f"{p['slug']}.md"
        if file_path.exists():
            try:
                from datetime import datetime, timezone

                stat = file_path.stat()
                stale_pages.append({
                    "slug": p["slug"],
                    "title": p["title"],
                    "mtime_formatted": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
                    "mtime": stat.st_mtime,
                })
            except OSError:
                continue
    stale_pages.sort(key=lambda x: x["mtime"])
    stale_pages = stale_pages[:5]

    # 4. Fehlende Rohquellen
    for p in pages:
        try:
            content = contents[p["slug"]]
            raw_matches = re.findall(r"\*\*Quelle:\*\*\s*`([^`]+)`", content)
            for raw_file in raw_matches:
                raw_file = raw_file.strip()
                raw_path = RAW_DIR / raw_file
                if not raw_path.exists():
                    missing_raw_files.append({
                        "page_title": p["title"],
                        "page_slug": p["slug"],
                        "raw_file": raw_file,
                    })
                    issue_count += 1
        except KeyError:
            continue

    # 4b. Quellen, die nach dem Ingest verändert wurden
    from services.quality import stale_sources
    for p in pages:
        try:
            for source in stale_sources(contents[p["slug"]]):
                changed_raw_sources.append({"page_title": p["title"], "page_slug": p["slug"], **source})
                issue_count += 1
        except OSError:
            pass

    # 5. OKF-Pflichtfeld `type` und `tags`
    for p in pages:
        if p["slug"] in SYSTEM_PAGES:
            continue
        try:
            content = contents[p["slug"]]
            fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            has_type = False
            has_tags = False
            if fm_match:
                for line in fm_match.group(1).splitlines():
                    if line.strip().startswith("type:"):
                        has_type = True
                    if line.strip().startswith("tags:"):
                        val = line.split(":", 1)[1].strip()
                        if val and val != "[]":
                            has_tags = True
            if not has_type:
                missing_type.append(p)
                issue_count += 1
            if not has_tags:
                no_tags.append(p)
                issue_count += 1
        except KeyError:
            continue

    # 6. Defekte absolute/relative Markdown-Links und Wortanzahl-Check
    for p in pages:
        if p["slug"] in SYSTEM_PAGES:
            continue
        try:
            content = contents[p["slug"]]
            body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
            
            # Wortanzahl
            words_count = len(body.split())
            if words_count < 100:
                short_pages.append({
                    "title": p["title"],
                    "slug": p["slug"],
                    "words": words_count,
                })
                issue_count += 1

            for match in re.finditer(r"\[.*?\]\(((?:\.|/)[^)]*?\.md)\)", body):
                target = match.group(1)
                clean = target.lstrip("/")
                clean = re.sub(r"^\./", "", clean)
                clean = re.sub(r"\.md$", "", clean).lower()
                clean = clean.replace(" ", "-").replace("_", "-")
                if clean not in all_slugs and clean not in SYSTEM_PAGES:
                    broken_links.append({
                        "page_title": p["title"],
                        "page_slug": p["slug"],
                        "target": target,
                    })
                    issue_count += 1
        except KeyError:
            continue

    # 7. Querverlinkungen vorschlagen (für verwaiste Seiten)
    for o in orphans:
        o_title_lower = o["title"].lower()
        for p in pages:
            if p["slug"] == o["slug"] or p["slug"] in SYSTEM_PAGES:
                continue
            try:
                p_content = contents[p["slug"]].lower()
                p_body = re.sub(r"^---.*?---\s*", "", p_content, flags=re.DOTALL)
                if o_title_lower in p_body:
                    link_suggestions.append({
                        "from_title": p["title"],
                        "from_slug": p["slug"],
                        "to_title": o["title"],
                        "to_slug": o["slug"],
                        "keyword": o["title"]
                    })
            except KeyError:
                continue

    return {
        "orphans": orphans,
        "missing": missing_pages,
        "stale": stale_pages,
        "missing_raw": missing_raw_files,
        "changed_sources": changed_raw_sources,
        "missing_type": missing_type,
        "broken_links": broken_links,
        "no_tags": no_tags,
        "short_pages": short_pages,
        "link_suggestions": link_suggestions,
        "issue_count": issue_count,
    }
