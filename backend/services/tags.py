# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path

import yaml
from core.config import DATA_DIR, wiki_path
from services.cache import get_cache

log = logging.getLogger("llmwiking.tags")

TAGS_STORE_FILE = DATA_DIR / "tags.json"


def normalize_tag(tag: str) -> str:
    """Normalisiert einen Tag: lowercase, Leerzeichen/Unterstriche → Bindestriche,
    entfernt alle Zeichen außer alphanumerisch, Bindestriche und Unicode-Buchstaben.
    """
    import unicodedata

    tag = tag.strip().lower()
    if tag.startswith("#"):
        tag = tag[1:]
    tag = tag.replace(" ", "-").replace("_", "-")
    # Behalte alphanumerisch, Bindestriche und Unicode-Buchstaben/Zahlen
    normalized = "".join(
        c
        for c in tag
        if c == "-" or unicodedata.category(c) in ("Ll", "Lu", "Lt", "Lo", "Nd", "Nl")
    )
    # Mehrfache Bindestriche zusammenfassen
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-")


def parse_tags_from_fm(fm_text: str) -> list[str]:
    """Parst Tags aus YAML-Frontmatter (unterstützt Listen, Komma-Separiert, Strings)."""
    tags: list[str] = []
    if not fm_text:
        return tags

    try:
        data = yaml.safe_load(fm_text)
        if isinstance(data, dict) and "tags" in data:
            raw = data["tags"]
            if isinstance(raw, list):
                tags = [normalize_tag(str(t)) for t in raw if t]
            elif isinstance(raw, str):
                tags = [
                    normalize_tag(t)
                    for t in raw.replace("[", "").replace("]", "").split(",")
                    if t.strip()
                ]
    except Exception:
        pass

    if not tags:
        for line in fm_text.split("\n"):
            line_s = line.strip()
            if line_s.startswith("tags:"):
                val = line_s.split(":", 1)[1].strip()
                val = val.strip("[]").replace('"', "").replace("'", "")
                if val:
                    tags = [normalize_tag(t) for t in val.split(",") if t.strip()]
                break

    # Deduplizieren
    res = []
    for t in tags:
        if t and t not in res:
            res.append(t)
    return res


def extract_hashtags(content: str) -> list[str]:
    """Extrahiert Inline-Hashtags (#tagname) aus dem Body (ohne Codeblöcke/Links)."""
    if not content:
        return []
    # Frontmatter und Codeblöcke entfernen
    body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
    body = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    body = re.sub(r"`.*?`", "", body)
    body = re.sub(r"\[.*?\]\(.*?\)", "", body)

    matches = re.findall(
        r"(?:^|\s)#([a-zA-ZäöüßÄÖÜ][a-zA-ZäöüßÄÖÜ0-9_-]{1,30})", body
    )
    res = []
    for m in matches:
        norm = normalize_tag(m)
        if norm and norm not in res:
            res.append(norm)
    return res


def extract_tags(content: str) -> list[str]:
    """Extrahiert Frontmatter-Tags und Inline-Hashtags aus einer Seite."""
    fm = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    tags: list[str] = []
    if fm:
        tags.extend(parse_tags_from_fm(fm.group(1)))

    hashtags = extract_hashtags(content)
    for ht in hashtags:
        if ht not in tags:
            tags.append(ht)

    return tags


