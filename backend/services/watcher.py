# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Background File-Watcher for wiki changes.

Uses watchdog to monitor wiki directories for .md file changes
and triggers incremental sync automatically with debounce.
When a MatrixIndexer is attached, changed files are indexed directly
into the persistent search shards before the full sync runs.
"""

import asyncio
import concurrent.futures
import logging
import re
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    Observer = object
    FileSystemEventHandler = object

from core.config import wiki_path
from services.sync import do_matrix_sync_async, do_sync_async

log = logging.getLogger("llmwiking.watcher")

SYSTEM_STEMS = {"index", "log", "ingestlater"}


def _index_changed_file(
    wiki: str,
    changed_path: Path | None,
    matrix_indexer,
) -> None:
    """Indexiert eine geänderte/neu angelegte Markdown-Datei in die Matrix."""
    if matrix_indexer is None or changed_path is None:
        return
    try:
        rel = changed_path.relative_to(wiki_path(wiki))
        if rel.parts and rel.parts[0].startswith("."):
            return  # versteckte Verzeichnisse ignorieren
        if changed_path.suffix.lower() != ".md":
            return
        if changed_path.stem in SYSTEM_STEMS:
            return

        content = changed_path.read_text(encoding="utf-8", errors="replace")
        body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
        title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else changed_path.stem.title()

        doc_id = str(rel.with_suffix("")).replace("\\", "/")
        fm = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        tags = ""
        if fm:
            from services.tags import parse_tags_from_fm

            tags = ",".join(parse_tags_from_fm(fm.group(1)))

        matrix_indexer.index_document(
            wiki_id=wiki,
            doc_id=doc_id,
            title=title,
            content=content,
            tags=tags,
            md_path=str(rel).replace("\\", "/"),
        )
    except Exception as e:
        log.warning("Watcher: Matrix-Index für '%s' fehlgeschlagen: %s", changed_path, e)


class WikiChangeHandler(FileSystemEventHandler):
    def __init__(
        self,
        wiki: str,
        loop: asyncio.AbstractEventLoop,
        matrix_indexer=None,
    ):
        self.wiki = wiki
        self.loop = loop
        self.matrix_indexer = matrix_indexer
        self._pending: concurrent.futures.Future | None = None

    def on_any_event(self, event):
        if event.is_directory:
            return
        if not str(event.src_path).endswith(".md"):
            return
        try:
            if self._pending and not self._pending.done():
                self._pending.cancel()
            self._pending = asyncio.run_coroutine_threadsafe(
                self._debounced_sync(
                    changed_path=Path(event.src_path),
                    event_type=event.event_type,
                ),
                self.loop,
            )
        except RuntimeError as e:
            log.error("Watcher: Event-Loop nicht verfügbar für '%s': %s", self.wiki, e)

    def on_deleted(self, event):
        if event.is_directory or self.matrix_indexer is None:
            return
        if not str(event.src_path).endswith(".md"):
            return
        try:
            rel = Path(event.src_path).relative_to(wiki_path(self.wiki))
            doc_id = str(rel.with_suffix("")).replace("\\", "/")
            self.matrix_indexer.remove_document(self.wiki, doc_id)
        except Exception as e:
            log.warning("Watcher: Matrix-Remove für '%s' fehlgeschlagen: %s", event.src_path, e)

    async def _debounced_sync(self, changed_path: Path | None = None, event_type: str = "modified"):
        await asyncio.sleep(2.0)
        log.info("Watcher: change in wiki '%s' -> sync", self.wiki)
        if event_type in ("created", "modified"):
            _index_changed_file(self.wiki, changed_path, self.matrix_indexer)
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                if self.matrix_indexer is not None:
                    await do_matrix_sync_async(
                        self.wiki, force=False, matrix_indexer=self.matrix_indexer
                    )
                else:
                    await do_sync_async(self.wiki, force=False)
                return
            except Exception as e:
                log.warning("Watcher sync Versuch %d/%d für '%s' fehlgeschlagen: %s", attempt, max_retries, self.wiki, e)
                if attempt < max_retries:
                    await asyncio.sleep(3.0 * attempt)
        log.error("Watcher: Sync für '%s' nach %d Versuchen aufgegeben", self.wiki, max_retries)


def start_watchers(
    loop: asyncio.AbstractEventLoop,
    wiki_slugs: list[str] | None = None,
    matrix_indexer=None,
) -> list[Observer]:
    """Start file watchers for all or specified wikis."""
    if wiki_slugs is None:
        from core.config import list_wikis
        wikis = list_wikis() or [{"slug": "main"}]
        wiki_slugs = [w.get("slug", "main") for w in wikis]

    observers = []
    for slug in wiki_slugs:
        path = wiki_path(slug, create=False)
        if not path.exists():
            log.warning("Watcher: wiki path '%s' not found, skipping", path)
            continue
        handler = WikiChangeHandler(slug, loop, matrix_indexer=matrix_indexer)
        obs = Observer()
        obs.schedule(handler, str(path), recursive=True)
        obs.start()
        observers.append(obs)
        log.info("Watcher started for wiki '%s'", slug)
    if matrix_indexer is not None:
        log.info("Watcher: Matrix-Indexierung aktiviert")
    else:
        log.info("Watcher: Matrix-Indexierung deaktiviert")
    return observers
