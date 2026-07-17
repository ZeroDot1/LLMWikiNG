"""LLMWikiNG – Sync-Logik (qmd embed, index.md, Logbuch).

Portiert aus llmWiki.py.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime

from core.config import WIKI_DIR, PROJECT_ROOT, QMD_BIN, wiki_path
from services.wiki import get_all_wiki_pages
from services.cache import get_cache

LAST_SYNC_TIME: dict[str, object] = {}


def is_sync_needed(wiki: str = "main") -> bool:
    """Prüft, ob seit dem letzten Sync neue/geänderte Dateien im Wiki sind."""
    global LAST_SYNC_TIME
    last = LAST_SYNC_TIME.get(wiki)
    if last is None:
        return True
    root = wiki_path(wiki)
    if not root.exists():
        return False
    for f in root.rglob("*.md"):
        if f.stem in ("index", "log", "ingestlater"):
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime > last:
            return True
    from core.config import RAW_DIR

    if RAW_DIR.exists():
        for f in RAW_DIR.iterdir():
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime > last:
                    return True
    return False


def set_last_sync(value: datetime | None = None, wiki: str = "main") -> None:
    global LAST_SYNC_TIME
    LAST_SYNC_TIME[wiki] = value or datetime.now()


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


def regenerate_index(wiki: str = "main") -> bool:
    """Baut <wiki>/index.md aus allen vorhandenen Seiten neu auf."""
    idx_path = wiki_path(wiki) / "index.md"
    pages = get_all_wiki_pages(wiki)

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


def do_sync(wiki: str = "main") -> dict:
    """Vollständiger Sync: qmd embed + index.md regenerieren + timestamp setzen."""
    global LAST_SYNC_TIME
    results = {"qmd": False, "index": False, "messages": []}

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

    LAST_SYNC_TIME[wiki] = datetime.now()

    try:
        append_okf_log("sync", "Webserver-Sync", f"qmd: {'ok' if qmd_ok else 'err'} | index: {'ok' if results['index'] else 'err'}", wiki)
    except Exception:
        pass

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
