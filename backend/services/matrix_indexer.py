# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Projekt Matrix: persistenter Volltextindex auf SQLite-Shards.

Der Indexer schreibt Dokumente in ein Shard-Schema (``<wiki>_shard_NNN.db``)
unter ``MATRIX_DATA_ROOT``. Alle Schreibvorgänge laufen sequentiell über einen
asyncio.Queue-Worker, damit SQLite auf NAS-freundlichen Pragma-Einstellungen
(WAL, synchronous=FULL, busy_timeout) kollisionsfrei bedient wird.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from core.config import MATRIX_DATA_ROOT, MATRIX_SHARDS, WIKIS_ROOT

log = logging.getLogger("llmwiking.matrix.indexer")

try:
    import aiosqlite
except ImportError:  # pragma: no cover
    aiosqlite = None

# NAS-sichere Pragma-Konfiguration für jede Shard-Verbindung.
_DEFAULT_PRAGMAS = {
    "journal_mode": "WAL",
    "synchronous": "FULL",
    "mmap_size": 0,
    "busy_timeout": 5000,
    "wal_autocheckpoint": 100,
}

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS docs (
    doc_id        TEXT PRIMARY KEY,
    wiki_id       TEXT NOT NULL,
    title         TEXT NOT NULL,
    tags          TEXT NOT NULL DEFAULT '',
    md_path       TEXT NOT NULL DEFAULT '',
    doc_type      TEXT NOT NULL DEFAULT 'concept',
    content_length INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
    title,
    content,
    tags,
    tokenize='porter unicode61'
);
"""

_REGISTRY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS doc_registry (
    doc_id       TEXT PRIMARY KEY,
    wiki_id      TEXT NOT NULL,
    md_path      TEXT NOT NULL DEFAULT '',
    shard_name   TEXT NOT NULL,
    last_updated TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MatrixIndexer:
    """Sequentieller Volltext-Indexer auf SQLite-Shards."""

    SHARDS = MATRIX_SHARDS

    def __init__(
        self,
        data_root: str | Path | None = None,
        wiki_root: str | Path | None = None,
    ) -> None:
        self.data_root = Path(data_root or MATRIX_DATA_ROOT)
        self.wiki_root = Path(wiki_root or WIKIS_ROOT)
        self.shards = int(getattr(self, "SHARDS", 0) or MATRIX_SHARDS)
        self._write_queue: asyncio.Queue = asyncio.Queue(maxsize=0)
        self._worker_task: asyncio.Task | None = None
        self._running = False
        self._stats: dict = {"indexed": 0, "errors": 0, "queue_peak": 0}
        self._registry_path = self.data_root / "registry.db"

    # ──────────────────────────────────────────────────────────── Lebenszyklus
    async def start(self) -> None:
        """Öffnet das Datenverzeichnis und startet den Schreib-Worker."""
        self.data_root.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._worker_task = asyncio.create_task(self._write_worker())
        await asyncio.to_thread(self._init_registry)
        log.info("MatrixIndexer gestartet: root=%s shards=%d", self.data_root, self.shards)

    async def stop(self) -> None:
        """Signalisiert dem Worker das Ende und wartet auf dessen Abschluss."""
        if not self._running:
            return
        self._running = False
        await self._write_queue.put(None)
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=30)
            except (asyncio.TimeoutError, Exception):
                log.exception("MatrixIndexer.stop: Worker räumt nicht auf")
            self._worker_task = None

    # ──────────────────────────────────────────────────────── Öffentliche API
    def index_document(
        self,
        wiki_id: str,
        doc_id: str,
        title: str,
        content: str,
        tags: str = "",
        md_path: str = "",
        doc_type: str = "concept",
    ) -> bool:
        """Reiht ein Dokument zur Indexierung ein. Retourniert True, wenn angenommen."""
        if not self._running or not doc_id:
            return False
        self._write_queue.put_nowait(
            {
                "_action": "index",
                "wiki_id": wiki_id,
                "doc_id": doc_id,
                "title": title,
                "content": content,
                "tags": tags,
                "md_path": md_path,
                "doc_type": doc_type,
            }
        )
        self._stats["queue_peak"] = max(
            self._stats["queue_peak"], self._write_queue.qsize()
        )
        return True

    def remove_document(self, wiki_id: str, doc_id: str) -> bool:
        """Reiht das Entfernen eines Dokuments ein."""
        if not self._running or not doc_id:
            return False
        self._write_queue.put_nowait(
            {"_action": "delete", "wiki_id": wiki_id, "doc_id": doc_id}
        )
        return True

    def get_stats(self) -> dict:
        """Liefert Kennzahlen des Indexes (Shard-Anzahl, Größen, Queue)."""
        shard_count = 0
        total_size = 0
        registry_size = 0
        try:
            for f in self.data_root.glob("*_shard_*.db"):
                shard_count += 1
                try:
                    total_size += f.stat().st_size
                except OSError:
                    pass
            try:
                registry_size = self._registry_path.stat().st_size
            except OSError:
                registry_size = 0
        except Exception:
            pass
        return {
            "shard_count": shard_count,
            "total_size_bytes": total_size,
            "registry_size_bytes": registry_size,
            "queue_size": self._write_queue.qsize() if self._running else 0,
            "indexed": self._stats["indexed"],
            "errors": self._stats["errors"],
            "queue_peak": self._stats["queue_peak"],
            "running": self._running,
        }

    def join(self) -> asyncio.Future:
        """Gibt ein Awaitable zurück, das abschließt, sobald die Queue leer ist."""
        return self._write_queue.join()

    # ────────────────────────────────────────────────────────────── Internals
    async def _write_worker(self) -> None:
        """Verarbeitet Index-/Lösch-Jobs strikt sequentiell."""
        while True:
            job = await self._write_queue.get()
            try:
                if job is None:
                    return
                try:
                    await self._do_index(job) if job["_action"] == "index" else await self._do_delete(job)
                    if job["_action"] == "index":
                        self._stats["indexed"] += 1
                except Exception:
                    self._stats["errors"] += 1
                    log.exception(
                        "MatrixIndexer: Job fehlgeschlagen (%s %s/%s)",
                        job["_action"], job.get("wiki_id", "?"), job.get("doc_id", "?"),
                    )
                    try:
                        from services.errorlog import append_error
                        append_error(
                            "matrix",
                            f"Index-/Delete-Job fehlgeschlagen "
                            f"({job['_action']} {job.get('wiki_id', '?')}/{job.get('doc_id', '?')})",
                            exc=sys.exc_info()[1],
                        )
                    except Exception:
                        pass
            finally:
                self._write_queue.task_done()

    def _get_shard_path(self, wiki_id: str, doc_id: str) -> Path:
        digest = hashlib.md5(f"{wiki_id}::{doc_id}".encode("utf-8")).hexdigest()
        shard_no = int(digest, 16) % self.shards
        return self.data_root / f"{wiki_id}_shard_{shard_no:03d}.db"

    def _init_registry(self) -> None:
        import sqlite3

        self.data_root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._registry_path))
        try:
            conn.executescript(_REGISTRY_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    async def _configure_connection(self, conn: aiosqlite.Connection) -> None:
        await conn.execute(f"PRAGMA journal_mode={_DEFAULT_PRAGMAS['journal_mode']}")
        await conn.execute(f"PRAGMA synchronous={_DEFAULT_PRAGMAS['synchronous']}")
        await conn.execute(f"PRAGMA mmap_size={_DEFAULT_PRAGMAS['mmap_size']}")
        await conn.execute(f"PRAGMA busy_timeout={_DEFAULT_PRAGMAS['busy_timeout']}")
        await conn.execute(f"PRAGMA wal_autocheckpoint={_DEFAULT_PRAGMAS['wal_autocheckpoint']}")

    async def _do_index(self, job: dict) -> None:
        from services.tags import extract_tags, normalize_tag

        wiki_id = job["wiki_id"]
        doc_id = job["doc_id"]
        md_path = job.get("md_path", "") or doc_id
        shard = self._get_shard_path(wiki_id, doc_id)

        tags = job.get("tags", "") or ""
        if isinstance(tags, str):
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            tag_list = list(tags)
        if job.get("content"):
            for t in extract_tags(job["content"]):
                norm = normalize_tag(t)
                if norm and norm not in tag_list:
                    tag_list.append(norm)
        tags_joined = ",".join(tag_list)
        title = job.get("title", "") or doc_id.replace("-", " ").title()
        content = job.get("content", "") or ""
        updated_at = _now()

        shard.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(shard), timeout=10) as conn:
            await self._configure_connection(conn)
            await conn.executescript(_SCHEMA_SQL)

            # Altbestand in docs suchen; bei erneuter Indexierung den FTS-Row
            # samt Inhalt löschen (UPSERT-Semantik).
            old_rowid = None
            async with conn.execute(
                "SELECT rowid FROM docs WHERE doc_id = ?", (doc_id,)
            ) as cur:
                row = await cur.fetchone()
                old_rowid = row[0] if row else None

            if old_rowid is not None:
                await conn.execute("DELETE FROM fts WHERE rowid = ?", (old_rowid,))

            await conn.execute(
                "DELETE FROM docs WHERE doc_id = ?", (doc_id,)
            )
            await conn.execute(
                "INSERT INTO docs "
                "(doc_id, wiki_id, title, tags, md_path, doc_type, content_length, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    wiki_id,
                    title,
                    tags_joined,
                    md_path,
                    job.get("doc_type", "concept"),
                    len(content.encode("utf-8")),
                    updated_at,
                ),
            )
            async with conn.execute(
                "SELECT rowid FROM docs WHERE doc_id = ?", (doc_id,)
            ) as cur:
                row = await cur.fetchone()
                new_rowid = row[0] if row else None

            if new_rowid is not None:
                await conn.execute(
                    "INSERT INTO fts(rowid, title, content, tags) VALUES (?, ?, ?, ?)",
                    (new_rowid, title, content, tags_joined),
                )
            await conn.commit()

        await self._update_registry(wiki_id, doc_id, md_path, shard.name)

    async def _do_delete(self, job: dict) -> None:
        wiki_id = job["wiki_id"]
        doc_id = job["doc_id"]
        shard = self._get_shard_path(wiki_id, doc_id)
        if not shard.exists():
            await self._remove_registry(doc_id)
            return

        async with aiosqlite.connect(str(shard), timeout=10) as conn:
            await self._configure_connection(conn)
            async with conn.execute(
                "SELECT rowid FROM docs WHERE doc_id = ?", (doc_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is not None:
                await conn.execute("DELETE FROM fts WHERE rowid = ?", (row[0],))
            await conn.execute("DELETE FROM docs WHERE doc_id = ?", (doc_id,))
            await conn.commit()
        await self._remove_registry(doc_id)

    async def _update_registry(self, wiki_id: str, doc_id: str, md_path: str, shard_name: str) -> None:
        import sqlite3

        def _write() -> None:
            conn = sqlite3.connect(str(self._registry_path), timeout=10)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO doc_registry "
                    "(doc_id, wiki_id, md_path, shard_name, last_updated) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (doc_id, wiki_id, md_path, shard_name, _now()),
                )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_write)

    async def _remove_registry(self, doc_id: str) -> None:
        import sqlite3

        def _write() -> None:
            conn = sqlite3.connect(str(self._registry_path), timeout=10)
            try:
                conn.execute("DELETE FROM doc_registry WHERE doc_id = ?", (doc_id,))
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_write)
