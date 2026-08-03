# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Volltextsuche (Matrix-Index FTS5 + lokaler Fallback).

Portiert aus llmWiki.py.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from core.config import (
    WIKI_DIR,
    RAW_DIR,
    EXPORT_DIR,
    BASE_PATH,
    wiki_path,
)
from services.wiki import is_text_file

TAG_SYNTAX_RE = re.compile(r'(?:^|\s)(?:tag:([\w-]+)|#([\w-]+))')


def parse_search_tags(query: str) -> tuple[str, list[str]]:
    """Extrahiert Tag-Filter aus der Suchanfrage.

    Unterstützt ``tag:tagname`` und ``#tagname`` Syntax.

    Returns:
        Tuple (bereinigter Suchtext, Liste der extrahierten Tags).
    """
    tags = TAG_SYNTAX_RE.findall(query)
    extracted = [t[0] or t[1] for t in tags]
    cleaned = TAG_SYNTAX_RE.sub("", query).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, extracted


def local_search(query: str, wiki: str = "main", num_results: int = 10) -> dict:

    """Fallback Volltextsuche. Unterstützt 'all' für Cross-Wiki-Suche und Tag-Suche."""
    from services.tags import extract_tags, normalize_tag

    results: list[dict] = []
    cleaned_query, search_tags = parse_search_tags(query)
    query_lower = (cleaned_query or query).lower()
    norm_search_tags = [normalize_tag(t) for t in search_tags if t]

    def snippet_of(content: str, q: str) -> str:
        if not q:
            clean = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
            return clean[:150].replace("\n", " ").strip() + "..."
        idx = content.lower().find(q)
        if idx == -1:
            clean = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
            return clean[:150].replace("\n", " ").strip() + "..."
        start = max(0, idx - 80)
        end = min(len(content), idx + 120)
        snip = content[start:end].replace("\n", " ").strip()
        if start > 0:
            snip = "..." + snip
        if end < len(content):
            snip = snip + "..."
        return snip

    wikis_to_search = []
    if wiki == "all":
        from core.config import list_wikis

        wikis_to_search = [w.get("slug") or w.get("name") for w in list_wikis()]
    else:
        wikis_to_search = [wiki]

    for w in wikis_to_search:
        root = wiki_path(w)
        if root.exists():
            for f in sorted(root.iterdir()):
                if f.suffix != ".md" or f.stem in ("index", "log", "ingestlater"):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    clean_content = re.sub(
                        r"^---.*?---\s*", "", content, flags=re.DOTALL
                    )
                    title_match = re.search(
                        r"^#\s+(.+)$", clean_content, re.MULTILINE
                    )
                    title = (
                        title_match.group(1)
                        if title_match
                        else f.stem.replace("-", " ").title()
                    )

                    page_tags = extract_tags(content)
                    norm_page_tags = [normalize_tag(t) for t in page_tags]

                    score = 0

                    # Tag-Match Prüfung
                    tag_matched = False
                    if norm_search_tags:
                        for st in norm_search_tags:
                            if st in norm_page_tags:
                                score += 20
                                tag_matched = True
                        if not tag_matched and not query_lower:
                            continue
                    elif query_lower in norm_page_tags or normalize_tag(query_lower) in norm_page_tags:
                        score += 15

                    if query_lower:
                        if query_lower in title.lower():
                            score += 10
                        if query_lower in clean_content.lower():
                            score += clean_content.lower().count(query_lower)

                    if score > 0:
                        results.append(
                            {
                                "title": title,
                                "slug": f.stem,
                                "path": f"wiki/{f.name}",
                                "wiki": w,
                                "url": f"{BASE_PATH}/wiki/{w}/{f.stem}",
                                "snippet": snippet_of(clean_content, query_lower),
                                "score": score,
                                "tags": page_tags,
                            }
                        )
                except Exception:
                    pass

    if RAW_DIR.exists() and not norm_search_tags:
        for f in sorted(RAW_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep" and is_text_file(f.name):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    score = 0
                    if query_lower and query_lower in f.name.lower():
                        score += 8
                    if query_lower and query_lower in content.lower():
                        score += content.lower().count(query_lower)
                    if score > 0:
                        results.append(
                            {
                                "title": f"Rohquelle: {f.name}",
                                "slug": f.stem,
                                "path": f"raw/{f.name}",
                                "wiki": "global",
                                "url": f"/raw/{f.name}",
                                "snippet": snippet_of(content, query_lower),
                                "score": score,
                            }
                        )
                except Exception:
                    pass

    if EXPORT_DIR.exists() and not norm_search_tags:
        for f in sorted(EXPORT_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep" and is_text_file(f.name):
                if wiki != "all" and not f.name.startswith(f"{wiki}__"):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    score = 0
                    if query_lower and query_lower in f.name.lower():
                        score += 8
                    if query_lower and query_lower in content.lower():
                        score += content.lower().count(query_lower)
                    if score > 0:
                        export_wiki = "global"
                        if "__" in f.name:
                            export_wiki = f.name.split("__")[0]
                        results.append(
                            {
                                "title": f"Exportiert: {f.name}",
                                "slug": f.stem,
                                "path": f"output_docs/{f.name}",
                                "wiki": export_wiki,
                                "url": f"/export/{f.name}",
                                "snippet": snippet_of(content, query_lower),
                                "score": score,
                            }
                        )
                except Exception:
                    pass

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"results": results, "error": None}


async def matrix_search(query: str, wiki: str = "main", num_results: int = 30) -> dict:
    """Projekt-Matrix-Suche: persistente SQLite-Shards (Hauptsuchsystem).

    Nutzt den ``MatrixSearcher``. Fällt bei Fehlern auf den lokalen Python-Index
    zurück, sodass die Suche niemals ausfällt.
    """
    try:
        from services.matrix_searcher import MatrixSearcher
    except (ImportError, Exception):
        return await asyncio.to_thread(local_search, query, wiki, num_results)

    cleaned_query, search_tags = parse_search_tags(query)
    effective_query = cleaned_query or query
    if len(effective_query.strip()) < 2:
        return {"results": [], "error": None}

    try:
        searcher = MatrixSearcher()
        wiki_ids = ["all"] if wiki == "all" else [wiki]
        data = await searcher.search(
            wiki_ids=wiki_ids, query=effective_query, limit=num_results, tags=search_tags
        )
    except (ImportError, Exception) as exc:
        log = __import__("logging").getLogger("llmwiking.matrix")
        log.warning("matrix_search fällt auf lokale Suche zurück: %s", exc)
        return await asyncio.to_thread(local_search, query, wiki, num_results)

    results = []
    for item in data.get("results", []):
        md_path = item.get("path", "").replace("wikis/" + item.get("wiki", "") + "/", "")
        results.append(
            {
                "title": item.get("title", ""),
                "slug": item.get("slug", md_path.rstrip(".md")),
                "path": f"wikis/{item.get('wiki', wiki)}/{md_path}",
                "wiki": item.get("wiki", wiki),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", ""),
                "score": abs(item.get("score", 0)),
                "tags": item.get("tags", []),
                "source": "matrix",
            }
        )
        results[-1]["search_time_ms"] = data.get("search_time_ms", 0)
        results[-1]["shards_queried"] = data.get("shards_queried", 0)

    if not results:
        return await asyncio.to_thread(local_search, query, wiki, num_results)

    return {
        "results": results,
        "error": None,
        "search_time_ms": data.get("search_time_ms", 0),
        "shards_queried": data.get("shards_queried", 0),
        "source": "matrix",
    }



def search_wiki(query: str, wiki: str = "main", num_results: int = 10) -> dict:
    """Pure-Matrix-Suche (synchron): Matrix vor lokalem Fallback.

    Laeuft ohne externe Binary und ist der einzige Suchpfad.
    """
    try:
        from services.matrix_searcher import MatrixSearcher

        data = asyncio.run(
            MatrixSearcher().search(
                wiki_ids=["all"] if wiki == "all" else [wiki],
                query=query,
                limit=num_results,
            )
        )
        if data.get("results"):
            results = []
            for item in data["results"]:
                md_path = item.get("path", "").replace(
                    "wikis/" + item.get("wiki", "") + "/", ""
                )
                results.append(
                    {
                        "title": item.get("title", ""),
                        "slug": item.get("slug", ""),
                        "path": f"wikis/{item.get('wiki', wiki)}/{md_path}",
                        "wiki": item.get("wiki", wiki),
                        "url": item.get("url", ""),
                        "snippet": item.get("snippet", ""),
                        "score": abs(item.get("score", 0)),
                        "tags": item.get("tags", []),
                        "source": "matrix",
                    }
                )
            return {"results": results, "error": None}
    except (ImportError, Exception):
        pass
    return local_search(query, wiki)
