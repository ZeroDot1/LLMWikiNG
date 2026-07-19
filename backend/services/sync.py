"""LLMWikiNG – Sync-Logik (qmd embed, index.md, Logbuch).

Portiert aus llmWiki.py.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from core.config import WIKI_DIR, PROJECT_ROOT, QMD_BIN, wiki_path, DATA_DIR
from services.wiki import get_all_wiki_pages
from services.cache import get_cache

# Persistenter Sync-Status
SYNC_STATUS_FILE = DATA_DIR / "sync_status.json"

def _load_sync_times() -> dict[str, str]:
    if SYNC_STATUS_FILE.exists():
        try:
            import json
            return json.loads(SYNC_STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_sync_times(times: dict[str, str]) -> None:
    try:
        import json
        SYNC_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SYNC_STATUS_FILE.write_text(json.dumps(times, indent=2), encoding="utf-8")
    except Exception:
        # Fallback: DATA_DIR evtl. nicht beschreibbar (read-only Mount im Container).
        # In diesem Fall bleibt der Hash-Vergleich deaktiviert; is_sync_needed
        # greift dann auf den mtime-Fallback zurück (siehe unten).
        pass

def _wiki_sync_hash_file(wiki: str = "main") -> "Path":
    """Pfad zur Hash-Statusdatei im Wiki-Verzeichnis.

    Wird als robuste Alternative zu ``SYNC_STATUS_FILE`` (DATA_DIR) genutzt,
    weil das Wiki-Verzeichnis im Container garantiert gemountet und beschreibbar
    ist – im Gegensatz zu DATA_DIR, das bei read-only Mounts nicht geschrieben
    werden kann (was sonst zu einem permanenten "Sync empfohlen" führte).
    """
    return wiki_path(wiki) / ".sync_hash"

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
    except Exception:
        pass

def _wiki_content_hash(wiki: str = "main") -> str:
    """Berechnet einen Hash über alle relevanten Wiki-Dateien (ohne index/log).

    Wird genutzt, um Änderungen unabhängig von Datei-mtimes (die bei
    Host/Container-Zeitverschiebungen unzuverlässig sind) zu erkennen.
    """
    import hashlib
    root = wiki_path(wiki)
    h = hashlib.sha256()
    if root.exists():
        for f in sorted(root.rglob("*.md")):
            if f.stem in ("index", "log", "ingestlater"):
                continue
            try:
                h.update(f.relative_to(root).as_posix().encode("utf-8"))
                h.update(f.read_bytes())
            except OSError:
                pass
    return h.hexdigest()

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
    """Prüft, ob seit dem letzten Sync neue/geänderte Dateien im Wiki sind.

    Nutzt einen **Hash-basierten** Vergleich der Wiki-Inhalte (statt mtime),
    um Zeitverschiebungen zwischen Host und Container (verschiedene Zeitzonen/
    Clocks) zu umgehen. Ein frisch gelaufener Sync setzt den Referenz-Hash, sodass
    danach kein falsches "Sync empfohlen" mehr erscheint.

    Der Hash wird primär in ``SYNC_STATUS_FILE`` (DATA_DIR) gespeichert und als
    robuster Fallback zusätzlich in ``.sync_hash`` im Wiki-Verzeichnis selbst
    (garantiert gemountet/beschreibbar im Container).
    """
    # 1. Hash aus Wiki-Verzeichnis (robuster Fallback)
    last_hash = _load_wiki_sync_hash(wiki)
    # 2. Fallback auf DATA_DIR-basierten Hash
    if last_hash is None:
        times = _load_sync_times()
        last_hash = times.get(f"{wiki}::hash")
    if last_hash is None:
        # Kein bekannter Sync-Zustand -> Sync empfohlen
        return True
    try:
        current_hash = _wiki_content_hash(wiki)
    except Exception:
        return True
    return current_hash != last_hash

async def is_sync_needed_async(wiki: str = "main") -> bool:
    """Async-Variante von :func:`is_sync_needed`."""
    return await asyncio.to_thread(is_sync_needed, wiki)

def set_last_sync(value: datetime | None = None, wiki: str = "main") -> None:
    times = _load_sync_times()
    # Zeitstempel für Anzeige-Zwecke (mit 1h Puffer für Robustheit)
    import datetime as dt
    base = value or dt.datetime.now()
    ref_time = base + dt.timedelta(seconds=3600)
    times[wiki] = ref_time.isoformat()
    # Hash der Wiki-Inhalte speichern, damit is_sync_needed hash-basiert
    # (zeitverschiebungs-unabhängig) erkennen kann, ob sich etwas geändert hat.
    try:
        content_hash = _wiki_content_hash(wiki)
        times[f"{wiki}::hash"] = content_hash
        # Robuster Fallback: Hash zusätzlich im Wiki-Verzeichnis speichern
        # (garantiert gemountet/beschreibbar, auch wenn DATA_DIR read-only ist).
        _save_wiki_sync_hash(wiki, content_hash)
    except Exception:
        pass
    _save_sync_times(times)

def run_qmd_embed(wiki: str = "main") -> tuple[bool, str]:
    """Führt qmd embed aus. Gibt (success, message) zurück."""
    try:
        import os
        from core.config import wiki_path
        env = os.environ.copy()
        env["WIKI_DIR"] = str(wiki_path(wiki))
        env["COLLECTION_NAME"] = f"wiki_{wiki}"
        result = subprocess.run(
            [QMD_BIN, "embed"],
            capture_output=True, text=True, timeout=60,
            cwd=str(PROJECT_ROOT), env=env
        )
        if result.returncode == 0:
            return True, "qmd-Embeddings aktualisiert"
        return False, result.stderr.strip() or "qmd embed fehlgeschlagen"
    except FileNotFoundError:
        return False, "qmd nicht installiert"
    except subprocess.TimeoutExpired:
        return False, "qmd embed Zeitüberschreitung (>60s)"
    except Exception as e:
        return False, str(e)

async def run_qmd_embed_async(wiki: str = "main") -> tuple[bool, str]:
    """Async-Variante von :func:`run_qmd_embed`.

    Nutzt asyncio.create_subprocess_exec für echte asynchrone Prozesssteuerung
    ohne Blockieren von Threads.
    """
    try:
        import os
        from core.config import wiki_path
        env = os.environ.copy()
        env["WIKI_DIR"] = str(wiki_path(wiki))
        env["COLLECTION_NAME"] = f"wiki_{wiki}"
        
        # Start command asynchronously
        process = await asyncio.create_subprocess_exec(
            QMD_BIN, "embed",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            env=env
        )
        
        try:
            # 60s timeout
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=60.0
            )
            returncode = process.returncode
        except asyncio.TimeoutExpired:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return False, "qmd embed Zeitüberschreitung (>60s)"
            
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
    """Baut <wiki>/index.md aus allen vorhandenen Seiten neu auf.

    Nutzt bewusst die **un-cached** Variante ``_get_all_wiki_pages_uncached``,
    damit der Index garantiert *alle* physisch vorhandenen Seiten enthält –
    unabhängig von einem evtl. veralteten mtime-basierten Seiten-Cache. Sonst
    kann es passieren, dass neu hinzugefügte Seiten (z. B. per MCP geschrieben)
    im Index fehlen, obwohl sie auf der Platte liegen.
    """
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
        f"> Aktualisiert am {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Concepts",
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
        f"- **Letzte Aktualisierung:** {datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]

    idx_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True

def do_sync(wiki: str = "main", force: bool = False) -> dict:
    """Vollständiger Sync: qmd embed + index.md regenerieren + timestamp setzen."""
    results = {"qmd": False, "index": False, "messages": []}

    # Prüfen ob ein Sync nötig ist (außer force=True)
    if not is_sync_needed(wiki) and not force:
        results["qmd"] = True
        results["index"] = True
        results["messages"].append("Sync nicht benötigt (keine Änderungen)")
        return results

    # Cache für dieses Wiki sofort invalidieren, damit nach dem Sync
    # alle Leseanfragen frische Daten bekommen.
    _cache = get_cache()
    _cache.invalidate_prefix(f"pages:{wiki}")
    _cache.invalidate(f"graph:{wiki}")

    qmd_ok, qmd_msg = run_qmd_embed(wiki)
    results["qmd"] = qmd_ok
    results["messages"].append(qmd_msg)

    try:
        regenerate_index(wiki)
        results["index"] = True
        results["messages"].append("index.md neu aufgebaut")
    except Exception as e:
        results["messages"].append(f"index.md Fehler: {e}")

    try:
        append_okf_log("sync", "Webserver-Sync", f"qmd: {'ok' if qmd_ok else 'err'} | index: {'ok' if results['index'] else 'err'}", wiki)
    except Exception:
        pass

    # WICHTIG: set_last_sync nach allen Schreiboperationen (siehe do_sync_async)
    set_last_sync(datetime.now(), wiki)

    return results

async def do_sync_async(wiki: str = "main", force: bool = False) -> dict:
    """Async-Variante von :func:`do_sync`.

    Führt den Sync asynchron aus. Nutzt einen Mutex pro Wiki, um konkurrierende
    Ausführungen zu verhindern, und überspringt den Sync, falls keine Änderungen
    vorliegen (es sei denn, force=True).

    Args:
        wiki: Wiki-Slug, das synchronisiert wird.
        force: Erzwingt den Sync auch wenn keine Änderungen vorliegen.

    Returns:
        Dict {"qmd": bool, "index": bool, "messages": list[str]}
    """
    results = {"qmd": False, "index": False, "messages": []}

    lock = await get_wiki_lock(wiki)
    async with lock:
        needed = await is_sync_needed_async(wiki)
        if not needed and not force:
            results["qmd"] = True
            results["index"] = True
            results["messages"].append("Sync nicht benötigt (keine Änderungen)")
            return results

        _cache = get_cache()
        _cache.invalidate_prefix(f"pages:{wiki}")
        _cache.invalidate(f"graph:{wiki}")

        qmd_ok, qmd_msg = await run_qmd_embed_async(wiki)
        results["qmd"] = qmd_ok
        results["messages"].append(qmd_msg)

        try:
            await asyncio.to_thread(regenerate_index, wiki)
            results["index"] = True
            results["messages"].append("index.md neu aufgebaut")
        except Exception as e:
            results["messages"].append(f"index.md Fehler: {e}")

        try:
            log_msg = f"qmd: {'ok' if qmd_ok else 'err'} | index: {'ok' if results['index'] else 'err'}"
            await asyncio.to_thread(
                append_okf_log,
                "sync",
                "Webserver-Sync",
                log_msg,
                wiki
            )
        except Exception:
            pass

        # WICHTIG: set_last_sync MUSS nach allen Schreiboperationen (regenerate_index,
        # append_okf_log) erfolgen, damit last_sync nach allen Sync-Schreibvorgängen
        # liegt. Sonst meldet is_sync_needed sofort wieder "Sync empfohlen", weil
        # log.md/index.md nach last_sync geschrieben wurden.
        await asyncio.to_thread(set_last_sync, datetime.now(), wiki)

        return results

def append_okf_log(action: str, title: str, details: str = "", wiki: str = "main") -> None:
    """Schreibt einen OKF-konformen Logbucheintrag (## YYYY-MM-DD mit Bullets)."""
    log_path = wiki_path(wiki) / "log.md"
    today_str = datetime.now().strftime("%Y-%m-%d")

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


# ═══════════════════════════════════════════════════════════════════════════════
# ASYNCHRONES MUTEX LOCK- & HINTERGRUND-SYNC-SYSTEM (COALESCING QUEUE)
# ═══════════════════════════════════════════════════════════════════════════════

_wiki_locks: dict[str, asyncio.Lock] = {}
_wiki_locks_lock = asyncio.Lock()

async def get_wiki_lock(wiki: str) -> asyncio.Lock:
    """Liefert das asynchrone Lock für ein bestimmtes Wiki."""
    async with _wiki_locks_lock:
        if wiki not in _wiki_locks:
            _wiki_locks[wiki] = asyncio.Lock()
        return _wiki_locks[wiki]

# Zustandsvariablen für das Coalescing (Zusammenfassen) von Hintergrund-Sync-Tasks
_active_syncs: set[str] = set()
_pending_syncs: set[str] = set()
_pending_force: set[str] = set()
_sync_state_lock = asyncio.Lock()

async def _run_bg_sync_loop(wiki: str) -> None:
    """Interne Schleife, die den Hintergrund-Sync für ein Wiki ausführt und ggf. wiederholt."""
    while True:
        # Force-Flag für diesen Durchlauf aus den Pending-Daten lesen
        async with _sync_state_lock:
            force = wiki in _pending_force
            _pending_force.discard(wiki)
        try:
            await do_sync_async(wiki, force=force)
        except Exception:
            pass
        
        # Prüfen, ob während des Laufs ein weiterer Sync angefordert wurde
        async with _sync_state_lock:
            if wiki in _pending_syncs:
                _pending_syncs.discard(wiki)
                # Die Schleife läuft weiter für den nächsten Durchlauf
            else:
                _active_syncs.discard(wiki)
                break

def request_sync_background(wiki: str = "main", force: bool = False) -> None:
    """Fordert einen Wiki-Sync im Hintergrund an.
    
    Diese Funktion ist nicht-blockierend und kehrt sofort zurück. Wenn bereits
    ein Sync für das Wiki läuft, wird ein weiterer Sync vorgemerkt und automatisch
    nach dem aktuellen Lauf gestartet. Mehrere Anforderungen während eines Laufs
    werden zu einem einzigen Folge-Lauf zusammengefasst (Coalescing), was
    Ressourcen schont.

    Args:
        wiki: Slug des Wikis.
        force: Wenn True, wird der Sync erzwungen (index.md wird immer neu
            aufgebaut). Sollte bei expliziten Schreiboperationen (z. B. MCP
            okf_write_concept) gesetzt werden, damit neu hinzugefügte Seiten
            garantiert im Index landen.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(_trigger_bg_sync(wiki, force=force))
    else:
        # Kein laufender Loop (z.B. CLI/Skript-Kontext oder synchroner Thread) -> im Thread ausführen
        # Wir rufen do_sync synchron auf, um die Dateischnittstelle zu bedienen
        try:
            do_sync(wiki, force=force)
        except Exception:
            pass

async def _trigger_bg_sync(wiki: str, force: bool = False) -> None:
    """Hilfsfunktion, um die Hintergrundschleife atomar zu starten."""
    async with _sync_state_lock:
        if wiki in _active_syncs:
            # Force-Flag für den nachfolgenden Pending-Lauf merken
            if force:
                _pending_force.add(wiki)
            _pending_syncs.add(wiki)
            return
        _active_syncs.add(wiki)
        if force:
            _pending_force.add(wiki)
    
    # Hintergrund-Loop starten
    await _run_bg_sync_loop(wiki)
