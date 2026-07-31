"""LLMWikiNG – Sync-Logik (qmd embed, index.md, Logbuch).

Portiert aus llmWiki.py.
"""

import asyncio
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.config import WIKI_DIR, PROJECT_ROOT, QMD_BIN, wiki_path, DATA_DIR, load_app_config
from services.wiki import get_all_wiki_pages
from services.cache import get_cache

log = logging.getLogger("llmwiking.sync")

SYNC_STATUS_FILE = DATA_DIR / "sync_status.json"
SYNC_CACHE_FILENAME = ".sync_cache.json"
SYSTEM_STEMS = {"index", "log", "ingestlater"}


def get_qmd_timeout() -> int:
    """Liefert den konfigurierbaren QMD Embed Timeout (Default: 180s)."""
    cfg = load_app_config()
    try:
        val = int(cfg.get("qmd_embed_timeout", 180))
        return val if val > 0 else 180
    except (ValueError, TypeError):
        return 180


@dataclass
class SyncStatus:
    wiki: str = ""
    qmd: bool = False
    index: bool = False
    messages: list[str] = field(default_factory=list)
    skipped: bool = False
    duration_ms: int = 0
    content_hash: str | None = None
    last_success: str | None = None
    last_attempt: str | None = None
    error: str | None = None
    pages_count: int = 0

    @property
    def success(self) -> bool:
        return self.qmd and self.index

    @property
    def summary(self) -> str:
        if self.skipped:
            return "Sync not needed (no changes)"
        parts = []
        parts.append(f"qmd: {'ok' if self.qmd else 'err'}")
        parts.append(f"index: {'ok' if self.index else 'err'}")
        return ", ".join(parts)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def load(cls, wiki: str) -> "SyncStatus":
        p = DATA_DIR / "sync_status"
        p.mkdir(parents=True, exist_ok=True)
        f = p / f"{wiki}.json"
        if f.exists():
            try:
                import json, dataclasses
                data = json.loads(f.read_text(encoding="utf-8"))
                known_fields = {field.name for field in dataclasses.fields(cls)}
                filtered = {k: v for k, v in data.items() if k in known_fields}
                return cls(**filtered)
            except Exception:
                pass
        return cls(wiki=wiki)

    def save(self) -> None:
        import json
        p = DATA_DIR / "sync_status"
        p.mkdir(parents=True, exist_ok=True)
        f = p / f"{self.wiki}.json"
        f.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

