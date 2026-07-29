from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from core.config import wiki_path
from services.cache import get_cache


def normalize_tag(tag: str) -> str:
    """Normalisiert einen Tag: lowercase, Leerzeichen → Bindestriche,
    entfernt alle Zeichen außer alphanumerisch, Bindestriche und Unicode-Buchstaben.
    """
    import unicodedata
    tag = tag.strip().lower()
    tag = tag.replace(" ", "-")
    # Behalte alphanumerisch, Bindestriche und Unicode-Buchstaben/Zahlen
    normalized = "".join(
        c for c in tag
        if c == "-" or unicodedata.category(c) in ("Ll", "Lu", "Lt", "Lo", "Nd", "Nl")
    )
    # Mehrfache Bindestriche zusammenfassen
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-")


def parse_tags_from_fm(fm_text: str) -> list[str]:
    for line in fm_text.split("\n"):
        if line.startswith("tags:"):
            val = line.split(":", 1)[1].strip()
            val = val.strip("[]").replace('"', "").replace("'", "")
            return [normalize_tag(t) for t in val.split(",") if t.strip()]
    return []


def extract_tags(content: str) -> list[str]:
    fm = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm:
        return parse_tags_from_fm(fm.group(1))
    return []


def get_page_tags(wiki: str, slug: str) -> list[str]:
    root = wiki_path(wiki)
    fp = root / f"{slug}.md"
    if not fp.exists():
        return []
    try:
        content = fp.read_text(encoding="utf-8", errors="replace")
        return extract_tags(content)
    except Exception:
        return []


def build_tag_index(wiki: str = "main") -> dict[str, list[dict]]:
    cache = get_cache()
    root = wiki_path(wiki)
    key = f"tags:{wiki}"
    cached = cache.get(key, root)
    if cached is not None:
        return cached

    from services.wiki import get_all_wiki_pages
    pages = get_all_wiki_pages(wiki)
    index: dict[str, list[dict]] = {}

    for p in pages:
        slug = p["slug"]
        fp = root / f"{slug}.md"
        if not fp.exists():
            continue
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
            tags = extract_tags(content)
        except Exception:
            continue
        for tag in tags:
            index.setdefault(tag, []).append({
                "slug": slug,
                "title": p["title"],
                "type": p["type"],
            })

    cache.set(key, index, root)
    return index


def list_all_tags(wiki: str = "main") -> list[dict]:
    index = build_tag_index(wiki)
    result = []
    for tag, pages in index.items():
        result.append({
            "tag": tag,
            "count": len(pages),
            "pages": pages,
        })
    # Sortierung nach Häufigkeit absteigend, bei Gleichstand alphabetisch
    result.sort(key=lambda x: (-x["count"], x["tag"]))
    return result


def get_tag_cloud(wiki: str = "main", min_count: int = 1) -> list[dict]:
    index = build_tag_index(wiki)
    result = [
        {"tag": tag, "count": len(pages)}
        for tag, pages in index.items()
        if len(pages) >= min_count
    ]
    # Absteigend nach Häufigkeit, bei Gleichstand alphabetisch
    result.sort(key=lambda x: (-x["count"], x["tag"]))
    return result


def get_pages_by_tag(tag: str, wiki: str = "main") -> list[dict]:
    index = build_tag_index(wiki)
    return index.get(normalize_tag(tag), [])


def get_all_tags_aggregated(wiki: str = "main") -> dict:
    index = build_tag_index(wiki)
    tag_counts = {t: len(ps) for t, ps in index.items()}
    all_pages = set()
    for ps in index.values():
        for p in ps:
            all_pages.add(p["slug"])
    return {
        "total_tags": len(index),
        "tagged_pages": len(all_pages),
        "tags": tag_counts,
    }
