"""LLMWikiNG – Background File-Watcher for wiki changes.

Uses watchdog to monitor wiki directories for .md file changes
and triggers incremental sync automatically with debounce.
"""

import asyncio
import concurrent.futures
import logging
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    Observer = object
    FileSystemEventHandler = object

from core.config import wiki_path
from services.sync import do_sync_async

log = logging.getLogger("llmwiking.watcher")


class WikiChangeHandler(FileSystemEventHandler):
    def __init__(self, wiki: str, loop: asyncio.AbstractEventLoop):
        self.wiki = wiki
        self.loop = loop
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
                self._debounced_sync(), self.loop
            )
        except RuntimeError as e:
            log.error("Watcher: Event-Loop nicht verfügbar für '%s': %s", self.wiki, e)

    async def _debounced_sync(self):
        await asyncio.sleep(2.0)
        log.info("Watcher: change in wiki '%s' -> sync", self.wiki)
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                await do_sync_async(self.wiki, force=False)
                return
            except Exception as e:
                log.warning("Watcher sync Versuch %d/%d für '%s' fehlgeschlagen: %s", attempt, max_retries, self.wiki, e)
                if attempt < max_retries:
                    await asyncio.sleep(3.0 * attempt)
        log.error("Watcher: Sync für '%s' nach %d Versuchen aufgegeben", self.wiki, max_retries)


def start_watchers(loop: asyncio.AbstractEventLoop, wiki_slugs: list[str] | None = None) -> list[Observer]:
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
        handler = WikiChangeHandler(slug, loop)
        obs = Observer()
        obs.schedule(handler, str(path), recursive=True)
        obs.start()
        observers.append(obs)
        log.info("Watcher started for wiki '%s'", slug)
    return observers

