# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Alle HTML-Routen, Form-POSTs und JSON-Endpoints.

Multi-Wiki-fähig, unter BASE_PATH gemountet und durch require_login geschützt.
"""

from __future__ import annotations

import asyncio
import os
import json
import re
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile as FastAPIUploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile
from fastapi.responses import JSONResponse

from core.config import (
    PROJECT_ROOT,
    WIKI_DIR,
    RAW_DIR,
    EXPORT_DIR,
    SCRATCH_DIR,
    APP_VERSION,
    BASE_PATH,
    CONFIG_FILE,
    DATA_DIR,
    load_app_config,
    slugify_wiki,
    wiki_path,
    list_wikis,
    save_wiki_meta,
    delete_wiki,
    MCP_TOOL_GROUPS,
)
from web import templates, render, abort, redirect, urlencode
from api.deps import require_login, require_admin, get_current_user
from services.audit import log_action, get_recent_audit_logs, ALL_CATEGORIES
from core.storage import list_users, list_keys, list_mcp_keys
from services.wiki import (
    get_all_wiki_pages,
    get_wiki_stats,
    read_wiki_file,
    is_text_file,
    find_wiki_slug_for_raw,
    get_pending_files,
    save_to_ingestlater,
    get_wiki_trails,
    extract_links_from_content,
    slugify_german,
    run_ingest_async,
    run_sync_async,
)
from services.markdown import render_markdown, render_markdown_preview
from services.search import matrix_search, local_search

from services.sync import is_sync_needed, append_okf_log, request_sync_background
from services.wiki import run_sync_async
from services.graph import build_graph_data, build_graph_data_paginated, build_graph_data_all
from services.lint import run_lint
from services.analytics import get_wiki_analytics
from services.editor import ensure_okf_frontmatter, detect_conflict
from services.email_sender import load_smtp_config, save_smtp_config, send_real_email

router = APIRouter(prefix=BASE_PATH, dependencies=[Depends(require_login)])


def _read_version() -> str:
    version_file = PROJECT_ROOT / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return APP_VERSION


def _highlight_text(text: str, query: str) -> str:
    import html

    if not query:
        return html.escape(text)
    escaped_text = html.escape(text)
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    return pattern.sub(lambda m: f'<mark class="search-highlight">{m.group(0)}</mark>', escaped_text)


def _parse_week_string(s: str):
    m = re.match(r"^(\d{4})-[Ww](\d{1,2})$", s.strip())
    if not m:
        raise ValueError()
    return int(m.group(1)), int(m.group(2))


def _default_wiki() -> str:
    wikis = list_wikis()
    slugs = [w.get("slug") for w in wikis if w.get("slug")]
    if "main" in slugs:
        return "main"
    return slugs[0] if slugs else "main"


@router.get("/")
def dashboard(request: Request):
    query = request.query_params.get("q", "").strip()
    if query:
        return redirect(f"{BASE_PATH}/search?q={urlencode(query)}")

    wikis = list_wikis()
    default = _default_wiki()

    wiki_stats = []
    total_pages = total_words = total_raw = total_export = 0
    for w in wikis:
        slug = w.get("slug") or w.get("name")
        s = get_wiki_stats(slug)
        wiki_stats.append({"name": w["name"], "slug": slug, "stats": s})
        total_pages += s["page_count"]
        total_words += s["word_count"]
        total_raw += s["raw_count"]
        total_export += s["export_count"]

    recent_logs = get_recent_audit_logs(5)
    return render(
        request, "dashboard.html",
        active_page="home",
        wikis=wikis,
        wiki_stats=wiki_stats,
        wiki_count=len(wikis),
        stats={
            "page_count": total_pages,
            "word_count": total_words,
            "raw_count": total_raw,
            "export_count": total_export,
        },
        recent_logs=recent_logs,
        sync_status=request.query_params.get("sync_status", ""),
        sync_msg=request.query_params.get("sync_msg", ""),
    )


@router.get("/settings/wikis/json")
def settings_wikis_list(request: Request):
    """JSON-Endpoint für Wiki-Liste (session-geschützt, kein API-Key nötig)."""
    return {"wikis": list_wikis()}


@router.post("/settings/wikis/json")
async def settings_wikis_create(request: Request):
    """JSON-Endpoint für Wiki-Erstellung (session-geschützt)."""
    user = require_login(request)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "detail": "Ungültiges JSON"})

    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip()
    description = (data.get("description") or "").strip()

    if not name or not slug:
        return JSONResponse(status_code=400, content={"ok": False, "detail": "Name und Slug sind erforderlich"})

    slug = slugify_wiki(slug)
    root = wiki_path(slug)
    if root.exists():
        return JSONResponse(status_code=409, content={"ok": False, "detail": f"Wiki '{slug}' existiert bereits"})

    root.mkdir(parents=True, exist_ok=True)
    (root / "index.md").write_text(
        f"---\nokf_version: \"0.1\"\n---\n# {name}\n\n> Wiki-Index von **{name}**.\n",
        encoding="utf-8",
    )
    (root / "log.md").write_text(
        f"---\nokf_version: \"0.1\"\n---\n# Wiki-Aktivitätslogbuch\n\n## {date.today().isoformat()}\n"
        f"- **Create**: Wiki '{name}' angelegt\n",
        encoding="utf-8",
    )

    save_wiki_meta({"slug": slug, "name": name, "description": description})
    log_action(action="wiki_create", details=f"Wiki '{name}' ({slug}) erstellt",
               username=user.get("username"), user_id=user.get("id"), request=request)
    return JSONResponse(status_code=201, content={"ok": True, "slug": slug})


@router.put("/settings/wikis/json/{slug}")
async def settings_wikis_update(slug: str, request: Request):
    """JSON-Endpoint für Wiki-Bearbeitung (session-geschützt)."""
    user = require_login(request)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "detail": "Ungültiges JSON"})

    new_name = (data.get("name") or "").strip()
    new_slug = (data.get("slug") or slug).strip()
    description = (data.get("description") or "").strip()

    if not new_name:
        return JSONResponse(status_code=400, content={"ok": False, "detail": "Name ist erforderlich"})

    new_slug = slugify_wiki(new_slug)
    old_root = wiki_path(slug)

    if not old_root.exists():
        return JSONResponse(status_code=404, content={"ok": False, "detail": f"Wiki '{slug}' nicht gefunden"})

    # Slug-Änderung → Verzeichnis umbenennen
    if new_slug != slug:
        new_root = wiki_path(new_slug)
        if new_root.exists():
            return JSONResponse(status_code=409, content={"ok": False, "detail": f"Slug '{new_slug}' bereits vergeben"})
        import shutil
        shutil.move(str(old_root), str(new_root))
        # Alten slug aus wikis.json entfernen + neuen eintragen
        from core.config import DATA_DIR, _atomic_write
        wikis_file = DATA_DIR / "wikis.json"
        if wikis_file.exists():
            wikis = json.loads(wikis_file.read_text(encoding="utf-8"))
            wikis = [w for w in wikis if w.get("slug") != slug]
            wikis.append({"slug": new_slug, "name": new_name, "description": description})
            _atomic_write(wikis_file, json.dumps(wikis, indent=2, ensure_ascii=False))
        else:
            save_wiki_meta({"slug": new_slug, "name": new_name, "description": description})
        log_action(action="wiki_rename", details=f"Wiki '{slug}' → '{new_slug}' umbenannt",
                   username=user.get("username"), user_id=user.get("id"), request=request)
    else:
        # Nur Name/Description aktualisieren
        from core.config import DATA_DIR, _atomic_write
        wikis_file = DATA_DIR / "wikis.json"
        if wikis_file.exists():
            wikis = json.loads(wikis_file.read_text(encoding="utf-8"))
            for w in wikis:
                if w.get("slug") == slug:
                    w["name"] = new_name
                    w["description"] = description
                    break
            _atomic_write(wikis_file, json.dumps(wikis, indent=2, ensure_ascii=False))
        log_action(action="wiki_update", details=f"Wiki '{slug}' aktualisiert",
                   username=user.get("username"), user_id=user.get("id"), request=request)

    return JSONResponse(content={"ok": True, "slug": new_slug})


@router.delete("/settings/wikis/json/{slug}")
async def settings_wikis_delete(slug: str, request: Request):
    """JSON-Endpoint für Wiki-Löschung (session-geschützt)."""
    user = require_login(request)

    if slug == "main":
        return JSONResponse(status_code=400, content={"ok": False, "detail": "Das Hauptwiki kann nicht gelöscht werden"})

    root = wiki_path(slug)
    if not root.exists():
        return JSONResponse(status_code=404, content={"ok": False, "detail": f"Wiki '{slug}' nicht gefunden"})

    name = slug
    from core.config import DATA_DIR
    wikis_file = DATA_DIR / "wikis.json"
    if wikis_file.exists():
        wikis = json.loads(wikis_file.read_text(encoding="utf-8"))
        for w in wikis:
            if w.get("slug") == slug:
                name = w.get("name", slug)
                break

    delete_wiki(slug)
    log_action(action="wiki_delete", details=f"Wiki '{name}' ({slug}) gelöscht",
               username=user.get("username"), user_id=user.get("id"), request=request)
    return JSONResponse(content={"ok": True})


@router.get("/wikis/new")
def wiki_new_form(request: Request):
    return render(request, "wiki_new.html", active_page="wiki_new", error=request.query_params.get("error"))


@router.post("/wikis/new")
async def wiki_new_create(request: Request):
    user = require_login(request)
    form = await request.form()
    name = (form.get("name") or "").strip()
    description = (form.get("description") or "").strip()
    if not name:
        return redirect(f"{BASE_PATH}/wikis/new?error=Name+ist+erforderlich")
    safe = slugify_wiki(name)
    root = wiki_path(safe)
    if not (root / "index.md").exists():
        (root / "index.md").write_text(
            f"---\nokf_version: \"0.1\"\n---\n# {name}\n\n> Wiki-Index von **{name}**.\n",
            encoding="utf-8",
        )
        (root / "log.md").write_text(
            f"---\nokf_version: \"0.1\"\n---\n# Wiki-Aktivitätslogbuch\n\n## {date.today().isoformat()}\n"
            f"- **Create**: Wiki '{name}' angelegt\n",
            encoding="utf-8",
        )
    save_wiki_meta(safe, name, description)
    log_action(action="wiki_create", details=f"Neues Wiki '{name}' (Slug: {safe}) angelegt", user_id=user["id"], username=user["username"], request=request)
    return redirect(f"{BASE_PATH}/wiki/{safe}/")


@router.get("/wiki/{wiki_name}/")
async def wiki_home(wiki_name: str, request: Request):
    return await _render_page(wiki_name, "index", request)


async def _render_page(wiki_name: str, page_name: str, request: Request):
    page_name = re.sub(r"\.md$", "", page_name)
    data = read_wiki_file(f"{page_name}.md", wiki_name)
    if not data:
        if page_name == "ingestlater":
            file_path = wiki_path(wiki_name) / "ingestlater.md"
            template = (
                "# Ingest Later\n\n"
                "> Liste von URLs und Text-Schnipseln, die später ins Wiki eingepflegt werden sollen.\n\n"
                "## 🔗 Gemerkte URLs\n\n"
                "## 📝 Gemerkte Texte und Notizen\n\n"
            )
            file_path.write_text(template, encoding="utf-8")
            await run_sync_async(wiki_name)
            data = read_wiki_file("ingestlater.md", wiki_name)
        else:
            abort(404, f"Seite '{page_name}' nicht im Wiki '{wiki_name}' gefunden.")

    all_page_slugs = {p["slug"] for p in get_all_wiki_pages(wiki_name)}
    wikilinks_slugs = set(extract_links_from_content(data["content"]))
    missing_links = sorted(wikilinks_slugs - all_page_slugs)

    is_index = page_name == "index"
    is_log = page_name == "log"

    raw_content = data["content"]
    if is_log:
        first_h2 = re.search(r"^##\s+\d{4}-\d{2}-\d{2}", raw_content, re.MULTILINE)
        if first_h2:
            header_part = raw_content[:first_h2.start()]
            body_part = raw_content[first_h2.start():]
            matches = list(re.finditer(r"^##\s+\d{4}-\d{2}-\d{2}", body_part, re.MULTILINE))
            log_entries = []
            for i, m in enumerate(matches):
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(body_part)
                log_entries.append(body_part[start:end].strip())
            log_entries.reverse()
            raw_content = header_part + "\n\n" + "\n\n".join(log_entries)

    html_content = render_markdown(raw_content, page_name, wiki_name)

    # Page Title Extraktion
    page_title = data.get("title")
    if not page_title:
        fm_match = re.search(r"^---\s*\n(.*?)\n---", data["content"], re.DOTALL)
        if fm_match:
            try:
                import yaml
                fm_data = yaml.safe_load(fm_match.group(1))
                if isinstance(fm_data, dict) and fm_data.get("title"):
                    page_title = str(fm_data["title"]).strip()
            except Exception:
                pass
    if not page_title:
        h1_match = re.search(r"^#\s+(.+)$", raw_content, re.MULTILINE)
        if h1_match:
            page_title = h1_match.group(1).strip()
        else:
            page_title = data["name"].replace("-", " ").capitalize()

    # Stellen sicher, dass jede Seite eine H1 Überschrift hat
    if not re.search(r"<h1[^>]*>", html_content, re.IGNORECASE):
        html_content = f'<h1 class="text-3xl font-bold mb-4 pb-2 border-b border-border text-primary">{page_title}</h1>\n' + html_content

    source_path = None
    fm_match = re.search(r"^---\s*\n(.*?)\n---", data["content"], re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).split("\n"):
            if line.startswith("source:"):
                source_path = line.split(":", 1)[1].strip()
                break

    trail_info = None
    trails = get_wiki_trails(wiki_name)
    for trail in trails:
        slugs_only = [item[1] for item in trail["path"]]
        if page_name in slugs_only:
            idx = slugs_only.index(page_name)
            prev_item = trail["path"][idx - 1] if idx > 0 else None
            next_item = trail["path"][idx + 1] if idx < len(trail["path"]) - 1 else None
            trail_info = {
                "title": trail["title"],
                "slug": trail["slug"],
                "prev": prev_item,
                "next": next_item,
                "index": idx + 1,
                "total": len(trail["path"]),
            }
            break

    from services.tags import extract_tags
    page_tags = extract_tags(data["content"])

    return render(
        request, "page.html",
        wiki=wiki_name,
        active_page=page_name,
        page_title=page_title,
        content=html_content,
        is_index=is_index,
        is_log=is_log,
        wikilinks_missing=missing_links,
        show_source=bool(source_path),
        source_path=source_path,
        raw_page_name=data["name"],
        success_msg=request.query_params.get("success_msg"),
        error_msg=request.query_params.get("error_msg"),
        trail_info=trail_info,
        page_tags=page_tags,
    )


_EXPORT_CSS = """\
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.6;color:#1a1a2e;background:#f8f9fa;padding:2rem;max-width:900px;margin:0 auto}
h1,h2,h3,h4{color:#16213e;margin-top:1.5em;margin-bottom:.5em}
h1{border-bottom:2px solid #0f3460;padding-bottom:.3em}
h2{border-bottom:1px solid #e2e8f0;padding-bottom:.2em}
a{color:#0f3460;text-decoration:none}
a:hover{text-decoration:underline}
pre{background:#1e293b;color:#e2e8f0;padding:1rem;border-radius:8px;overflow-x:auto;font-size:.9em;margin:1em 0}
code{background:#e2e8f0;padding:.15em .35em;border-radius:4px;font-size:.9em}
pre code{background:transparent;padding:0;color:inherit}
blockquote{border-left:4px solid #0f3460;margin:1em 0;padding:.5em 1em;background:#fff;border-radius:0 8px 8px 0}
img{max-width:100%;height:auto;border-radius:8px}
table{border-collapse:collapse;width:100%;margin:1em 0}
th,td{border:1px solid #e2e8f0;padding:.5em .75em;text-align:left}
th{background:#0f3460;color:#fff}
ul,ol{margin:.5em 0 .5em 1.5em}
.meta{color:#64748b;font-size:.85em;margin-bottom:1.5em;padding-bottom:1em;border-bottom:1px solid #e2e8f0}
.tags{display:flex;gap:.5em;flex-wrap:wrap;margin-bottom:1em}
.tag{background:#e2e8f0;color:#0f3460;padding:.15em .6em;border-radius:99px;font-size:.8em}
"""


@router.get("/wiki/{wiki_name}/{page_name}/export")
def wiki_export(wiki_name: str, page_name: str, request: Request):
    user = require_login(request)
    page_name = re.sub(r"\.md$", "", page_name)
    src_file = wiki_path(wiki_name) / f"{page_name}.md"
    if not src_file.exists():
        abort(404, f"Seite '{page_name}' existiert nicht.")

    export_format = request.query_params.get("format", "md").lower()
    EXPORT_DIR.mkdir(exist_ok=True)

    try:
        if export_format == "html":
            content_md = src_file.read_text(encoding="utf-8")
            body = re.sub(r"^---.*?---\s*", "", content_md, flags=re.DOTALL)
            title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else page_name.replace("-", " ").title()

            from services.tags import extract_tags
            tags = extract_tags(content_md)
            tags_html = ""
            if tags:
                tags_html = '<div class="tags">' + "".join(f'<span class="tag">#{t}</span>' for t in tags) + "</div>"

            from services.markdown import render_markdown
            rendered = render_markdown(body)
            html = f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} – LLMWikiNG Export</title>
<style>{_EXPORT_CSS}</style>
</head>
<body>
<h1>{title}</h1>
{tags_html}
<div class="meta">Exportiert aus LLMWikiNG · Wiki: {wiki_name} · {datetime.now().strftime('%Y-%m-%d')}</div>
{rendered}
</body>
</html>"""
            dest_file = EXPORT_DIR / f"{wiki_name}__{page_name}.html"
            dest_file.write_text(html, encoding="utf-8")
            try:
                append_okf_log("export", page_name, f"HTML exportiert nach {dest_file.relative_to(PROJECT_ROOT)}", wiki_name)
                log_action(action="page_export_html", details=f"Seite '{page_name}' (Wiki: {wiki_name}) als HTML exportiert", user_id=user["id"], username=user["username"], request=request)
            except Exception:
                pass
            success_msg = f"Seite '{page_name}.html' erfolgreich nach output_docs/ exportiert!"
        else:
            dest_file = EXPORT_DIR / f"{wiki_name}__{page_name}.md"
            dest_file.write_text(src_file.read_text(encoding="utf-8"), encoding="utf-8")
            try:
                append_okf_log("export", page_name, f"Seite exportiert nach {dest_file.relative_to(PROJECT_ROOT)}", wiki_name)
                log_action(action="page_export", details=f"Seite '{page_name}' (Wiki: {wiki_name}) exportiert nach output_docs/", user_id=user["id"], username=user["username"], request=request)
            except Exception:
                pass
            success_msg = f"Seite '{page_name}.md' erfolgreich nach output_docs/ exportiert!"
        return redirect(f"{BASE_PATH}/wiki/{wiki_name}/{urlencode(page_name)}?success_msg={urlencode(success_msg)}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/wiki/{wiki_name}/{urlencode(page_name)}?error_msg={urlencode(f'Export fehlgeschlagen: {e}')}")


@router.get("/wiki/{wiki_name}/export/bundle")
def wiki_export_bundle(wiki_name: str, request: Request):
    user = require_login(request)
    from services.wiki import get_all_wiki_pages

    pages = get_all_wiki_pages(wiki_name)
    if not pages:
        abort(404, f"Keine Seiten im Wiki '{wiki_name}' gefunden.")

    EXPORT_DIR.mkdir(exist_ok=True)
    pages_html = ""

    for p in pages:
        slug = p["slug"]
        fp = wiki_path(wiki_name) / f"{slug}.md"
        if not fp.exists():
            continue
        try:
            content_md = fp.read_text(encoding="utf-8", errors="replace")
            body = re.sub(r"^---.*?---\s*", "", content_md, flags=re.DOTALL)
            title = p["title"]
            from services.markdown import render_markdown
            rendered = render_markdown(body)
            from services.tags import extract_tags
            tags = extract_tags(content_md)
            tags_html = ""
            if tags:
                tags_html = '<div class="tags">' + "".join(f'<span class="tag">#{t}</span>' for t in tags) + "</div>"
            pages_html += f"""<section id="{slug}">
<h2>{title}</h2>
{tags_html}
{rendered}
<hr class="my-8 border-border">
</section>
"""
        except Exception:
            continue

    html = f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wiki-Bundle: {wiki_name} – LLMWikiNG Export</title>
<style>{_EXPORT_CSS}
hr{{margin:2rem 0;border:none;border-top:1px solid #e2e8f0}}
</style>
</head>
<body>
<h1>📦 Wiki-Bundle: {wiki_name}</h1>
<div class="meta">Exportiert aus LLMWikiNG · {len(pages)} Seiten · {datetime.now().strftime('%Y-%m-%d')}</div>
{pages_html}
</body>
</html>"""
    dest_file = EXPORT_DIR / f"{wiki_name}__bundle.html"
    dest_file.write_text(html, encoding="utf-8")
    try:
        log_action(action="bundle_export", details=f"Gesamtes Wiki '{wiki_name}' als HTML-Bundle exportiert ({len(pages)} Seiten)", user_id=user["id"], username=user["username"], request=request)
    except Exception:
        pass
    success_msg = f"Wiki-Bundle '{wiki_name}' erfolgreich nach output_docs/ exportiert! ({len(pages)} Seiten)"
    return redirect(f"{BASE_PATH}/export?success_msg={urlencode(success_msg)}")


@router.get("/wiki/{wiki_name}/{page_name}/delete")
async def wiki_delete(wiki_name: str, page_name: str, request: Request):
    user = require_login(request)
    page_name = re.sub(r"\.md$", "", page_name)
    if page_name in ("index", "log", "ingestlater"):
        abort(403, "System-Dateien können nicht gelöscht werden.")

    src_file = wiki_path(wiki_name) / f"{page_name}.md"
    if not src_file.exists():
        abort(404, f"Seite '{page_name}' existiert nicht.")

    try:
        src_file.unlink()
        try:
            append_okf_log("delete", page_name, "Seite gelöscht", wiki_name)
            log_action(action="page_delete", details=f"Seite '{page_name}' (Wiki: {wiki_name}) gelöscht", user_id=user["id"], username=user["username"], request=request)
        except Exception:
            pass
        await run_sync_async(wiki_name)
        success_msg = f"Seite '{page_name}.md' erfolgreich gelöscht."
        return redirect(f"{BASE_PATH}/wiki/{wiki_name}/?sync_status={urlencode(success_msg)}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/wiki/{wiki_name}/{urlencode(page_name)}?error_msg={urlencode(f'Löschen fehlgeschlagen: {e}')}")


@router.get("/raw")
def raw_list(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    files = []
    if RAW_DIR.exists():
        for f in sorted(RAW_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep":
                stat = f.stat()
                size_kb = stat.st_size / 1024
                size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
                mtime_formatted = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                wiki_slug = find_wiki_slug_for_raw(f.name, wiki)
                files.append({
                    "name": f.name,
                    "size_formatted": size_formatted,
                    "mtime_formatted": mtime_formatted,
                    "wiki_slug": wiki_slug,
                })
    return render(request, "raw_list.html", active_page="raw_list", files=files, wiki=wiki)


@router.get("/raw/{filename}")
def raw_page(filename: str, request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    filepath = RAW_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        wiki_filepath = wiki_path(wiki) / filename
        if wiki_filepath.exists() and wiki_filepath.is_file():
            filepath = wiki_filepath
        else:
            abort(404, f"Rohdatei '{filename}' wurde nicht gefunden.")

    download_requested = request.query_params.get("download", "0") == "1"
    is_text = is_text_file(filename)

    if download_requested or not is_text:
        return FileResponse(str(filepath), filename=filename, media_type="application/octet-stream")

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        stat = filepath.stat()
        size_kb = stat.st_size / 1024
        size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
        mtime_formatted = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        wiki_slug = find_wiki_slug_for_raw(filename, wiki)
        return render(
            request, "raw_view.html",
            active_page="raw_list",
            filename=filename, content=content,
            size_formatted=size_formatted, mtime_formatted=mtime_formatted,
            wiki_slug=wiki_slug, is_text=True, wiki=wiki,
        )
    except Exception as e:
        abort(500, f"Fehler beim Lesen der Datei: {e}")


@router.get("/pending")
def pending_list(request: Request):
    files = get_pending_files()
    return render(
        request, "pending_list.html",
        active_page="pending_list",
        files=files,
        success_msg=request.query_params.get("success_msg"),
        error_msg=request.query_params.get("error_msg"),
    )


@router.get("/pending/ingest/{filename}")
async def pending_ingest_single(filename: str, request: Request):
    filepath = RAW_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        abort(404, f"Datei '{filename}' nicht im raw/ Ordner gefunden.")

    try:
        backend = os.environ.get("LLM_BACKEND", "ollama")
        env = os.environ.copy()
        env["LLM_BACKEND"] = backend
        result = await run_ingest_async(filepath, timeout=120, env=env)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"Ingest fehlgeschlagen (Exitcode {result.returncode})")

        try:
            if filepath.exists() and filepath.is_file():
                filepath.unlink()
        except Exception:
            pass

        await run_sync_async("main")
        success_msg = f"Datei '{filename}' wurde erfolgreich ingestiert!"
        return redirect(f"{BASE_PATH}/pending?success_msg={urlencode(success_msg)}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/pending?error_msg={urlencode(f'Fehler beim Ingest von {filename}: {e}')}")


@router.get("/pending/delete/{filename}")
def pending_delete_single(filename: str, request: Request):
    user = require_login(request)
    filepath = RAW_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        return redirect(f"{BASE_PATH}/pending?error_msg=" + urlencode(f"Datei '{filename}' nicht gefunden."))

    try:
        filepath.unlink()
        log_action(
            action="pages_delete",
            details=f"Rohdatei aus Pending Ingest gelöscht: '{filename}'",
            username=user.get("username"),
            user_id=user.get("id"),
            request=request
        )
        success_msg = f"Datei '{filename}' wurde gelöscht!"
        return redirect(f"{BASE_PATH}/pending?success_msg={urlencode(success_msg)}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/pending?error_msg={urlencode(f'Fehler beim Löschen von {filename}: {e}')}")



@router.get("/pending/ingest-all")
async def pending_ingest_all(request: Request):
    files = get_pending_files()
    if not files:
        return redirect(f"{BASE_PATH}/pending?error_msg=" + urlencode("Keine ausstehenden Dateien zum Ingestieren gefunden."))

    success_count = 0
    errors = []
    backend = os.environ.get("LLM_BACKEND", "ollama")

    for file in files:
        filename = file["name"]
        filepath = RAW_DIR / filename
        try:
            env = os.environ.copy()
            env["LLM_BACKEND"] = backend
            result = await run_ingest_async(filepath, timeout=120, env=env)
            if result.returncode == 0:
                success_count += 1
                try:
                    if filepath.exists() and filepath.is_file():
                        filepath.unlink()
                except Exception:
                    pass
            else:
                errors.append(f"{filename}: {result.stderr.strip()}")
        except Exception as e:
            errors.append(f"{filename}: {e}")

    await run_sync_async("main")

    if success_count > 0:
        msg = f"{success_count} Datei(en) erfolgreich ingestiert!"
        if errors:
            msg += f" (Fehler bei: {', '.join(errors)})"
        return redirect(f"{BASE_PATH}/pending?success_msg={urlencode(msg)}")
    err_msg = f"Ingest fehlgeschlagen: {'; '.join(errors)}"
    return redirect(f"{BASE_PATH}/pending?error_msg={urlencode(err_msg)}")


@router.get("/export")
def export_list(request: Request):
    files = []
    if EXPORT_DIR.exists():
        for f in sorted(EXPORT_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep":
                stat = f.stat()
                size_kb = stat.st_size / 1024
                size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
                mtime_formatted = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                files.append({"name": f.name, "size_formatted": size_formatted, "mtime_formatted": mtime_formatted})
    return render(request, "export_list.html", active_page="export_list", files=files, wikis=list_wikis())


@router.get("/export/{filename}")
def export_view(filename: str, request: Request):
    filepath = EXPORT_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        abort(404, f"Exportiertes Dokument '{filename}' wurde nicht gefunden.")

    download_requested = request.query_params.get("download", "0") == "1"
    is_markdown = filename.lower().endswith(".md")

    if download_requested:
        return FileResponse(str(filepath), filename=filename, media_type="application/octet-stream")

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        stat = filepath.stat()
        size_kb = stat.st_size / 1024
        size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
        mtime_formatted = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        content_html = render_markdown(content) if is_markdown else ""
        return render(
            request, "export_view.html",
            active_page="export_list",
            filename=filename, content=content, content_html=content_html,
            size_formatted=size_formatted, mtime_formatted=mtime_formatted,
            is_markdown=is_markdown,
        )
    except Exception as e:
        abort(500, f"Fehler beim Lesen des Dokuments: {e}")


@router.get("/tags")
def tags_page(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    tag_filter = request.query_params.get("tag", "").strip()
    from services.tags import list_all_tags, get_tag_cloud, get_pages_by_tag, get_all_tags_aggregated
    tag_cloud = get_tag_cloud(wiki)
    max_count = max((t["count"] for t in tag_cloud), default=1)
    tag_stats = get_all_tags_aggregated(wiki)

    if tag_filter:
        tagged_pages = get_pages_by_tag(tag_filter, wiki)
        def _sort_key(p):
            return 0 if tag_filter.lower() in p["title"].lower() else 1
        tagged_pages.sort(key=_sort_key)
        return render(request, "tags.html", active_page="tags", wiki=wiki, wikis=list_wikis(),
                      tag_filter=tag_filter, tagged_pages=tagged_pages,
                      tag_cloud=tag_cloud, max_count=max_count, tag_stats=tag_stats, page_tags=None)

    return render(request, "tags.html", active_page="tags", wiki=wiki, wikis=list_wikis(),
                  tag_filter=None, tagged_pages=[], tag_cloud=tag_cloud,
                  max_count=max_count, tag_stats=tag_stats, page_tags=None)


@router.get("/graph")
def graph_page(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    return render(request, "graph.html", active_page="graph", wiki=wiki, wikis=list_wikis())


@router.get("/graph/data")
async def graph_data(request: Request):
    from fastapi.responses import JSONResponse

    wiki = request.query_params.get("wiki") or _default_wiki()
    if wiki == "__all__":
        return JSONResponse(await asyncio.to_thread(build_graph_data_all))
    return JSONResponse(await asyncio.to_thread(build_graph_data, wiki))


@router.get("/graph/data/paginated")
async def graph_data_paginated(request: Request):
    """Paginierter Graph-Endpunkt für Lazy-Loading im Frontend.

    Query-Parameter:
        wiki: Wiki-Name.
        page: Null-basierter Seitenindex (default 0).
        page_size: Knoten pro Seite (default 200, max 1000).
        tag: Optionaler Tag-Filter.
    """
    from fastapi.responses import JSONResponse

    wiki = request.query_params.get("wiki") or _default_wiki()
    try:
        page = int(request.query_params.get("page", 0))
    except (ValueError, TypeError):
        page = 0
    try:
        page_size = min(max(1, int(request.query_params.get("page_size", 200))), 1000)
    except (ValueError, TypeError):
        page_size = 200
    tag = request.query_params.get("tag", "") or None
    return JSONResponse(
        await asyncio.to_thread(
            build_graph_data_paginated,
            wiki, page=page, page_size=page_size, tag_filter=tag,
        )
    )


@router.get("/ingest")
def ingest_get(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    return render(
        request, "ingest.html",
        active_page="ingest", wiki=wiki,
        wikis=list_wikis(),
        success_msg=None, error_msg=None, new_slug=None, is_later=False,
    )


@router.post("/ingest")
async def ingest_post(request: Request):
    success_msg = None
    error_msg = None
    new_slug = None
    is_later = False
    
    form = await request.form()
    user = require_login(request)
    wiki = (form.get("wiki") or request.query_params.get("wiki") or _default_wiki())
    ingest_type = form.get("type")
    backend = form.get("backend", "ollama")

    temp_dir = SCRATCH_DIR
    temp_dir.mkdir(exist_ok=True)

    filepath = None
    orig_filename = None

    try:
        if ingest_type == "url_later":
            url = (form.get("url") or "").strip()
            title = (form.get("title") or "").strip()
            if not url:
                raise ValueError("URL darf nicht leer sein.")
            save_to_ingestlater("url", title, url, wiki)
            log_action(action="ingest_save_later", details=f"URL zur späteren Verarbeitung gespeichert: '{title}' → {url} (Wiki: {wiki})", username=user.get("username"), user_id=user.get("id"), request=request)
            success_msg = "URL erfolgreich in ingestlater.md gespeichert!"
            is_later = True

        elif ingest_type == "text_later":
            title = (form.get("title") or "").strip()
            content = (form.get("content") or "").strip()
            if not title or not content:
                raise ValueError("Titel und Inhalt dürfen nicht leer sein.")
            save_to_ingestlater("text", title, content, wiki)
            log_action(action="ingest_save_later", details=f"Text zur späteren Verarbeitung gespeichert: '{title}' ({len(content)} Zeichen, Wiki: {wiki})", username=user.get("username"), user_id=user.get("id"), request=request)
            success_msg = "Text erfolgreich in ingestlater.md gespeichert!"
            is_later = True

        elif ingest_type == "file":
            upload = form.get("file")
            if not isinstance(upload, (StarletteUploadFile, FastAPIUploadFile)) or not getattr(upload, "filename", None):
                raise ValueError("Keine Datei ausgewählt.")
            orig_filename = upload.filename
            safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", orig_filename)
            filepath = temp_dir / safe_name
            content = await upload.read()
            filepath.write_bytes(content)

        elif ingest_type == "text":
            title = (form.get("title") or "").strip()
            content = (form.get("content") or "").strip()
            if not title or not content:
                raise ValueError("Titel und Inhalt dürfen nicht leer sein.")
            safe_title = title.lower().replace(" ", "-").replace("/", "-")
            safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", safe_title) + ".md"
            orig_filename = safe_name
            filepath = temp_dir / safe_name
            if not content.startswith("#"):
                content = f"# {title}\n\n{content}"
            filepath.write_text(content, encoding="utf-8")

        else:
            raise ValueError("Ungültiger Ingest-Typ.")

        if filepath is not None:
            from core.config import load_app_config
            from services.wiki import chunk_content, suggest_tags_from_content

            cfg = load_app_config()
            env = os.environ.copy()
            env["LLM_BACKEND"] = backend
            env["OLLAMA_HOST"] = cfg.get("ollama_host", "http://localhost:11434")
            env["OLLAMA_MODEL"] = cfg.get("ollama_model", "llama3.2:3b")
            env["WIKI_DIR"] = str(wiki_path(wiki))
            env["COLLECTION_NAME"] = f"wiki_{wiki}"

            raw_text = filepath.read_text(encoding="utf-8", errors="replace")

            # Tag-Vorschläge generieren
            suggested_tags = suggest_tags_from_content(raw_text, wiki)
            if suggested_tags:
                env["SUGGESTED_TAGS"] = ",".join(suggested_tags)

            # Große Texte chunken
            from services.wiki import CHUNK_THRESHOLD
            chunks = chunk_content(raw_text, title or Path(orig_filename).stem, max_chars=CHUNK_THRESHOLD)

            created_slugs: list[str] = []

            for chunk_title, chunk_body in chunks:
                chunk_file = temp_dir / f"{slugify_german(chunk_title)}.md"
                chunk_content_text = f"# {chunk_title}\n\n{chunk_body}"
                chunk_file.write_text(chunk_content_text, encoding="utf-8")

                custom_title = chunk_title
                result = await run_ingest_async(
                    chunk_file,
                    title=custom_title or None,
                    timeout=120,
                    env=env,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        result.stderr.strip()
                        or f"Ingest fehlgeschlagen für '{chunk_title}' (Exitcode {result.returncode})"
                    )

                current_slug = slugify_german(chunk_title)
                created_slugs.append(current_slug)

                try:
                    chunk_file.unlink()
                except Exception:
                    pass

            # Aus dem aktuellen Inhalt den Slug ermitteln
            if not title:
                try:
                    h1_match = re.search(r"^#\s+(.+)$", raw_text, re.MULTILINE)
                    if h1_match:
                        title = h1_match.group(1).strip()
                except Exception:
                    pass
            title_to_slug = title or Path(orig_filename).stem
            new_slug = slugify_german(title_to_slug)

            slug_list = ", ".join(created_slugs)
            log_action(
                action="ingest",
                details=f"Ingest: {slug_list} aus '{orig_filename}' ({len(chunks)} Chunk(s), Typ: {ingest_type}, Backend: {backend}, Wiki: {wiki})",
                username=user.get("username"),
                user_id=user.get("id"),
                request=request,
            )
            success_msg = (
                f"Quelle erfolgreich eingespielt! ({len(chunks)} Seite(n): {slug_list})"
                if len(chunks) > 1
                else f"Quelle erfolgreich eingespielt! ({new_slug}.md)"
            )
            await run_sync_async(wiki)

    except Exception as e:
        error_msg = str(e)
    finally:
        if filepath and filepath.exists():
            try:
                filepath.unlink()
            except Exception:
                pass

    return render(
        request, "ingest.html",
        active_page="ingest", wiki=wiki,
        wikis=list_wikis(),
        success_msg=success_msg, error_msg=error_msg, new_slug=new_slug, is_later=is_later,
    )


@router.get("/search/tags-autocomplete")
async def search_tags_autocomplete(request: Request):
    """Gibt passende Tags als JSON für das Autocomplete zurück.

    Query-Parameter: ``q`` = Teilbegriff, ``wiki`` = Wiki-Slug.
    """
    from services.tags import list_all_tags as _list_tags

    q = request.query_params.get("q", "").strip().lower()
    wiki = request.query_params.get("wiki") or _default_wiki()
    limit = 10

    if not q:
        return JSONResponse({"tags": []})

    all_tags = _list_tags(wiki) if wiki != "all" else []
    matched = [t for t in all_tags if q in t["tag"].lower()]
    matched = matched[:limit]

    return JSONResponse({"tags": matched})


@router.get("/search")
async def search(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    query = request.query_params.get("q", "").strip()
    tag_filter = request.query_params.get("tag", "").strip()
    results = []
    error = None
    sync_hint = False
    search_time_ms = None
    shards_queried = None

    # Parse tag: and # syntax from query – mehrere Tags werden AND-verknüpft
    from services.search import parse_search_tags
    from services.tags import normalize_tag as _norm_tag
    parsed_query, inline_tags = parse_search_tags(query)
    if parsed_query != query:
        query = parsed_query
    # Alle inline-tags UND den ?tag= Query-Parameter zusammenführen
    active_tag_filters: list[str] = [_norm_tag(t) for t in inline_tags if t]
    if tag_filter and (norm_tf := _norm_tag(tag_filter)):
        if norm_tf not in active_tag_filters:
            active_tag_filters.append(norm_tf)
    # Für Rückwärtskompatibilität: tag_filter auf ersten aktiven Filter setzen
    tag_filter = active_tag_filters[0] if active_tag_filters else ""

    if wiki == "all":
        page_count = sum(len(get_all_wiki_pages(w["name"])) for w in list_wikis())
        sync_needed_flag = any(is_sync_needed(w["name"]) for w in list_wikis())
    else:
        page_count = len(get_all_wiki_pages(wiki))
        sync_needed_flag = is_sync_needed(wiki)

    if query:
        if page_count > 0 and sync_needed_flag:
            sync_hint = True

        # Tag-Filter VOR dem Matrix-Call anwenden (Performance: Plan § 6)
        candidate_slugs: set[str] | None = None
        if active_tag_filters:
            from services.tags import get_pages_by_tag as _get_by_tag
            for _tag in active_tag_filters:
                _tag_pages = _get_by_tag(_tag, wiki if wiki != "all" else "main")
                _tag_slugs = {p["slug"] for p in _tag_pages}
                if candidate_slugs is None:
                    candidate_slugs = _tag_slugs
                else:
                    candidate_slugs &= _tag_slugs  # AND-Verknüpfung
            if candidate_slugs is not None and not candidate_slugs:
                # Keine Treffer für Tag-Kombination → Matrix-Suche überspringen
                results = []
                raw_mentions_count = 0
                slug_exists = False
                if not results and page_count > 0 and sync_needed_flag:
                    sync_hint = True
                error = None
                # direkt zu render springen
                from services.tags import list_all_tags as _list_tags
                available_tags = _list_tags(wiki) if wiki != "all" else []
                _tag_filter = tag_filter or ""
                return render(
                    request, "search.html",
                    active_page="search", wiki=wiki, wikis=list_wikis(),
                    query=query, results=results, error=error, sync_hint=sync_hint,
                    page_count=page_count,
                    raw_mentions_count=0,
                    slug_exists=False,
                    available_tags=available_tags, tag_filter=_tag_filter,
                )

        search_result = await matrix_search(query, wiki, num_results=30)
        search_time_ms = search_result.get("search_time_ms")
        shards_queried = search_result.get("shards_queried")
        if search_result.get("error"):
            if "not found" in search_result.get("error", "").lower() or "timeout" in search_result.get("error", "").lower():
                if wiki == "all":
                    for w in list_wikis():
                        await run_sync_async(w["name"])
                else:
                    await run_sync_async(wiki)
                search_result = await matrix_search(query, wiki, num_results=30)
                sync_hint = False
            else:
                error = search_result["error"]


        if not error:
            for r in search_result.get("results", []):
                # Tag-Filter anwenden (Kandidaten-Set aus Pre-Filter oder per Lookup)
                if candidate_slugs is not None:
                    if r["slug"] not in candidate_slugs:
                        continue
                elif active_tag_filters:
                    from services.tags import get_page_tags
                    r_tags = get_page_tags(r.get("wiki", wiki), r["slug"])
                    norm_r_tags = [_norm_tag(t) for t in r_tags]
                    if not all(ft in norm_r_tags for ft in active_tag_filters):
                        continue
                r["title_html"] = _highlight_text(r["title"], query)
                r["snippet_html"] = _highlight_text(r["snippet"], query)
                results.append(r)

        if not results and page_count > 0 and sync_needed_flag:
            sync_hint = True

        raw_mentions_count = 0
        if RAW_DIR.exists():
            for f in RAW_DIR.iterdir():
                if f.is_file() and f.suffix in (".md", ".txt"):
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace").lower()
                        if query.lower() in content:
                            raw_mentions_count += 1
                    except Exception:
                        pass

        target_slug = slugify_german(query)
        if wiki == "all":
            all_slugs = set()
            for w in list_wikis():
                all_slugs.update(p["slug"] for p in get_all_wiki_pages(w["name"]))
            slug_exists = target_slug in all_slugs
        else:
            slug_exists = target_slug in {p["slug"] for p in get_all_wiki_pages(wiki)}
            
        _u = get_current_user(request) or {}
        log_action(
            action="search",
            details=f"Suche '{query}' in '{wiki}' – {len(results)} Treffer",
            username=(_u or {}).get("username"),
            user_id=(_u or {}).get("id"),
            request=request,
        )
    else:
        raw_mentions_count = 0
        slug_exists = False

    from services.tags import list_all_tags as _list_tags
    available_tags = _list_tags(wiki) if wiki != "all" else []
    _tag_filter = tag_filter or ""

    return render(
        request, "search.html",
        active_page="search", wiki=wiki, wikis=list_wikis(),
        query=query, results=results, error=error, sync_hint=sync_hint,
        page_count=page_count,
        raw_mentions_count=raw_mentions_count if query else 0,
        slug_exists=slug_exists if query else False,
        available_tags=available_tags, tag_filter=_tag_filter,
        search_time_ms=search_time_ms, shards_queried=shards_queried,
    )


@router.get("/lang/{code}")
def switch_language(code: str, request: Request):
    from core.config import get_available_languages, load_app_config, CONFIG_FILE

    available = get_available_languages()
    if code not in available:
        code = "en"
    referrer = request.headers.get("referer") or f"{BASE_PATH}/"
    response = redirect(referrer)
    response.set_cookie("llmwiki_lang", code, max_age=365 * 24 * 3600)
    # Sprache dauerhaft in config.json sichern (einzige Einstellungsquelle)
    try:
        from core.config import _atomic_write
        data = load_app_config()
        data["language"] = code
        _atomic_write(CONFIG_FILE, json.dumps(data, indent=2, ensure_ascii=False))
    except Exception:
        pass
    return response


@router.get("/docs")
def docs_page(request: Request):
    from core.config import resolve_lang
    lang = resolve_lang(
        request.query_params.get("lang"),
        request.cookies.get("llmwiki_lang"),
    )
    template = "docs_de.html" if lang == "de" else "docs.html"
    return render(
        request, template,
        active_page="docs",
        app_version=APP_VERSION,
    )


@router.get("/about")
async def about(request: Request):
    from core.config import resolve_lang
    lang = resolve_lang(
        request.query_params.get("lang"),
        request.cookies.get("llmwiki_lang"),
    )
    template = "about_de.html" if lang == "de" else "about.html"
    matrix_ver = "Matrix 3.0.0"
    try:
        from core.config import MATRIX_DATA_ROOT
        if MATRIX_DATA_ROOT.exists():
            shards = list(MATRIX_DATA_ROOT.glob("*_shard_*.db"))
            matrix_ver = f"Matrix 3.0.0 · {len(shards)} Shards"
    except Exception:
        pass

    import sys
    from importlib.metadata import version as pkg_version

    def _pv(pkg: str) -> str:
        try:
            return pkg_version(pkg)
        except Exception:
            return "unbekannt"

    try:
        fastapi_ver = _pv("fastapi")
    except Exception:
        fastapi_ver = "unbekannt"

    return render(
        request, template,
        active_page="about",
        app_version=APP_VERSION,
        python_version=sys.version.split()[0],
        fastapi_version=fastapi_ver,
        markdown_version=_pv("markdown"),
        jinja_version=_pv("jinja2"),
        matrix_version=matrix_ver,
        uvicorn_version=_pv("uvicorn"),
    )


@router.get("/admin/status")
def admin_status(request: Request):
    from fastapi.responses import JSONResponse

    wiki = request.query_params.get("wiki") or _default_wiki()
    return JSONResponse({
        "sync_needed": is_sync_needed(wiki),
        "pages": len(get_all_wiki_pages(wiki)),
        "server": APP_VERSION,
    })


@router.get("/admin/sync")
async def admin_sync(request: Request, admin: dict = Depends(require_admin)):
    from fastapi.responses import JSONResponse

    wiki = request.query_params.get("wiki") or _default_wiki()
    results = await run_sync_async(wiki, force=True)
    log_action(action="wiki_sync", details=f"Wiki '{wiki}' manuell synchronisiert", user_id=admin["id"], username=admin["username"], request=request)
    fmt = request.query_params.get("format", "html")
    if fmt == "json":
        return JSONResponse({
            "success": results.get("matrix", True) and results.get("index", True),
            "matrix": results.get("matrix", True),
            "index": results.get("index", True),
            "messages": results.get("messages", []),
        })
    status = "✅ Sync erfolgreich!" if (results.get("matrix", True) and results.get("index", True)) else "⚠ Sync teilweise fehlgeschlagen"

    # Deduplizieren und Säubern der Log-Nachrichten
    raw_msgs = results.get("messages", [])
    unique_msgs = []
    for msg in raw_msgs:
        if msg and msg not in unique_msgs:
            unique_msgs.append(msg)
    messages = "; ".join(unique_msgs) if unique_msgs else "Matrix-Index aktualisiert"
    return redirect(f"{BASE_PATH}/?sync_status={urlencode(status)}&sync_msg={urlencode(messages)}")



@router.get("/admin/update")
def admin_update(request: Request):
    return redirect(f"{BASE_PATH}/settings?tab=update")


@router.post("/admin/update/run")
def admin_update_run(request: Request):
    return redirect(f"{BASE_PATH}/settings?tab=update")


@router.get("/admin/update/check")
async def admin_update_check(request: Request):
    from fastapi.responses import JSONResponse
    raw_token = request.query_params.get("github_token", "").strip()
    github_token = "" if raw_token in ("ghp_xxxxxxxxxxxx", "ghp_...") else raw_token

    version_file = PROJECT_ROOT / "VERSION"
    local_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unbekannt"

    # Stellt sicher, dass ein Git-Repository existiert
    git_dir_check = await asyncio.to_thread(
        subprocess.run,
        ["git", "rev-parse", "--git-dir"],
        capture_output=True, text=True, timeout=5, cwd=str(PROJECT_ROOT),
    )
    if git_dir_check.returncode != 0:
        await asyncio.to_thread(
            subprocess.run,
            ["git", "init"],
            capture_output=True, text=True, timeout=5, cwd=str(PROJECT_ROOT),
        )
        await asyncio.to_thread(
            subprocess.run,
            ["git", "remote", "add", "origin", "https://github.com/ZeroDot1/LLMWikiNG.git"],
            capture_output=True, text=True, timeout=5, cwd=str(PROJECT_ROOT),
        )

    original_url = None
    github_version = None
    try:
        if github_token:
            # Origin-URL merken, um spaeter wieder herzustellen
            orig = (await asyncio.to_thread(
                subprocess.run,
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5, cwd=str(PROJECT_ROOT),
            )).stdout.strip()
            import re as _re
            clean_url = _re.sub(r"https://[^@]+@", "https://", orig)
            auth_url = clean_url.replace("https://", f"https://{github_token}@")
            await asyncio.to_thread(
                subprocess.run,
                ["git", "remote", "set-url", "origin", auth_url],
                timeout=5, cwd=str(PROJECT_ROOT),
            )
            original_url = orig

        # git ls-remote ist read-only – prueft ob Remote-Ref auf neuerem Commit liegt
        ls_proc = await asyncio.to_thread(
            subprocess.run,
            ["git", "ls-remote", "origin", "main"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT),
        )

        # Fallback: Falls Token angegeben war aber mit Auth-Fehler scheiterte, ohne Token versuchen
        if (ls_proc.returncode != 0 or not ls_proc.stdout.strip()) and original_url:
            await asyncio.to_thread(
                subprocess.run,
                ["git", "remote", "set-url", "origin", original_url],
                timeout=5, cwd=str(PROJECT_ROOT),
            )
            ls_proc = await asyncio.to_thread(
                subprocess.run,
                ["git", "ls-remote", "origin", "main"],
                capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT),
            )

        if ls_proc.returncode == 0 and ls_proc.stdout.strip():
            remote_hash = ls_proc.stdout.strip().split()[0]
            local_hash_proc = await asyncio.to_thread(
                subprocess.run,
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=str(PROJECT_ROOT),
            )
            local_hash = local_hash_proc.stdout.strip() if local_hash_proc.returncode == 0 else ""

            if remote_hash == local_hash:
                return JSONResponse({
                    "success": True,
                    "local_version": local_version,
                    "github_version": local_version,
                    "update_available": False,
                    "up_to_date": True,
                })

            await asyncio.to_thread(
                subprocess.run,
                ["git", "fetch", "origin"],
                capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
            )
            show_proc = await asyncio.to_thread(
                subprocess.run,
                ["git", "show", "origin/main:VERSION"],
                capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT),
            )
            if show_proc.returncode == 0 and show_proc.stdout.strip():
                github_version = show_proc.stdout.strip()

        # HTTP Fallback, falls git ls-remote scheiterte
        if not github_version:
            import urllib.request
            try:
                raw_url = "https://raw.githubusercontent.com/ZeroDot1/LLMWikiNG/main/VERSION"
                req = urllib.request.Request(raw_url, headers={"User-Agent": "LLMWikiNG-UpdateCheck/2.15"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        github_version = resp.read().decode("utf-8").strip()
            except Exception:
                pass

    except Exception as e:
        return JSONResponse({"success": False, "error": f"Fehler bei der Versionsprüfung: {e}"})
    finally:
        # GitHub-Token aus remote URL entfernen (Sicherheit!)
        if original_url:
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["git", "remote", "set-url", "origin", original_url],
                    timeout=5, cwd=str(PROJECT_ROOT),
                )
            except Exception:
                pass

    if github_version is None:
        return JSONResponse({"success": False, "error": "Konnte Version von GitHub nicht abrufen."})

    return JSONResponse({
        "success": True,
        "local_version": local_version,
        "github_version": github_version,
        "update_available": github_version != local_version,
        "up_to_date": github_version == local_version,
    })


@router.get("/status")
def status_dashboard(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    stats = get_wiki_stats(wiki)
    analytics = get_wiki_analytics(wiki)

    tools = {}
    for tool in ("jq", "ollama", "agy", "opencode"):
        tools[tool] = shutil.which(tool) is not None
    tools["matrix"] = bool(load_app_config().get("enable_matrix", False))

    config_data = {
        "backend": os.environ.get("LLM_BACKEND", "ollama"),
        "ollama_model": os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
        "wiki_dir": str(wiki_path(wiki)),
        "raw_dir": str(RAW_DIR),
        "export_dir": str(EXPORT_DIR),
    }

    app_version_text = _read_version()
    update_available = (PROJECT_ROOT / "update.sh").exists()

    return render(
        request, "status.html",
        active_page="status", wiki=wiki, wikis=list_wikis(),
        stats=stats,
        tools=tools,
        config=config_data,
        analytics=analytics,
        app_version=app_version_text,
        update_available=update_available,
    )


@router.get("/lint")
def lint_dashboard(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    run_check = request.query_params.get("run", "0") == "1"
    if run_check:
        res = run_lint(wiki)
    else:
        res = {
            "orphans": [], "missing": [], "stale": [], "missing_raw": [],
            "missing_type": [], "broken_links": [], "no_tags": [], "short_pages": [], "link_suggestions": [], "issue_count": 0,
        }
    return render(
        request, "lint.html",
        active_page="lint", wiki=wiki, wikis=list_wikis(),
        run_check=run_check,
        orphans=res.get("orphans", []),
        missing=res.get("missing", []),
        stale=res.get("stale", []),
        missing_raw=res.get("missing_raw", []),
        missing_type=res.get("missing_type", []),
        broken_links=res.get("broken_links", []),
        no_tags=res.get("no_tags", []),
        short_pages=res.get("short_pages", []),
        link_suggestions=res.get("link_suggestions", []),
        issue_count=res.get("issue_count", 0),
    )

@router.get("/config")
def config_get(request: Request):
    config_data = load_smtp_config()
    env_user = os.environ.get("GMAIL_USER", "")
    env_pass_exists = bool(os.environ.get("GMAIL_APP_PASSWORD"))
    return render(
        request, "config.html",
        active_page="config",
        config=config_data,
        env_user=env_user,
        env_pass_exists=env_pass_exists,
        success_msg=None,
        error_msg=None,
    )


@router.post("/config")
async def config_post(request: Request):
    form = await request.form()
    smtp_host = form.get("smtp_host", "smtp.gmail.com")
    try:
        smtp_port = int(form.get("smtp_port", "587"))
    except ValueError:
        smtp_port = 587
    smtp_user = (form.get("smtp_user") or "").strip()
    smtp_pass = (form.get("smtp_pass") or "").strip()
    use_tls = form.get("use_tls") == "1"
    recipients = (form.get("recipients") or "").strip()

    new_config = {
        "smtp_host": smtp_host, "smtp_port": smtp_port, "smtp_user": smtp_user,
        "smtp_pass": smtp_pass, "use_tls": use_tls, "recipients": recipients,
    }
    ok = save_smtp_config(new_config)
    success_msg = "Konfiguration erfolgreich in config.json gespeichert!" if ok else "Fehler beim Speichern der Konfiguration."
    error_msg = None if ok else "Fehler beim Speichern der Konfiguration."

    config_data = load_smtp_config()
    env_user = os.environ.get("GMAIL_USER", "")
    env_pass_exists = bool(os.environ.get("GMAIL_APP_PASSWORD"))
    return render(
        request, "config.html",
        active_page="config",
        config=config_data,
        env_user=env_user,
        env_pass_exists=env_pass_exists,
        success_msg=success_msg,
        error_msg=error_msg,
    )


@router.get("/settings")
def settings_get(request: Request):
    app_version_text = _read_version()
    update_available_flag = (PROJECT_ROOT / "update.sh").exists()
    update_log_output = request.query_params.get("update_log")
    # Bei reloaded=1 (nach Countdown-Refresh) das update.log NICHT mehr laden,
    # sonst entsteht ein Endlosschleifen-Refresh (Log -> Countdown -> Refresh -> Log -> ...).
    reloaded = request.query_params.get("reloaded") == "1"
    if reloaded:
        _log_file = DATA_DIR / "update.log"
        if _log_file.exists():
            _log_file.unlink()
    if not update_log_output and not reloaded:
        update_log_file = DATA_DIR / "update.log"
        if update_log_file.exists():
            update_log_output = update_log_file.read_text(encoding="utf-8").strip() or None

    health_run_check = request.query_params.get("run") == "1"
    if health_run_check:
        h = run_lint(_default_wiki())
        health = {
            "orphans": h["orphans"], "missing": h["missing"], "stale": h["stale"],
            "missing_raw": h["missing_raw"], "issue_count": h["issue_count"],
        }
    else:
        health = {"orphans": [], "missing": [], "stale": [], "missing_raw": [], "issue_count": 0}

    smtp_config_data = load_smtp_config()
    env_user = os.environ.get("GMAIL_USER", "")
    env_pass_exists = bool(os.environ.get("GMAIL_APP_PASSWORD"))

    from core.config import load_app_config
    from services.backup import list_server_backups
    from services.ai_config import load_ai_config
    cfg = load_app_config()
    return render(
        request, "settings.html",
        active_page="settings",
        smtp_config=smtp_config_data,
        env_user=env_user,
        env_pass_exists=env_pass_exists,
        audit_config=cfg,
        mcp_config=cfg,
        ai_config=load_ai_config(),
        syntax_highlighting=cfg.get("syntax_highlighting", True),
        all_audit_categories=ALL_CATEGORIES,
        config_success_msg=None,
        config_error_msg=None,
        health_run_check=health_run_check,
        health_orphans=health["orphans"],
        health_missing=health["missing"],
        health_stale=health["stale"],
        health_missing_raw=health["missing_raw"],
        health_issue_count=health["issue_count"],
        app_version=app_version_text,
        update_available=update_available_flag,
        update_log=update_log_output,
        users=list_users(),
        keys=list_keys(),
        new_key=None,
        new_generated_mcp_key=None,
        new_generated_api_key=None,
        syntax_msg=request.query_params.get("syntax_msg"),
        registration_enabled=cfg.get("registration_enabled", True),
        server_backups=list_server_backups(),
        mcp_keys=list_mcp_keys(),
        mcp_tool_groups=MCP_TOOL_GROUPS,
        lang=request.cookies.get("llmwiki_lang", "de"),
    )


@router.post("/settings/syntax-highlighting/set")
async def settings_syntax_highlighting_set(request: Request):
    """Speichert die globale Option für Syntax-Highlighting in config.json."""
    user = require_login(request)
    form = await request.form()
    enabled = form.get("value") == "1" or form.get("enabled") == "1" or form.get("value") == "on"
    from core.config import save_app_config
    ok = save_app_config({"syntax_highlighting": bool(enabled)})
    msg = "Syntax-Highlighting aktiviert." if enabled else "Syntax-Highlighting deaktiviert."
    if not ok:
        msg = "Fehler beim Speichern der Einstellung."
    return redirect(f"{BASE_PATH}/settings?syntax_msg={urlencode(msg)}")


@router.get("/settings/ai-config/json")
def settings_ai_config_json(request: Request):
    """Gibt die AI-Konfiguration samt Verfügbarkeit der Tools als JSON zurück."""
    require_login(request)
    from services.ai_config import load_ai_config, in_docker

    cfg = load_ai_config()
    availability = {}
    for key in ("opencode_path", "hermes_path", "agy_path"):
        path = cfg.get(key, "")
        availability[key] = bool(path) and os.path.isfile(path)
    cfg["docker"] = in_docker()
    cfg["availability"] = availability
    return JSONResponse(cfg)


@router.post("/settings/ai-config")
async def settings_ai_config_post(request: Request):
    """Speichert die AI-Integrations-Konfiguration in ai.config.json."""
    require_login(request)
    from services.ai_config import save_ai_config

    form = await request.form()

    def _int(name: str, fallback: int) -> int:
        raw = (form.get(name) or "").strip()
        try:
            return int(raw)
        except (TypeError, ValueError):
            return fallback

    updates = {
        "ollama_host": (form.get("ollama_host") or "127.0.0.1").strip(),
        "ollama_port": _int("ollama_port", 11434),
        "ollama_username": (form.get("ollama_username") or "").strip(),
        "ollama_password": (form.get("ollama_password") or "").strip(),
        "ollama_model": (form.get("ollama_model") or "").strip(),
        "opencode_path": (form.get("opencode_path") or "").strip(),
        "hermes_path": (form.get("hermes_path") or "").strip(),
        "agy_path": (form.get("agy_path") or "").strip(),
    }
    ok = save_ai_config(updates)
    msg = "AI-Integration gespeichert." if ok else "Fehler beim Speichern der AI-Integration."
    return redirect(f"{BASE_PATH}/settings?tab=ai&ai_msg={urlencode(msg)}")


def _trigger_server_restart() -> None:
    """Leitet einen sauberen Server-Neustart ein.

    Der aktuelle uvicorn-Worker wird nach einer kurzen Verzögerung mit
    ``SIGTERM`` beendet, sodass der Browser die Response noch empfangen kann.
    Im Docker-Container (``restart: always``) oder via Systemd/start.sh wird
    der Prozess dadurch automatisch mit dem NEUEN Code neu hochgefahren –
    das verhindert, dass nach einem Update weiterhin der alte (fehlerhafte)
    Code im Speicher läuft.
    """
    import os
    import signal
    import time
    import threading

    pid_file = PROJECT_ROOT / "llmwiking.pid"

    def _kill():
        time.sleep(1)  # Browser Zeit geben, die Response zu empfangen
        try:
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text(encoding="utf-8").strip())
                    if pid and pid != os.getpid() and os.kill(pid, 0):
                        os.kill(pid, signal.SIGTERM)
                        return
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
        except Exception:
            pass
        # Fallback: eigenen Prozess beenden
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_kill, daemon=True).start()


@router.post("/settings")
async def settings_post(request: Request):
    form = await request.form()
    action = form.get("action", "")

    app_version_text = _read_version()
    update_available_flag = (PROJECT_ROOT / "update.sh").exists()
    update_log_output = None
    config_success_msg = None
    config_error_msg = None
    new_generated_mcp_key = None
    new_generated_api_key = None

    if action == "run_update":
        update_script = PROJECT_ROOT / "update.sh"
        github_token = (form.get("github_token") or "").strip()

        env = os.environ.copy()
        if github_token:
            env["GITHUB_TOKEN"] = github_token

        log_file = DATA_DIR / "update.log"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not update_script.exists():
            update_log_output = "FEHLER: update.sh nicht gefunden."
            log_file.write_text(update_log_output + "\n", encoding="utf-8")
        else:
            try:
                log_file.write_text("", encoding="utf-8")

                # ACHTUNG: async-Route -> blockierenden Subprozess via to_thread
                # auslagern, sonst friert die Event-Loop (Hänger) ein.
                proc = await asyncio.to_thread(
                    subprocess.run,
                    [str(update_script)],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(PROJECT_ROOT),
                    env=env,
                )
                # ANSI-Farbcodes aus Output entfernen (fuer saubere HTML-Anzeige)
                import re as _re
                raw_output = proc.stdout + proc.stderr
                update_log_output = _re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw_output)

                log_file.write_text(update_log_output, encoding="utf-8")

                # Automatischen Server-Neustart nach erfolgreichem Update auslösen,
                # damit direkt der neue Code im Speicher aktiv wird.
                _trigger_server_restart()
            except subprocess.TimeoutExpired:
                update_log_output = "FEHLER: Update-Skript hat 300 Sekunden ueberschritten."
                log_file.write_text(update_log_output + "\n", encoding="utf-8")
            except Exception as e:
                update_log_output = f"FEHLER: {e}"
                log_file.write_text(update_log_output + "\n", encoding="utf-8")
    elif action == "restart_server":
        # Startet den Server neu, indem der Hauptprozess beendet wird.
        # Im Docker-Container (restart: always) oder via Systemd wird der Prozess sofort neu gestartet.
        _trigger_server_restart()
        config_success_msg = "Server-Neustart wurde initiiert. Bitte lade die Seite in 5 Sekunden neu."
    elif action == "save_audit_config":
        from core.config import save_app_config
        audit_enabled = form.get("audit_enabled") == "1"
        enabled_cats = [c.strip() for c in form.getlist("audit_categories") if c.strip()]
        disabled = [c for c in ALL_CATEGORIES if c not in enabled_cats]
        save_app_config({"audit_enabled": audit_enabled, "audit_disabled_categories": disabled})
        
        user = get_current_user(request) or {}
        log_action(action="settings_change", details=f"Audit-Konfiguration gespeichert: enabled={audit_enabled}, disabled={disabled}", username=user.get("username"), user_id=user.get("id"), request=request)
        config_success_msg = "Audit-Konfiguration gespeichert!"
    elif action == "generate_mcp_keys":
        from core.config import save_app_config
        from core.storage import create_key, create_mcp_key
        
        user = get_current_user(request) or {}
        user_id = user.get("id")
        if not user_id:
            admins = [u for u in list_users() if u.get("role") == "admin"]
            user_id = admins[0]["id"] if admins else "admin"
        
        # Per-User MCP-Key mit vollem Tool-Zugriff erstellen
        all_tool_names = []
        for group in MCP_TOOL_GROUPS.values():
            all_tool_names.extend(group.get("tools", []))
        all_tool_names = sorted(set(all_tool_names))
        
        mcp_key_obj, raw_mcp_key = create_mcp_key(
            user_id=user_id,
            name="MCP-Agent-Key-Auto",
            allowed_tools=[],  # Leer = alle Tools erlaubt
        )
        
        key_obj, raw_api_key = create_key(
            user_id=user_id,
            name="MCP-Agent-API-Key",
            require_password=False,
            scopes=["read", "write"]
        )
        
        # MCP-Server aktivieren (Legacy-Key bleibt gesetzt für Rückwärtskompatibilität)
        save_app_config({
            "enable_mcp_server": True,
        })
        
        log_action(
            action="settings_change",
            details=f"Sicherer Per-User MCP-Key und passender API-Key generiert (User: {user.get('username', 'unknown')})",
            username=user.get("username"),
            user_id=user.get("id"),
            request=request,
        )
        config_success_msg = "Sicherer MCP-Key und passender API-Key wurden erfolgreich generiert! Den MCP-Key jetzt kopieren — er ist danach nicht mehr lesbar."
        new_generated_mcp_key = raw_mcp_key
        new_generated_api_key = raw_api_key
    elif action == "save_mcp_config":
        from core.config import save_app_config
        enable_mcp_server = form.get("enable_mcp_server") == "1"
        llmwiking_mcp_key = (form.get("llmwiking_mcp_key") or "").strip()
        save_app_config({
            "enable_mcp_server": enable_mcp_server,
            "llmwiking_mcp_key": llmwiking_mcp_key,
        })
        
        user = get_current_user(request) or {}
        log_action(
            action="settings_change",
            details=f"MCP-Konfiguration gespeichert: enabled={enable_mcp_server}",
            username=user.get("username"),
            user_id=user.get("id"),
            request=request,
        )
        config_success_msg = "MCP-Konfiguration erfolgreich gespeichert!"
    elif action == "save_registration":
        from core.config import save_app_config
        registration_enabled = form.get("registration_enabled") == "1"
        save_app_config({"registration_enabled": registration_enabled})
        user = get_current_user(request) or {}
        log_action(
            action="settings_change",
            details=f"Registrierung {'aktiviert' if registration_enabled else 'deaktiviert'}",
            username=user.get("username"),
            user_id=user.get("id"),
            request=request,
        )
        config_success_msg = "Registrierung wurde {}.".format("aktiviert" if registration_enabled else "deaktiviert")
    else:
        smtp_host = form.get("smtp_host", "smtp.gmail.com")
        try:
            smtp_port = int(form.get("smtp_port", "587"))
        except ValueError:
            smtp_port = 587
        smtp_user = (form.get("smtp_user") or "").strip()
        smtp_pass = (form.get("smtp_pass") or "").strip()
        use_tls = form.get("use_tls") == "1"
        recipients = (form.get("recipients") or "").strip()
        new_config = {
            "smtp_host": smtp_host, "smtp_port": smtp_port, "smtp_user": smtp_user,
            "smtp_pass": smtp_pass, "use_tls": use_tls, "recipients": recipients,
        }
        if save_smtp_config(new_config):
            config_success_msg = "Konfiguration erfolgreich in config.json gespeichert!"
        else:
            config_error_msg = "Fehler beim Speichern der Konfiguration."

    health_run_check = request.query_params.get("run") == "1"
    if health_run_check:
        h = run_lint(_default_wiki())
        health = {
            "orphans": h["orphans"], "missing": h["missing"], "stale": h["stale"],
            "missing_raw": h["missing_raw"], "issue_count": h["issue_count"],
        }
    else:
        health = {"orphans": [], "missing": [], "stale": [], "missing_raw": [], "issue_count": 0}

    smtp_config_data = load_smtp_config()
    env_user = os.environ.get("GMAIL_USER", "")
    env_pass_exists = bool(os.environ.get("GMAIL_APP_PASSWORD"))

    from core.config import load_app_config
    cfg_post = load_app_config()
    return render(
        request, "settings.html",
        active_page="settings",
        smtp_config=smtp_config_data,
        env_user=env_user,
        env_pass_exists=env_pass_exists,
        audit_config=cfg_post,
        mcp_config=cfg_post,
        all_audit_categories=ALL_CATEGORIES,
        config_success_msg=config_success_msg,
        config_error_msg=config_error_msg,
        health_run_check=health_run_check,
        health_orphans=health["orphans"],
        health_missing=health["missing"],
        health_stale=health["stale"],
        health_missing_raw=health["missing_raw"],
        health_issue_count=health["issue_count"],
        app_version=app_version_text,
        update_available=update_available_flag,
        update_log=update_log_output,
        users=list_users(),
        keys=list_keys(),
        new_key=None,
        new_generated_mcp_key=new_generated_mcp_key,
        new_generated_api_key=new_generated_api_key,
        registration_enabled=cfg_post.get("registration_enabled", True),
        mcp_keys=list_mcp_keys(),
        mcp_tool_groups=MCP_TOOL_GROUPS,
        lang=request.cookies.get("llmwiki_lang", "de"),
    )


@router.get("/briefings")
def briefings_get(request: Request):
    return _briefings(request, form=None)


@router.post("/briefings")
async def briefings_post(request: Request):
    form = await request.form()
    return _briefings(request, form=form)


def _briefings(request: Request, form):
    wiki = request.query_params.get("wiki") or _default_wiki()
    week_arg = request.query_params.get("week") or (form and form.get("week"))
    today = date.today()
    if not week_arg:
        iso = today.isocalendar()
        week_arg = f"{iso[0]}-W{iso[1]:02d}"

    try:
        year, week_num = _parse_week_string(week_arg)
    except Exception:
        iso = today.isocalendar()
        week_arg = f"{iso[0]}-W{iso[1]:02d}"
        year, week_num = iso[0], iso[1]

    start_date = date.fromisocalendar(year, week_num, 1)
    end_date = date.fromisocalendar(year, week_num, 7)

    pages = get_all_wiki_pages(wiki)
    week_pages = []

    for p in pages:
        if p["slug"] in ("index", "log", "ingestlater") or p["slug"].startswith("briefing-"):
            continue
        file_path = wiki_path(wiki) / f"{p['slug']}.md"
        if file_path.exists():
            try:
                stat = file_path.stat()
                mtime_date = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).date()
                created_date = None
                content = file_path.read_text(encoding="utf-8", errors="replace")
                fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("timestamp:"):
                            created_str = line.split(":", 1)[1].strip().strip('"\'')
                            try:
                                created_date = date.fromisoformat(created_str[:10])
                            except ValueError:
                                pass
                in_week = False
                if created_date and start_date <= created_date <= end_date:
                    in_week = True
                elif start_date <= mtime_date <= end_date:
                    in_week = True
                if in_week:
                    week_pages.append(p)
            except Exception:
                pass

    success_msg = None
    error_msg = None
    email_simulation = None
    smtp_cfg = load_smtp_config()

    if form is not None:
        action = form.get("action")
        if action == "generate":
            briefing_slug = f"briefing-{year}-w{week_num:02d}"
            briefing_path = wiki_path(wiki) / f"{briefing_slug}.md"
            list_items = [f"- **[{wp['title']}]({BASE_PATH}/wiki/{wiki}/{wp['slug']})** — {wp['desc']}" for wp in week_pages]
            list_text = "\n".join(list_items) if list_items else "- Keine neuen Einträge in dieser Woche."
            template = (
                f"---\n"
                f"type: timeline\n"
                f'title: "Wochenbericht: {year}-W{week_num:02d}"\n'
                f"description: \"Wochenbericht für die Kalenderwoche {week_num:02d} im Jahr {year}\"\n"
                f"timestamp: {today.isoformat()}T00:00:00Z\n"
                f"---\n\n"
                f"# 📰 Wochenbericht: {year}-W{week_num:02d}\n\n"
                f"Zusammenfassung des Wissenszuwachses vom {start_date.strftime('%d.%m.%Y')} bis zum {end_date.strftime('%d.%m.%Y')}.\n\n"
                f"## 🆕 Neue & geänderte Themen\n\n"
                f"{list_text}\n\n"
                f"## 🔮 Ausblick & Synthese\n"
                f"Automatisch generiertes Briefing für den Wissensspeicher.\n"
            )
            briefing_path.write_text(template, encoding="utf-8")
            request_sync_background(wiki)
            return redirect(f"{BASE_PATH}/wiki/{wiki}/{urlencode(briefing_slug)}?success_msg={urlencode('Wochenbericht erfolgreich generiert!')}")

        elif action == "email":
            to_emails = (form.get("to_emails") or "").strip()
            recipients = [e.strip() for e in to_emails.split(",") if e.strip()]
            subject = f"📰 LLMWikiNG Wochenbericht {year}-W{week_num:02d}"
            email_html = (
                f"<div style='font-family: sans-serif; max-width: 600px; margin: auto; padding: 1.5rem; border: 1px solid #ddd; border-radius: 8px; background: #fafafa; color: black;'>"
                f"<h2 style='color: #4f46e5; border-bottom: 2px solid #4f46e5; padding-bottom: 0.5rem;'>📰 LLMWikiNG Wochenbericht {year}-W{week_num:02d}</h2>"
                f"<p style='color: #555;'>Hallo,</p>"
                f"<p style='color: #555;'>hier ist deine wöchentliche Übersicht über die neuen Themen im Recht-Wiki (Zeitraum: {start_date.strftime('%d.%m.%Y')} bis {end_date.strftime('%d.%m.%Y')}):</p>"
                f"<ul style='padding-left: 1.2rem;'>"
            )
            for wp in week_pages:
                email_html += f"<li style='margin-bottom: 0.8rem;'><strong>{wp['title']}</strong> — {wp['desc']}</li>"
            if not week_pages:
                email_html += "<li style='color: #888;'>Keine neuen Einträge in dieser Woche.</li>"
            email_html += (
                f"</ul>"
                f"<hr style='border: none; border-top: 1px solid #eee; margin: 1.5rem 0;'>"
                f"<p style='font-size: 0.8rem; color: #888; text-align: center;'>Generiert von LLMWikiNG · Unlicense</p>"
                f"</div>"
            )
            try:
                sent_to = send_real_email(subject, email_html, to_list_override=recipients)
                success_msg = f"E-Mail erfolgreich an {', '.join(sent_to)} versendet!"
            except Exception as e:
                error_msg = f"Fehler beim E-Mail-Versand: {e}"
            email_simulation = {
                "to": ", ".join(recipients) if recipients else smtp_cfg.get("recipients", ""),
                "subject": subject,
                "html": email_html,
            }

    default_smtp_user = smtp_cfg.get("smtp_user") or os.environ.get("GMAIL_USER", "")
    has_env_creds = bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD")) or bool(smtp_cfg.get("smtp_user") and smtp_cfg.get("smtp_pass"))
    recipients_value = smtp_cfg.get("recipients", "")

    return render(
        request, "briefing.html",
        active_page="briefings", wiki=wiki, wikis=list_wikis(),
        week=week_arg,
        start_date=start_date,
        end_date=end_date,
        week_pages=week_pages,
        success_msg=success_msg,
        error_msg=error_msg,
        email_simulation=email_simulation,
        default_smtp_user=default_smtp_user,
        has_env_creds=has_env_creds,
        recipients_value=recipients_value,
        smtp_cfg=smtp_cfg,
    )


@router.get("/edit")
def edit_get(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    filename = request.query_params.get("filename", "")
    folder = request.query_params.get("folder", "wiki")
    content = ""

    target_dir = wiki_path(wiki) if folder == "wiki" else RAW_DIR
    error_msg = request.query_params.get("error_msg")

    if filename:
        clean_filename = filename
        if not clean_filename.endswith(".md"):
            clean_filename += ".md"
        filepath = target_dir / clean_filename
        if filepath.exists() and filepath.is_file():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                filename = clean_filename
            except Exception:
                pass

    import sys
    import markdown as _md
    from importlib.metadata import version as _pkg_version

    def _pv(pkg):
        try:
            return _pkg_version(pkg)
        except Exception:
            return "unbekannt"

    return render(
        request, "editor.html",
        active_page="editor", wiki=wiki, wikis=list_wikis(),
        filename=filename,
        content=content,
        folder=folder,
        app_version=APP_VERSION,
        python_version=sys.version.split()[0],
        markdown_version=_pv("markdown"),
        matrix_version="Matrix 3.0.0",
        jinja_version=_pv("jinja2"),
        error_msg=error_msg,
    )


@router.post("/edit/preview")
async def edit_preview(request: Request):
    form = await request.form()
    text @router.post("/edit/save")
async def edit_save(request: Request):
    user = require_login(request)
    is_json = request.headers.get("content-type", "").startswith("application/json")
    if is_json:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)

    filename = str(payload.get("filename") or "").strip()
    content = str(payload.get("content") or "")
    folder = str(payload.get("folder") or "wiki")
    wiki = str(request.query_params.get("wiki") or payload.get("wiki") or _default_wiki())
    force = bool(payload.get("force"))
    client_hash = payload.get("client_hash")

    if not filename:
        if is_json:
            return JSONResponse(status_code=400, content={"detail": "Dateiname erforderlich"})
        return redirect(f"{BASE_PATH}/edit?folder={urlencode(folder)}&error_msg={urlencode('Dateiname erforderlich')}")

    if not filename.endswith(".md"):
        filename += ".md"

    if ".." in filename.split("/") or ".." in filename.split("\\"):
        if is_json:
            return JSONResponse(status_code=400, content={"detail": "Path-Traversal blockiert"})
        return redirect(f"{BASE_PATH}/edit?folder={urlencode(folder)}&error_msg={urlencode('Path-Traversal blockiert')}")

    target_dir = wiki_path(wiki) if folder == "wiki" else RAW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = (target_dir / filename).resolve()
    if not str(filepath).startswith(str(target_dir.resolve())):
        if is_json:
            return JSONResponse(status_code=400, content={"detail": "Path-Traversal blockiert"})
        return redirect(f"{BASE_PATH}/edit?folder={urlencode(folder)}&error_msg={urlencode('Path-Traversal blockiert')}")

    try:
        if folder == "wiki":
            page_title = filename[:-3]
            content = ensure_okf_frontmatter(content, title=page_title)

        # Conflict-Detection: Prüfe ob Seite seit dem letzten Laden geändert wurde
        if folder == "wiki" and filepath.exists() and not force:
            conflict = detect_conflict(wiki, filename[:-3], content, client_loaded_hash=client_hash)
            if conflict:
                error_detail = "Konflikt erkannt: Die Seite wurde seit dem letzten Laden geändert. Bitte lade sie neu."
                if is_json:
                    return JSONResponse(status_code=409, content={"detail": error_detail, "conflict": conflict})
                return redirect(
                    f"{BASE_PATH}/edit?wiki={urlencode(wiki)}&filename={urlencode(filename)}"
                    f"&folder={urlencode(folder)}&error_msg={urlencode(error_detail)}"
                )
        
        action_type = "Update" if filepath.exists() else "Creation"
        if filepath.exists() and folder == "wiki":
            try:
                from services.history import save_version
                old_content = filepath.read_text(encoding="utf-8", errors="replace")
                save_version(wiki, filename[:-3], old_content)
            except Exception:
                pass
        filepath.write_text(content, encoding="utf-8")
        try:
            append_okf_log(action_type, filename, f"Datei im Browser-Editor bearbeitet ({folder})", wiki)
            request_sync_background(wiki)
            log_action(action="page_save", details=f"Datei '{filename}' in '{folder}' (Wiki: {wiki}) als {action_type} gespeichert", user_id=user["id"], username=user["username"], request=request)
        except Exception:
            pass

        success_msg = f"Datei '{filename}' erfolgreich in {folder}/ gespeichert."
        if folder == "wiki":
            page_slug = filename[:-3]
            redirect_url = f"{BASE_PATH}/wiki/{wiki}/{urlencode(page_slug)}?success_msg={urlencode(success_msg)}"
        else:
            redirect_url = f"{BASE_PATH}/edit?wiki={urlencode(wiki)}&folder={urlencode(folder)}&success_msg={urlencode(success_msg)}"

        if is_json:
            return JSONResponse(content={"ok": True, "redirect": redirect_url, "message": success_msg})
        return redirect(redirect_url)
    except Exception as e:
        if is_json:
            return JSONResponse(status_code=500, content={"detail": f"Fehler beim Speichern: {e}"})
        err_msg = urlencode(f"Fehler beim Speichern: {e}")
        return redirect(f"{BASE_PATH}/edit?wiki={urlencode(wiki)}&filename={urlencode(filename)}&folder={urlencode(folder)}&error_msg={err_msg}")


@router.get("/admin/clear-log")
def clear_log(request: Request, admin: dict = Depends(require_admin)):
    wiki = request.query_params.get("wiki") or "main"
    log_path = wiki_path(wiki) / "log.md"
    today = date.today().isoformat()
    try:
        template = (
            f"---\n"
            f'okf_version: "0.1"\n'
            f"---\n"
            f"# Wiki-Aktivitätslogbuch\n\n"
            f"## {today}\n"
            f"- **Clear**: Logbuch zurückgesetzt\n"
        )
        log_path.write_text(template, encoding="utf-8")
        request_sync_background(wiki)
        log_action(action="activity_log_clear", details=f"Aktivitätslogbuch für Wiki '{wiki}' geleert", user_id=admin["id"], username=admin["username"], request=request)
        return redirect(f"{BASE_PATH}/audit?success_msg={urlencode('Logbuch zurückgesetzt. Alle Aktivitäten werden im Audit-Log erfasst.')}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/audit?error_msg={urlencode(f'Fehler beim Leeren des Logbuchs: {e}')}")


from fastapi.responses import FileResponse
from fastapi import UploadFile, File

@router.get("/settings/backup")
def settings_backup(request: Request):
    from services.backup import create_backup_xz
    from datetime import datetime
    
    backup_filename = f"llmwiki_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.xz"
    backup_path = PROJECT_ROOT / "data" / backup_filename
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    create_backup_xz(backup_path)
    return FileResponse(path=backup_path, filename=backup_filename, media_type="application/x-xz")

@router.post("/settings/restore")
async def settings_restore(request: Request, backup_file: UploadFile = File(...)):
    from services.backup import restore_backup_xz
    from core.storage import list_users, save_users
    from api.deps import get_current_user
    from services.audit import log_action
    
    current_user = get_current_user(request)
    current_uid = current_user.get("id") if current_user else None
    current_username = current_user.get("username") if current_user else None
    current_hash = current_user.get("password") if current_user else None
    current_role = current_user.get("role", "admin") if current_user else "admin"

    temp_archive = PROJECT_ROOT / "data" / "temp_restore.tar.xz"
    temp_archive.parent.mkdir(parents=True, exist_ok=True)
    
    with open(temp_archive, "wb") as f:
        f.write(await backup_file.read())
        
    try:
        restore_backup_xz(temp_archive)
        if current_username and current_hash and current_uid:
            users = list_users()
            user_exists = False
            for u in users:
                if u.get("username") == current_username:
                    user_exists = True
                    u["id"] = current_uid
                    break
            if not user_exists:
                users.append({"id": current_uid, "username": current_username, "password": current_hash, "role": current_role, "active": True})
            save_users(users)
            
        if temp_archive.exists():
            temp_archive.unlink()
            
        log_action(action="backup_restore", details="Backup aus Upload-Datei wiederhergestellt", username=current_username, user_id=current_uid, request=request)
        from services.sync import request_sync_background
        request_sync_background("main")
            
        return redirect(f"{BASE_PATH}/settings?tab=backup&config_success_msg={urlencode('Backup erfolgreich wiederhergestellt!')}")
    except Exception as e:
        if temp_archive.exists():
            temp_archive.unlink()
        return redirect(f"{BASE_PATH}/settings?tab=backup&config_error_msg={urlencode(f'Restore fehlgeschlagen: {e}')}")

@router.post("/settings/backup/create")
async def settings_backup_create(request: Request):
    """Erstellt ein neues Backup auf dem Server."""
    user = require_login(request)
    from services.backup import create_backup_xz
    from services.audit import log_action
    
    b_path = create_backup_xz()
    log_action(action="backup_create", details=f"Server-Backup erstellt: {b_path.name}", username=user.get("username"), user_id=user.get("id"), request=request)
    return redirect(f"{BASE_PATH}/settings?tab=backup&config_success_msg={urlencode(f'Server-Backup {b_path.name} erfolgreich erstellt!')}")

@router.get("/settings/backup/download/{filename}")
def settings_backup_download(filename: str, request: Request):
    """Lädt ein bestimmtes Server-Backup herunter."""
    require_login(request)
    from services.backup import get_backup_filepath
    b_path = get_backup_filepath(filename)
    if not b_path:
        raise HTTPException(status_code=404, detail="Backup-Datei nicht gefunden")
    return FileResponse(path=b_path, filename=b_path.name, media_type="application/x-xz")

@router.post("/settings/backup/restore/{filename}")
async def settings_backup_restore_server(filename: str, request: Request):
    """Stellt ein auf dem Server gespeichertes Backup wieder her."""
    from services.backup import get_backup_filepath, restore_backup_xz
    from core.storage import list_users, save_users
    from api.deps import get_current_user
    from services.audit import log_action
    
    b_path = get_backup_filepath(filename)
    if not b_path:
        return redirect(f"{BASE_PATH}/settings?tab=backup&config_error_msg={urlencode('Backup-Datei nicht gefunden')}")

    current_user = get_current_user(request)
    current_uid = current_user.get("id") if current_user else None
    current_username = current_user.get("username") if current_user else None
    current_hash = current_user.get("password") if current_user else None
    current_role = current_user.get("role", "admin") if current_user else "admin"

    try:
        restore_backup_xz(b_path)
        if current_username and current_hash and current_uid:
            users = list_users()
            user_exists = False
            for u in users:
                if u.get("username") == current_username:
                    user_exists = True
                    u["id"] = current_uid
                    break
            if not user_exists:
                users.append({"id": current_uid, "username": current_username, "password": current_hash, "role": current_role, "active": True})
            save_users(users)
        
        log_action(action="backup_restore", details=f"Server-Backup wiederhergestellt: {b_path.name}", username=current_username, user_id=current_uid, request=request)
        from services.sync import request_sync_background
        request_sync_background("main")
        return redirect(f"{BASE_PATH}/settings?tab=backup&config_success_msg={urlencode(f'Server-Backup {b_path.name} erfolgreich wiederhergestellt!')}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/settings?tab=backup&config_error_msg={urlencode(f'Restore fehlgeschlagen: {e}')}")

@router.post("/settings/backup/delete/{filename}")
async def settings_backup_delete(filename: str, request: Request):
    """Löscht eine Server-Backup-Datei."""
    user = require_login(request)
    from services.backup import delete_server_backup
    from services.audit import log_action
    ok = delete_server_backup(filename)
    if ok:
        log_action(action="backup_delete", details=f"Server-Backup gelöscht: {filename}", username=user.get("username"), user_id=user.get("id"), request=request)
        return redirect(f"{BASE_PATH}/settings?tab=backup&config_success_msg={urlencode(f'Backup {filename} gelöscht.')}")
    return redirect(f"{BASE_PATH}/settings?tab=backup&config_error_msg={urlencode('Fehler beim Löschen des Backups.')}")


@router.get("/audit")
def audit_dashboard(
    request: Request,
    admin: dict = Depends(require_admin),
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    category: str | None = None,
    username: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
):
    from services.audit import get_logs, ALL_CATEGORIES
    from datetime import datetime
    
    logs, total = get_logs(
        limit=limit,
        offset=offset,
        action=action,
        category=category,
        username=username,
        start_date=start_date,
        end_date=end_date,
        search=search,
    )
    
    return render(
        request, "audit.html",
        active_page="audit",
        wiki=_default_wiki(),
        wikis=list_wikis(),
        logs=logs,
        total=total,
        limit=limit,
        offset=offset,
        action_filter=action,
        category_filter=category,
        search_filter=search,
        user_filter=username,
        start_date=start_date,
        end_date=end_date,
        all_categories=ALL_CATEGORIES,
        now_year=datetime.now().year,
        success_msg=request.query_params.get("success_msg"),
        error_msg=request.query_params.get("error_msg")
    )

@router.post("/audit/prune")
async def audit_prune(request: Request, admin: dict = Depends(require_admin)):
    from services.audit import prune_logs
    form = await request.form()
    try:
        year = int(form.get("year", "2026"))
        month_str = form.get("month", "")
        month = int(month_str) if month_str else None
        
        deleted = prune_logs(year, month)
        details = f"Logs gelöscht vor {month_str + '/' if month_str else ''}{year}"
        log_action(action="audit_prune", details=details, user_id=admin["id"], username=admin["username"], request=request)
        return redirect(f"{BASE_PATH}/audit?success_msg={urlencode(f'{deleted} Log-Einträge erfolgreich gelöscht.')}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/audit?error_msg={urlencode(f'Fehler beim Löschen: {e}')}")


@router.get("/audit/export")
def audit_export(
    request: Request,
    admin: dict = Depends(require_admin),
    fmt: str = "json",
    action: str | None = None,
    category: str | None = None,
    username: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
):
    from services.audit import get_all_logs, export_logs_csv
    from starlette.responses import Response, JSONResponse
    
    logs = get_all_logs(
        action=action,
        category=category,
        username=username,
        start_date=start_date,
        end_date=end_date,
        search=search,
    )
    
    log_action(action="audit_export", details=f"Audit-Logs exportiert (Format: {fmt}, {len(logs)} Einträge)", user_id=admin["id"], username=admin["username"], request=request)
    
    if fmt == "csv":
        csv_data = export_logs_csv(logs)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )
    else:
        return JSONResponse(
            content={"logs": logs, "count": len(logs)},
            headers={"Content-Disposition": "attachment; filename=audit_logs.json"},
        )



@router.get("/wiki/{wiki_name}/{page_name}")
async def wiki_page(wiki_name: str, page_name: str, request: Request):
    return await _render_page(wiki_name, page_name, request)


@router.get("/wiki/{wiki_name}/{page_name}/history")
async def wiki_page_history(wiki_name: str, page_name: str, request: Request):
    user = require_login(request)
    from services.history import list_versions
    versions = list_versions(wiki_name, page_name)
    return JSONResponse(content={"wiki": wiki_name, "slug": page_name, "versions": versions})


@router.get("/wiki/{wiki_name}/{page_name}/history/{version_id}")
async def wiki_page_version(wiki_name: str, page_name: str, version_id: str, request: Request):
    user = require_login(request)
    from services.history import get_version
    content = get_version(wiki_name, page_name, version_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Version nicht gefunden")
    return JSONResponse(content={"wiki": wiki_name, "slug": page_name, "version_id": version_id, "content": content})

