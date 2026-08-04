# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Projekt Matrix: paralleler FTS5-Reader über alle Shards.

Der Searcher öffnet jeden vorhandenen Shard kurzzeitig, führt eine BM25-
Abfrage aus und aggregiert die Ergebnisse. Die Anzahl gleichzeitiger
Verbindungen ist über ein asyncio.Semaphore begrenzt.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path


from core.config import BASE_PATH, MATRIX_DATA_ROOT, MATRIX_MAX_CONCURRENT_READS, MATRIX_SHARDS

log = logging.getLogger("llmwiking.matrix.searcher")

try:
    import aiosqlite
except ImportError:  # pragma: no cover
    aiosqlite = None

# Pro-Shard-Limit: nur die besten Treffer je Shard holen und global sortieren.
_PER_SHARD_LIMIT = 10
_QUERY_TIMEOUT = 10.0

_QUERY_SQL = """
SELECT
    d.wiki_id    AS wiki_id,
    d.doc_id     AS doc_id,
    d.title      AS title,
    d.tags       AS tags,
    d.md_path    AS md_path,
    d.doc_type   AS doc_type,
    snippet(fts, 1, '<mark>', '</mark>', '...', 32) AS snippet,
    bm25(fts)    AS rank
FROM fts
JOIN docs d ON d.rowid = fts.rowid
WHERE fts MATCH ?
ORDER BY rank
LIMIT ?
"""


class MatrixSearcher:
    """Durchsucht die Matrix-Shards mit parallelen FTS5-Queries."""

    def __init__(
        self,
        data_root: str | Path | None = None,
        max_concurrent: int | None = None,
    ) -> None:
        self.data_root = Path(data_root or MATRIX_DATA_ROOT)
        self.shards = MATRIX_SHARDS
        self.max_concurrent = max_concurrent or MATRIX_MAX_CONCURRENT_READS
        self._sem = asyncio.Semaphore(self.max_concurrent)

    async def search(
        self,
        wiki_ids: list[str],
        query: str,
        limit: int = 30,
        tags: list[str] | None = None,
    ) -> dict:
        """Sucht über alle Shards und liefert sortierte Ergebnisse.

        Returns:
            Dict mit den Schlüsseln ``results``, ``total``, ``search_time_ms``
            und ``shards_queried``.
        """
        start = time.perf_counter()
        # Tag-Filter normalisieren, damit Groß-/Kleinschreibung und
        # Umlaute korrekt mit den indizierten (normalisierten) Tags matchen.
        try:
            from services.tags import normalize_tag
            tag_filters = [normalize_tag(t) for t in (tags or []) if t]
        except (ImportError, Exception):
            tag_filters = [t.lower() for t in (tags or []) if t]
        wikis = self._resolve_wikis(wiki_ids)
        query_text = query.strip()

        shard_paths = sorted(self.data_root.glob("*_shard_*.db"))
        tasks = [
            self._query_shard(path, query_text, tag_filters, wikis)
            for path in shard_paths
        ]
        shards_queried = 0
        results: list[dict] = []

        chunk_size = max(self.max_concurrent // 2, 8)
        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i : i + chunk_size]
            batch = await asyncio.gather(*chunk, return_exceptions=True)
            for outcome in batch:
                if isinstance(outcome, Exception):
                    log.warning("MatrixSearcher: Shard-Fehler übersprungen: %s", outcome)
                    continue
                if not outcome:
                    continue
                shards_queried += 1
                results.extend(outcome)

        results.sort(key=lambda r: r.get("score", 0), reverse=True)
        results = results[:limit]
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return {
            "results": results,
            "total": len(results),
            "search_time_ms": elapsed_ms,
            "shards_queried": shards_queried,
        }

    def _resolve_wikis(self, wiki_ids: list[str]) -> list[str]:
        from core.config import list_wikis

        wanted = set(wiki_ids or [])
        if not wanted or "all" in wanted:
            return [w.get("slug") or w.get("name") for w in list_wikis()]
        return list(wanted)

    async def _query_shard(
        self,
        shard_path: Path,
        query: str,
        tag_filters: list[str],
        wikis: list[str],
    ) -> list[dict] | None:
        async with self._sem:
            # FTS5 Sonderzeichen bereinigen & Suchwörter flexibel verknüpfen
            words = re.findall(r"\w+", query)
            if not words:
                return None
            fts_query = " OR ".join(words)

            try:
                async with aiosqlite.connect(str(shard_path), timeout=_QUERY_TIMEOUT) as conn:
                    conn.row_factory = aiosqlite.Row
                    await conn.execute("PRAGMA query_only=ON")
                    async with conn.execute(
                        _QUERY_SQL, (fts_query, _PER_SHARD_LIMIT)
                    ) as cur:
                        rows = await cur.fetchall()
            except Exception:
                raise

        out: list[dict] = []
        for row in rows:
            wiki_id = row["wiki_id"]
            if wikis and wiki_id not in wikis:
                continue
            row_tags = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
            if tag_filters and not all(t in row_tags for t in tag_filters):
                continue
            md_path = row["md_path"] or row["doc_id"]
            slug = md_path[:-3] if md_path.endswith(".md") else md_path
            out.append(
                {
                    "doc_id": row["doc_id"],
                    "wiki": wiki_id,
                    "title": row["title"],
                    "slug": slug,
                    "path": f"wikis/{wiki_id}/{md_path}",
                    "url": f"{BASE_PATH}/wiki/{wiki_id}/{slug}",
                    "snippet": row["snippet"],
                    "tags": row_tags,
                    "doc_type": row["doc_type"],
                    "score": abs(row["rank"]),
                }
            )
        return out

    def get_stats(self) -> dict:
        """Liefert Groesse und Anzahl der Shards sowie das Concurrent-Limit."""
        shard_count = 0
        total_size = 0
        try:
            for f in self.data_root.glob("*_shard_*.db"):
                shard_count += 1
                try:
                    total_size += f.stat().st_size
                except OSError:
                    pass
        except Exception:
            pass
        return {
            "shard_count": shard_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_concurrent": self.max_concurrent,
        }