def _load_sync_times() -> dict[str, str]:
    if SYNC_STATUS_FILE.exists():
        try:
            import json
            return json.loads(SYNC_STATUS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("sync_status.json fehlerhaft: %s", e)
            return {}
    return {}

def _save_sync_times(times: dict[str, str]) -> None:
    try:
        import json
        SYNC_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SYNC_STATUS_FILE.write_text(json.dumps(times, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("Konnte sync_status.json nicht schreiben: %s", e)

def _wiki_sync_hash_file(wiki: str = "main") -> Path:
    """Pfad zur Hash-Statusdatei im Wiki-Verzeichnis (ohne unerwünschtes mkdir)."""
    return wiki_path(wiki, create=False) / ".sync_hash"

def _load_wiki_sync_hash(wiki: str = "main") -> str | None:
    p = _wiki_sync_hash_file(wiki)
    try:
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return None

def _save_wiki_sync_hash(wiki: str = "main", value: str = "") -> None:
    p = _wiki_sync_hash_file(wiki)
    try:
        p.write_text(value, encoding="utf-8")
    except Exception as e:
        log.warning("Konnte .sync_hash für Wiki '%s' nicht schreiben: %s", wiki, e)

def _wiki_content_hash(wiki: str = "main") -> str:
    """Berechnet einen Hash über alle relevanten Wiki-Dateien (ohne index/log)."""
    import hashlib
    root = wiki_path(wiki, create=False)
    h = hashlib.sha256()
    if root.exists():
        try:
            files = sorted(root.rglob("*.md"))
        except OSError as e:
            log.warning("rglob fehlgeschlagen für Wiki '%s': %s", wiki, e)
            files = []
        for f in files:
            if f.stem in SYSTEM_STEMS:
                continue
            try:
                h.update(f.relative_to(root).as_posix().encode("utf-8"))
                h.update(f.read_bytes())
            except OSError as e:
                log.warning("Datei '%s' nicht lesbar für Hash: %s", f, e)
                pass
    return h.hexdigest()

def _sync_cache_path(wiki: str = "main") -> Path:
    return wiki_path(wiki, create=False) / SYNC_CACHE_FILENAME


def _load_sync_cache(wiki: str = "main", default: dict | None = None) -> dict:
    p = _sync_cache_path(wiki)
    if p.exists():
        try:
            import json
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default or {"version": 1, "fingerprints": {}, "mtimes": {}, "last_sync": None}


def _save_sync_cache(cache: dict, wiki: str = "main") -> None:
    p = _sync_cache_path(wiki)
    try:
        import json
        p.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning(".sync_cache.json nicht schreibbar: %s", e)


def _compute_blake2b_fingerprint(file_path: Path) -> str | None:
    import hashlib
    try:
        h = hashlib.blake2b(digest_size=16)
        h.update(file_path.read_bytes())
        return h.hexdigest()
    except Exception:
        return None


def _compute_file_fingerprints(wiki: str = "main") -> tuple[dict[str, str], dict[str, str]]:
    """Gibt (fingerprints, mtimes) für alle relevanten .md Dateien zurück."""
    root = wiki_path(wiki, create=False)
    fps: dict[str, str] = {}
    mtimes: dict[str, str] = {}
    if root.exists():
        try:
            files = sorted(root.rglob("*.md"))
        except OSError:
            return fps, mtimes
        for f in files:
            if f.stem in SYSTEM_STEMS:
                continue
            try:
                stat = f.stat()
                mtimes[f.name] = f"{stat.st_mtime_ns}:{stat.st_size}"
            except OSError:
                pass
            fp = _compute_blake2b_fingerprint(f)
            if fp:
                fps[f.name] = fp
    return fps, mtimes


def _get_changed_files(wiki: str = "main") -> tuple[list[str], list[str], list[str]]:
    """Returns (added, changed, removed) file lists since last sync."""
    cache = _load_sync_cache(wiki)
    old_fps = cache.get("fingerprints", {})
    new_fps, _ = _compute_file_fingerprints(wiki)

    added = [f for f in new_fps if f not in old_fps]
    removed = [f for f in old_fps if f not in new_fps]
    changed = [f for f in new_fps if f in old_fps and new_fps[f] != old_fps[f]]

    return added, changed, removed


def get_last_sync(wiki: str = "main") -> datetime | None:
    times = _load_sync_times()
    val = times.get(wiki)
    if val:
        try:
            return datetime.fromisoformat(val)
        except Exception:
            return None
    return None

def is_sync_needed(wiki: str = "main") -> bool:
    """Prüft, ob seit dem letzten Sync neue/geänderte Dateien im Wiki sind."""
    root = wiki_path(wiki, create=False)
    if not root.exists():
        return False

    cache = _load_sync_cache(wiki)
    old_fps = cache.get("fingerprints", {})
    old_mtimes = cache.get("mtimes", {})

    # Phase 1: Schneller mtime/size Vergleich vor teurem Hashing
    current_mtimes = {}
    try:
        for f in root.rglob("*.md"):
            if f.stem in SYSTEM_STEMS:
                continue
            try:
                stat = f.stat()
                current_mtimes[f.name] = f"{stat.st_mtime_ns}:{stat.st_size}"
            except OSError:
                pass
    except OSError:
        return True

    if old_fps and old_mtimes:
        if set(current_mtimes.keys()) != set(old_mtimes.keys()):
            return True
        if all(old_mtimes.get(name) == mtime_key for name, mtime_key in current_mtimes.items()):
            return False

    # Phase 2: Hash-Vergleich
    if not old_fps:
        last_hash = _load_wiki_sync_hash(wiki)
        if last_hash is None:
            times = _load_sync_times()
            last_hash = times.get(f"{wiki}::hash")
        if last_hash is None:
            log.info("Kein Sync-Status für Wiki '%s' -> Sync empfohlen", wiki)
            return True
        try:
            current_hash = _wiki_content_hash(wiki)
            return current_hash != last_hash
        except Exception as e:
            log.error("Hash für Wiki '%s' nicht berechenbar: %s", wiki, e)
            return True

    try:
        new_fps, _ = _compute_file_fingerprints(wiki)
    except Exception as e:
        log.error("Fingerprints für Wiki '%s' nicht berechenbar: %s", wiki, e)
        return True

    return old_fps != new_fps

async def is_sync_needed_async(wiki: str = "main") -> bool:
    """Async-Variante von :func:`is_sync_needed`."""
    return await asyncio.to_thread(is_sync_needed, wiki)

def set_last_sync(value: datetime | None = None, wiki: str = "main") -> None:
    times = _load_sync_times()
    base = value or datetime.now(timezone.utc)
    times[wiki] = base.isoformat()

    content_hash: str | None = None
    try:
        content_hash = _wiki_content_hash(wiki)
    except Exception as e:
        log.error("Hash-Berechnung für Wiki '%s' fehlgeschlagen: %s", wiki, e)

    if content_hash is not None:
        times[f"{wiki}::hash"] = content_hash
        _save_wiki_sync_hash(wiki, content_hash)

    _save_sync_times(times)

def run_qmd_embed(wiki: str = "main") -> tuple[bool, str]:
    """Führt qmd embed aus. Gibt (success, message) zurück."""
    timeout = get_qmd_timeout()
    try:
        import os
        from core.config import wiki_path
        env = os.environ.copy()
        env["WIKI_DIR"] = str(wiki_path(wiki))
        env["COLLECTION_NAME"] = f"wiki_{wiki}"
        result = subprocess.run(
            [QMD_BIN, "embed"],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(PROJECT_ROOT), env=env
        )
        if result.returncode == 0:
            return True, "qmd-Embeddings aktualisiert"
        return False, result.stderr.strip() or "qmd embed fehlgeschlagen"
    except FileNotFoundError:
        return False, "qmd nicht installiert"
    except subprocess.TimeoutExpired:
        return False, f"qmd embed Zeitüberschreitung (>{timeout}s)"
    except Exception as e:
        return False, str(e)

async def run_qmd_embed_async(wiki: str = "main") -> tuple[bool, str]:
    """Async-Variante von :func:`run_qmd_embed`."""
    timeout = get_qmd_timeout()
    try:
        import os
        from core.config import wiki_path
        env = os.environ.copy()
        env["WIKI_DIR"] = str(wiki_path(wiki))
        env["COLLECTION_NAME"] = f"wiki_{wiki}"
        process = await asyncio.create_subprocess_exec(
            QMD_BIN, "embed",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            env=env
        )
        
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=float(timeout)
            )
            returncode = process.returncode
        except asyncio.TimeoutExpired:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return False, f"qmd embed Zeitüberschreitung (>{timeout}s)"
            
        stdout = stdout_bytes.decode(encoding="utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode(encoding="utf-8", errors="replace").strip()
        
        if returncode == 0:
            return True, "qmd-Embeddings aktualisiert"
        return False, stderr or stdout or "qmd embed fehlgeschlagen"
    except FileNotFoundError:
        return False, "qmd nicht installiert"
    except Exception as e:
        return False, str(e)

def regenerate_index(wiki: str = "main") -> bool:
    """Baut <wiki>/index.md aus allen vorhandenen Seiten neu auf."""
    from services.wiki import _get_all_wiki_pages_uncached

    idx_path = wiki_path(wiki) / "index.md"
    pages = _get_all_wiki_pages_uncached(wiki)

    lines = [
        "---",
        'okf_version: "0.1"',
        "---",
        "# Wiki-Index",
        "",
        "> Automatisch gepflegtes Inhaltsverzeichnis.",
        f"> Aktualisiert am {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        "## Inhaltsverzeichnis",
        "",
    ]

    pages_by_type: dict[str, list[dict]] = {}
    for p in pages:
        ptype = p["type"].title()
        pages_by_type.setdefault(ptype, []).append(p)

    for ptype, type_pages in sorted(pages_by_type.items()):
        lines.append(f"### {ptype}")
        lines.append("")
        for p in type_pages:
            lines.append(f"* [{p['title']}](./{p['slug']}.md) - {p['desc']}")
        lines.append("")

    if not pages:
        lines.append("_Noch keine Seiten im Wiki._")

    lines += [
        "",
        "## Statistik",
        "",
        f"- **Seiten gesamt:** {len(pages)}",
        f"- **Letzte Aktualisierung:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
    ]

    idx_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def sync_tags_for_wiki(wiki: str = "main") -> int:
    """Scannet alle Seiten im Wiki, generiert automatisch fehlende Tags im Frontmatter und aktualisiert data/tags.json."""
    from services.tags import extract_tags, auto_generate_tags_for_content, build_tag_index
    from services.editor import ensure_okf_frontmatter

    root = wiki_path(wiki, create=False)
    if not root.exists():
        return 0

    updated_count = 0
    for f in root.rglob("*.md"):
        if f.stem in SYSTEM_STEMS:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            tags = extract_tags(content)
            if not tags:
                title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                title = title_match.group(1) if title_match else f.stem
                new_tags = auto_generate_tags_for_content(content, title=title, wiki=wiki)
                if new_tags:
                    new_content = ensure_okf_frontmatter(content, title=title, tags=new_tags, updated_by="sync")
                    f.write_text(new_content, encoding="utf-8")
                    updated_count += 1
        except Exception as e:
            log.warning("Fehler beim Auto-Tagging der Datei %s: %s", f.name, e)

    build_tag_index(wiki, force_rebuild=True)
    return updated_count

def _get_pages_count(wiki: str) -> int:
    root = wiki_path(wiki, create=False)
    if not root.exists():
        return 0
    return len([f for f in root.rglob("*.md") if f.stem not in SYSTEM_STEMS])

def do_sync(wiki: str = "main", force: bool = False) -> dict:
    """Vollständiger Sync: qmd embed + index.md regenerieren + timestamp setzen."""
    import time as _time
    _start = _time.monotonic()
    status = SyncStatus.load(wiki)
    status.wiki = wiki
    status.last_attempt = datetime.now(timezone.utc).isoformat()

    if not is_sync_needed(wiki) and not force:
        status.qmd = True
        status.index = True
        status.skipped = True
        status.messages.append("Sync not needed (no changes)")
        status.duration_ms = int((_time.monotonic() - _start) * 1000)
        status.pages_count = _get_pages_count(wiki)
        status.save()
        return {
            "qmd": status.qmd,
            "index": status.index,
            "messages": status.messages,
            "skipped": status.skipped,
            "duration_ms": status.duration_ms,
            "_status": status,
        }

    added, changed, removed = _get_changed_files(wiki)
    if added:
        status.messages.append(f"Neue Seiten: {', '.join(added)}")
    if changed:
        status.messages.append(f"Geänderte Seiten: {', '.join(changed)}")
    if removed:
        status.messages.append(f"Gelöschte Seiten: {', '.join(removed)}")

    qmd_ok, qmd_msg = run_qmd_embed(wiki)
    status.qmd = qmd_ok
    status.messages.append(qmd_msg)

    try:
        regenerate_index(wiki)
        status.index = True
        status.messages.append("index.md neu aufgebaut")
    except Exception as e:
        status.messages.append(f"index.md Fehler: {e}")

    try:
        updated_tags_count = sync_tags_for_wiki(wiki)
        if updated_tags_count > 0:
            status.messages.append(f"Tags für {updated_tags_count} Seite(n) automatisch generiert und indiziert")
        else:
            status.messages.append("Tag-Index in data/tags.json aktualisiert")
    except Exception as e:
        status.messages.append(f"Tag-Sync Fehler: {e}")

    if qmd_ok and status.index:
        _cache = get_cache()
        _cache.invalidate_prefix(f"pages:{wiki}")
        _cache.invalidate(f"graph:{wiki}")
        _cache.invalidate_prefix(f"tags:{wiki}")

    try:
        append_okf_log("sync", "Webserver-Sync", f"qmd: {'ok' if qmd_ok else 'err'} | index: {'ok' if status.index else 'err'}", wiki)
    except Exception:
        pass

    set_last_sync(datetime.now(timezone.utc), wiki)

    fps, mtimes = _compute_file_fingerprints(wiki)
    _save_sync_cache({
        "version": 1,
        "fingerprints": fps,
        "mtimes": mtimes,
        "last_sync": datetime.now(timezone.utc).isoformat(),
    }, wiki)

    status.duration_ms = int((_time.monotonic() - _start) * 1000)
    status.last_success = datetime.now(timezone.utc).isoformat()
    status.pages_count = _get_pages_count(wiki)
    status.save()

    return {
        "qmd": status.qmd,
        "index": status.index,
        "messages": status.messages,
        "skipped": status.skipped,
        "duration_ms": status.duration_ms,
        "_status": status,
    }

async def do_sync_async(wiki: str = "main", force: bool = False) -> dict:
    """Async-Variante von :func:`do_sync`."""
    import time as _time
    _start = _time.monotonic()
    status = SyncStatus.load(wiki)
    status.wiki = wiki
    status.last_attempt = datetime.now(timezone.utc).isoformat()

    lock = await get_wiki_lock(wiki)
    async with lock:
        needed = await is_sync_needed_async(wiki)
        if not needed and not force:
            status.qmd = True
            status.index = True
            status.skipped = True
            status.messages.append("Sync not needed (no changes)")
            status.duration_ms = int((_time.monotonic() - _start) * 1000)
            status.pages_count = await asyncio.to_thread(_get_pages_count, wiki)
            await asyncio.to_thread(status.save)
            return {
                "qmd": status.qmd,
                "index": status.index,
                "messages": status.messages,
                "skipped": status.skipped,
                "duration_ms": status.duration_ms,
                "_status": status,
            }

        added, changed, removed = await asyncio.to_thread(_get_changed_files, wiki)
        if added:
            status.messages.append(f"Neue Seiten: {', '.join(added)}")
        if changed:
            status.messages.append(f"Geänderte Seiten: {', '.join(changed)}")
        if removed:
            status.messages.append(f"Gelöschte Seiten: {', '.join(removed)}")

        qmd_ok, qmd_msg = await run_qmd_embed_async(wiki)
        status.qmd = qmd_ok
        status.messages.append(qmd_msg)

        try:
            await asyncio.to_thread(regenerate_index, wiki)
            status.index = True
            status.messages.append("index.md neu aufgebaut")
        except Exception as e:
            status.messages.append(f"index.md Fehler: {e}")

        try:
            updated_tags_count = await asyncio.to_thread(sync_tags_for_wiki, wiki)
            if updated_tags_count > 0:
                status.messages.append(f"Tags für {updated_tags_count} Seite(n) automatisch generiert und indiziert")
            else:
                status.messages.append("Tag-Index in data/tags.json aktualisiert")
        except Exception as e:
            status.messages.append(f"Tag-Sync Fehler: {e}")

        if qmd_ok and status.index:
            _cache = get_cache()
            _cache.invalidate_prefix(f"pages:{wiki}")
            _cache.invalidate(f"graph:{wiki}")
            _cache.invalidate_prefix(f"tags:{wiki}")

        try:
            log_msg = f"qmd: {'ok' if qmd_ok else 'err'} | index: {'ok' if status.index else 'err'}"
            await asyncio.to_thread(
                append_okf_log,
                "sync",
                "Webserver-Sync",
                log_msg,
                wiki
            )
        except Exception:
            pass

        await asyncio.to_thread(set_last_sync, datetime.now(timezone.utc), wiki)

        fps, mtimes = await asyncio.to_thread(_compute_file_fingerprints, wiki)
        await asyncio.to_thread(_save_sync_cache, {
            "version": 1,
            "fingerprints": fps,
            "mtimes": mtimes,
            "last_sync": datetime.now(timezone.utc).isoformat(),
        }, wiki)

        status.duration_ms = int((_time.monotonic() - _start) * 1000)
        status.last_success = datetime.now(timezone.utc).isoformat()
        status.pages_count = await asyncio.to_thread(_get_pages_count, wiki)
        await asyncio.to_thread(status.save)

        return {
            "qmd": status.qmd,
            "index": status.index,
            "messages": status.messages,
            "skipped": status.skipped,
            "duration_ms": status.duration_ms,
            "_status": status,
        }

def append_okf_log(action: str, title: str, details: str = "", wiki: str = "main") -> None:
    """Schreibt einen OKF-konformen Logbucheintrag (## YYYY-MM-DD mit Bullets)."""
    log_path = wiki_path(wiki) / "log.md"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    action_type = "Update"
    if action.lower() in ("ingest", "create", "creation"):
        action_type = "Creation"
    elif action.lower() in ("delete", "remove", "deprecation"):
        action_type = "Deprecation"

    log_entry = f"* **{action_type}**: {title}"
    if details:
        log_entry += f" - {details}"

    if not log_path.exists():
        log_path.write_text(
            f"---\n"
            f'okf_version: "0.1"\n'
            f"---\n"
            f"# Wiki-Aktivitätslogbuch\n\n"
            f"## {today_str}\n"
            f"{log_entry}\n",
            encoding="utf-8",
        )
        return

    content = log_path.read_text(encoding="utf-8")

    if not content.startswith("---"):
        content = (
            f"---\n"
            f'okf_version: "0.1"\n'
            f"---\n"
            f"# Wiki-Aktivitätslogbuch\n\n"
            f"{content.strip()}\n"
        )

    header = f"## {today_str}"
    if header in content:
        pos = content.find(header) + len(header)
        eol = content.find("\n", pos)
        if eol == -1:
            eol = len(content)
        new_content = content[:eol] + f"\n{log_entry}" + content[eol:]
    else:
        new_content = content.rstrip() + f"\n\n{header}\n{log_entry}\n"

    log_path.write_text(new_content, encoding="utf-8")


_wiki_locks: dict[str, asyncio.Lock] = {}
_wiki_locks_lock = asyncio.Lock()

async def get_wiki_lock(wiki: str) -> asyncio.Lock:
    """Liefert das asynchrone Lock für ein bestimmtes Wiki."""
    async with _wiki_locks_lock:
        if wiki not in _wiki_locks:
            _wiki_locks[wiki] = asyncio.Lock()
        return _wiki_locks[wiki]

_active_syncs: set[str] = set()
_pending_syncs: set[str] = set()
_pending_force: set[str] = set()
_sync_state_lock = asyncio.Lock()

async def _run_bg_sync_loop(wiki: str) -> None:
    """Interne Schleife, die den Hintergrund-Sync für ein Wiki ausführt und ggf. wiederholt."""
    while True:
        async with _sync_state_lock:
            force = wiki in _pending_force
            _pending_force.discard(wiki)
        try:
            await do_sync_async(wiki, force=force)
        except Exception:
            pass
        
        async with _sync_state_lock:
            if wiki in _pending_syncs:
                _pending_syncs.discard(wiki)
            else:
                _active_syncs.discard(wiki)
                break

def request_sync_background(wiki: str = "main", force: bool = False) -> None:
    """Fordert einen Wiki-Sync im Hintergrund an (nicht-blockierend)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(_trigger_bg_sync(wiki, force=force))
    else:
        import threading
        t = threading.Thread(
            target=do_sync, args=(wiki,), kwargs={"force": force},
            daemon=True, name=f"sync-{wiki}"
        )
        t.start()

async def _trigger_bg_sync(wiki: str, force: bool = False) -> None:
    """Hilfsfunktion, um die Hintergrundschleife atomar zu starten."""
    async with _sync_state_lock:
        if wiki in _active_syncs:
            if force:
                _pending_force.add(wiki)
            _pending_syncs.add(wiki)
            return
        _active_syncs.add(wiki)
        if force:
            _pending_force.add(wiki)
    
    await _run_bg_sync_loop(wiki)

