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
    missing_type: list[dict] = []
    broken_links: list[dict] = []
    issue_count = 0

    root = wiki_path(wiki)
    if not root.exists():
        return {
            "orphans": orphans,
            "missing": missing_pages,
            "stale": stale_pages,
            "missing_raw": missing_raw_files,
            "missing_type": missing_type,
            "broken_links": broken_links,
            "issue_count": issue_count,
        }

    pages = get_all_wiki_pages(wiki)
    all_slugs = {p["slug"] for p in pages}

    # 1. Orphans (keine Rückverweise)
    for p in pages:
        if p["slug"] in SYSTEM_PAGES:
            continue
        has_backlink = False
        for other in pages:
            if other["slug"] == p["slug"]:
                continue
            other_file = root / f"{other['slug']}.md"
            try:
                other_content = other_file.read_text(encoding="utf-8", errors="replace")
                other_links = extract_links_from_content(other_content)
                if p["slug"] in other_links:
                    has_backlink = True
                    break
            except Exception:
                pass
        if not has_backlink:
            orphans.append(p)
            issue_count += 1

    # 2. Fehlende verlinkte Seiten
    missing_map: dict[str, dict] = {}
    for p in pages:
        file_path = root / f"{p['slug']}.md"
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            refs = extract_links_from_content(content)
            for target_slug in refs:
                if target_slug and target_slug not in all_slugs and target_slug not in SYSTEM_PAGES:
                    if target_slug not in missing_map:
                        missing_map[target_slug] = {
                            "title": target_slug.replace("-", " ").title(),
                            "sources": set(),
                        }
                    missing_map[target_slug]["sources"].add((p["title"], p["slug"]))
        except Exception:
            pass

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
                import datetime

                stat = file_path.stat()
                stale_pages.append({
                    "slug": p["slug"],
                    "title": p["title"],
                    "mtime_formatted": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                    "mtime": stat.st_mtime,
                })
            except Exception:
                pass
    stale_pages.sort(key=lambda x: x["mtime"])
    stale_pages = stale_pages[:5]

    # 4. Fehlende Rohquellen
    for p in pages:
        file_path = root / f"{p['slug']}.md"
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
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
        except Exception:
            pass

    # 5. OKF-Pflichtfeld `type`
    for p in pages:
        if p["slug"] in SYSTEM_PAGES:
            continue
        file_path = root / f"{p['slug']}.md"
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            has_type = False
            if fm_match:
                for line in fm_match.group(1).splitlines():
                    if line.strip().startswith("type:"):
                        has_type = True
                        break
            if not has_type:
                missing_type.append(p)
                issue_count += 1
        except Exception:
            pass

    # 6. Defekte absolute/relative Markdown-Links
    for p in pages:
        if p["slug"] in SYSTEM_PAGES:
            continue
        file_path = root / f"{p['slug']}.md"
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
            for target in re.findall(r"\[.*?\]\(((\.|/).*?\.md)\)", body):
                clean = target.lstrip("/")
                clean = re.sub(r"\.md$", "", clean).lower()
                clean = clean.replace(" ", "-").replace("_", "-")
                if clean not in all_slugs and clean not in SYSTEM_PAGES:
                    broken_links.append({
                        "page_title": p["title"],
                        "page_slug": p["slug"],
                        "target": target,
                    })
                    issue_count += 1
        except Exception:
            pass

    return {
        "orphans": orphans,
        "missing": missing_pages,
        "stale": stale_pages,
        "missing_raw": missing_raw_files,
        "missing_type": missing_type,
        "broken_links": broken_links,
        "issue_count": issue_count,
    }