def auto_generate_tags_for_content(
    content: str, title: str = "", wiki: str = "main", max_tags: int = 4
) -> list[str]:
    """Generiert automatisch passende Tags basierend auf Titel, Textinhalt und vorhandenem Tag-Index."""
    clean_text = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
    words = re.findall(
        r"[a-zA-ZäöüßÄÖÜ0-9-]{3,}", f"{title} {clean_text}".lower()
    )

    stopwords = {
        "und",
        "der",
        "die",
        "das",
        "mit",
        "für",
        "von",
        "ein",
        "eine",
        "einer",
        "einem",
        "des",
        "dem",
        "den",
        "auf",
        "aus",
        "ist",
        "sind",
        "wie",
        "nach",
        "über",
        "nicht",
        "auch",
        "dass",
        "diese",
        "dieser",
        "dieses",
        "oder",
        "aber",
        "wiki",
        "seite",
        "teil",
        "index",
        "main",
        "http",
        "https",
        "html",
        "com",
    }

    word_freq = Counter(words)
    matched_tags: list[str] = []

    # 1. Bekannte Tags aus vorhandenen Tag-Clouds bevorzugen
    try:
        existing_cloud = get_tag_cloud(wiki)
        existing_tags = {t["tag"].lower(): t["tag"] for t in existing_cloud}
        for word, _ in word_freq.most_common(30):
            if word in existing_tags and existing_tags[word] not in matched_tags:
                matched_tags.append(existing_tags[word])
                if len(matched_tags) >= max_tags:
                    break
    except Exception:
        pass

    # 2. Wenn noch nicht genügend Tags gefunden wurden, Schlüsselwörter verwenden
    if len(matched_tags) < max_tags:
        for word, _ in word_freq.most_common(30):
            norm = normalize_tag(word)
            if (
                norm
                and len(norm) >= 3
                and norm not in stopwords
                and norm not in matched_tags
            ):
                matched_tags.append(norm)
                if len(matched_tags) >= max_tags:
                    break

    return matched_tags


def _load_tag_store() -> dict[str, dict[str, list[dict]]]:
    """Liest den persistenten Tag-Speicher aus data/tags.json."""
    if TAGS_STORE_FILE.exists():
        try:
            data = json.loads(TAGS_STORE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as e:
            log.warning("Fehler beim Lesen von data/tags.json: %s", e)
    return {}


def _save_tag_store(store: dict[str, dict[str, list[dict]]]) -> None:
    """Speichert den persistenten Tag-Speicher in data/tags.json."""
    try:
        from core.config import _atomic_write
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            TAGS_STORE_FILE,
            json.dumps(store, indent=2, ensure_ascii=False),
        )
    except Exception as e:
        log.warning("Konnte data/tags.json nicht schreiben: %s", e)


def get_page_tags(wiki: str, slug: str) -> list[str]:
    root = wiki_path(wiki)
    fp = root / f"{slug}.md"
    if not fp.exists():
        return []
    try:
        content = fp.read_text(encoding="utf-8", errors="replace")
        tags = extract_tags(content)
        if not tags:
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1) if title_match else slug
            tags = auto_generate_tags_for_content(content, title=title, wiki=wiki)
        return tags
    except Exception:
        return []


def build_tag_index(
    wiki: str = "main", force_rebuild: bool = False
) -> dict[str, list[dict]]:
    cache = get_cache()
    root = wiki_path(wiki)
    key = f"tags:{wiki}"

    from services.wiki import get_all_wiki_pages, _get_all_wiki_pages_uncached

    if not force_rebuild:
        cached = cache.get(key, root)
        if cached is not None:
            return cached

        # Versuche aus data/tags.json zu laden
        store = _load_tag_store()
        if wiki in store and store[wiki]:
            cache.set(key, store[wiki], root)
            return store[wiki]
        pages = get_all_wiki_pages(wiki)
    else:
        cache.invalidate(f"pages:{wiki}")
        pages = _get_all_wiki_pages_uncached(wiki)

    index: dict[str, list[dict]] = {}

    for p in pages:
        slug = p["slug"]
        fp = root / f"{slug}.md"
        if not fp.exists():
            continue
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
            tags = extract_tags(content)
            if not tags:
                tags = auto_generate_tags_for_content(
                    content, title=p["title"], wiki=wiki
                )
        except Exception:
            continue
        for tag in tags:
            index.setdefault(tag, []).append(
                {
                    "slug": slug,
                    "title": p["title"],
                    "type": p["type"],
                }
            )

    cache.set(key, index, root)

    # Persistieren in data/tags.json
    store = _load_tag_store()
    store[wiki] = index
    _save_tag_store(store)

    return index


def list_all_tags(wiki: str = "main") -> list[dict]:
    index = build_tag_index(wiki)
    result = []
    for tag, pages in index.items():
        result.append(
            {
                "tag": tag,
                "count": len(pages),
                "pages": pages,
            }
        )
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
    norm = normalize_tag(tag)
    return index.get(norm, [])


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

