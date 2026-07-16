"""LLMWikiNG – Alle HTML-Routen, Form-POSTs und JSON-Endpoints.

Multi-Wiki-fähig, unter BASE_PATH gemountet und durch require_login geschützt.
"""

from __future__ import annotations

import os
import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile

from core.config import (
    PROJECT_ROOT,
    WIKI_DIR,
    RAW_DIR,
    EXPORT_DIR,
    SCRATCH_DIR,
    APP_VERSION,
    QMD_BIN,
    BASE_PATH,
    CONFIG_FILE,
    load_app_config,
    slugify_wiki,
    wiki_path,
    list_wikis,
    save_wiki_meta,
)
from web import templates, render, abort, redirect, urlencode
from api.deps import require_login
from core.storage import list_users, list_keys
from services.wiki import (
    get_all_wiki_pages,
    get_wiki_stats,
    read_wiki_file,
    is_text_file,
    find_wiki_slug_for_raw,
    get_pending_files,
    save_to_ingestlater,
    get_recent_logs,
    get_wiki_trails,
    extract_links_from_content,
    slugify_german,
)
from services.markdown import render_markdown, render_markdown_preview
from services.search import qmd_search, local_search
from services.sync import is_sync_needed, do_sync, append_okf_log
from services.graph import build_graph_data
from services.lint import run_lint
from services.analytics import get_wiki_analytics
from services.editor import ensure_okf_frontmatter
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
    return wikis[0]["name"] if wikis else "main"


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard (Wiki-Übersicht)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/")
def dashboard(request: Request):
    query = request.query_params.get("q", "").strip()
    if query:
        return redirect(f"{BASE_PATH}/search?q={urlencode(query)}")

    wikis = list_wikis()
    default = _default_wiki()

    # Per-Wiki-Statistiken + Gesamtwerte für die Übersicht
    wiki_stats = []
    total_pages = total_words = total_raw = total_export = 0
    for w in wikis:
        s = get_wiki_stats(w["name"])
        wiki_stats.append({"name": w["name"], "stats": s})
        total_pages += s["page_count"]
        total_words += s["word_count"]
        total_raw += s["raw_count"]
        total_export += s["export_count"]

    recent_logs = get_recent_logs(default, 5)
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


# ═══════════════════════════════════════════════════════════════════════════════
# Wiki anlegen
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/wikis/new")
def wiki_new_form(request: Request):
    return render(request, "wiki_new.html", active_page="wiki_new", error=request.query_params.get("error"))


@router.post("/wikis/new")
async def wiki_new_create(request: Request):
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
    return redirect(f"{BASE_PATH}/wiki/{safe}/")


# ═══════════════════════════════════════════════════════════════════════════════
# Wiki-Home + Wiki-Seiten
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/wiki/{wiki_name}/")
def wiki_home(wiki_name: str, request: Request):
    return _render_page(wiki_name, "index", request)


def _render_page(wiki_name: str, page_name: str, request: Request):
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
            subprocess.run(["./wiki.sh", "sync"], capture_output=True, cwd=str(PROJECT_ROOT))
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

    return render(
        request, "page.html",
        wiki=wiki_name,
        active_page=page_name,
        page_title=data["name"].replace("-", " ").title(),
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
    )


@router.get("/wiki/{wiki_name}/{page_name}/export")
def wiki_export(wiki_name: str, page_name: str, request: Request):
    page_name = re.sub(r"\.md$", "", page_name)
    src_file = wiki_path(wiki_name) / f"{page_name}.md"
    if not src_file.exists():
        abort(404, f"Seite '{page_name}' existiert nicht.")

    try:
        EXPORT_DIR.mkdir(exist_ok=True)
        dest_file = EXPORT_DIR / f"{wiki_name}__{page_name}.md"
        dest_file.write_text(src_file.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            append_okf_log("export", page_name, f"Seite exportiert nach {dest_file.relative_to(PROJECT_ROOT)}", wiki_name)
        except Exception:
            pass
        success_msg = f"Seite '{page_name}.md' erfolgreich nach output_docs/ exportiert!"
        return redirect(f"{BASE_PATH}/wiki/{wiki_name}/{urlencode(page_name)}?success_msg={urlencode(success_msg)}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/wiki/{wiki_name}/{urlencode(page_name)}?error_msg={urlencode(f'Export fehlgeschlagen: {e}')}")


@router.get("/wiki/{wiki_name}/{page_name}/delete")
def wiki_delete(wiki_name: str, page_name: str, request: Request):
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
        except Exception:
            pass
        do_sync(wiki_name)
        success_msg = f"Seite '{page_name}.md' erfolgreich gelöscht."
        return redirect(f"{BASE_PATH}/wiki/{wiki_name}/?sync_status={urlencode(success_msg)}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/wiki/{wiki_name}/{urlencode(page_name)}?error_msg={urlencode(f'Löschen fehlgeschlagen: {e}')}")


# ═══════════════════════════════════════════════════════════════════════════════
# Rohquellen
# ═══════════════════════════════════════════════════════════════════════════════

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
                mtime_formatted = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
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
        mtime_formatted = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
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


# ═══════════════════════════════════════════════════════════════════════════════
# Pending
# ═══════════════════════════════════════════════════════════════════════════════

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
def pending_ingest_single(filename: str, request: Request):
    filepath = RAW_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        abort(404, f"Datei '{filename}' nicht im raw/ Ordner gefunden.")

    try:
        backend = os.environ.get("LLM_BACKEND", "ollama")
        env = os.environ.copy()
        env["LLM_BACKEND"] = backend
        result = subprocess.run(
            ["./wiki.sh", "ingest", str(filepath)],
            capture_output=True, text=True, timeout=120,
            cwd=str(PROJECT_ROOT), env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"Ingest fehlgeschlagen (Exitcode {result.returncode})")

        today_prefix = datetime.now().strftime("%Y-%m-%d")
        if not filename.startswith(today_prefix):
            try:
                filepath.unlink()
            except Exception:
                pass

        do_sync("main")
        success_msg = f"Datei '{filename}' wurde erfolgreich ingestiert!"
        return redirect(f"{BASE_PATH}/pending?success_msg={urlencode(success_msg)}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/pending?error_msg={urlencode(f'Fehler beim Ingest von {filename}: {e}')}")


@router.get("/pending/ingest-all")
def pending_ingest_all(request: Request):
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
            result = subprocess.run(
                ["./wiki.sh", "ingest", str(filepath)],
                capture_output=True, text=True, timeout=120,
                cwd=str(PROJECT_ROOT), env=env,
            )
            if result.returncode == 0:
                success_count += 1
                today_prefix = datetime.now().strftime("%Y-%m-%d")
                if not filename.startswith(today_prefix):
                    try:
                        filepath.unlink()
                    except Exception:
                        pass
            else:
                errors.append(f"{filename}: {result.stderr.strip()}")
        except Exception as e:
            errors.append(f"{filename}: {e}")

    do_sync("main")

    if success_count > 0:
        msg = f"{success_count} Datei(en) erfolgreich ingestiert!"
        if errors:
            msg += f" (Fehler bei: {', '.join(errors)})"
        return redirect(f"{BASE_PATH}/pending?success_msg={urlencode(msg)}")
    err_msg = f"Ingest fehlgeschlagen: {'; '.join(errors)}"
    return redirect(f"{BASE_PATH}/pending?error_msg={urlencode(err_msg)}")


# ═══════════════════════════════════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/export")
def export_list(request: Request):
    files = []
    if EXPORT_DIR.exists():
        for f in sorted(EXPORT_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep":
                stat = f.stat()
                size_kb = stat.st_size / 1024
                size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
                mtime_formatted = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                files.append({"name": f.name, "size_formatted": size_formatted, "mtime_formatted": mtime_formatted})
    return render(request, "export_list.html", active_page="export_list", files=files)


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
        mtime_formatted = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
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


# ═══════════════════════════════════════════════════════════════════════════════
# Graph
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/graph")
def graph_page(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    return render(request, "graph.html", active_page="graph", wiki=wiki, wikis=list_wikis())


@router.get("/graph/data")
def graph_data(request: Request):
    from fastapi.responses import JSONResponse

    wiki = request.query_params.get("wiki") or _default_wiki()
    return JSONResponse(build_graph_data(wiki))


# ═══════════════════════════════════════════════════════════════════════════════
# Ingest
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/ingest")
def ingest_get(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    return render(
        request, "ingest.html",
        active_page="ingest", wiki=wiki,
        success_msg=None, error_msg=None, new_slug=None, is_later=False,
    )


@router.post("/ingest")
async def ingest_post(request: Request):
    success_msg = None
    error_msg = None
    new_slug = None
    is_later = False
    wiki = (request.query_params.get("wiki") or _default_wiki())

    form = await request.form()
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
            success_msg = "URL erfolgreich in ingestlater.md gespeichert!"
            is_later = True

        elif ingest_type == "text_later":
            title = (form.get("title") or "").strip()
            content = (form.get("content") or "").strip()
            if not title or not content:
                raise ValueError("Titel und Inhalt dürfen nicht leer sein.")
            save_to_ingestlater("text", title, content, wiki)
            success_msg = "Text erfolgreich in ingestlater.md gespeichert!"
            is_later = True

        elif ingest_type == "file":
            upload = form.get("file")
            if not isinstance(upload, UploadFile) or not upload.filename:
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
            env = os.environ.copy()
            env["LLM_BACKEND"] = backend
            cmd = ["./wiki.sh", "ingest", str(filepath)]
            custom_title = (form.get("title") or "").strip()
            if custom_title and ingest_type == "file":
                cmd += ["--title", custom_title]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                cwd=str(PROJECT_ROOT), env=env,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or f"Ingest fehlgeschlagen mit Exitcode {result.returncode}")

            title_to_slug = custom_title if (custom_title and ingest_type == "file") else (form.get("title") or "").strip()
            if not title_to_slug and filepath:
                try:
                    f_content = filepath.read_text(encoding="utf-8")
                    h1_match = re.search(r"^#\s+(.+)$", f_content, re.MULTILINE)
                    if h1_match:
                        title_to_slug = h1_match.group(1).strip()
                except Exception:
                    pass
            if not title_to_slug:
                title_to_slug = Path(orig_filename).stem

            new_slug = slugify_german(title_to_slug)
            success_msg = f"Quelle erfolgreich eingespielt! ({new_slug}.md)"
            do_sync("main")

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
        success_msg=success_msg, error_msg=error_msg, new_slug=new_slug, is_later=is_later,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Suche
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/search")
def search(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    query = request.query_params.get("q", "").strip()
    results = []
    error = None
    sync_hint = False

    page_count = len(get_all_wiki_pages(wiki))

    if query:
        if page_count > 0 and is_sync_needed(wiki):
            sync_hint = True

        search_result = qmd_search(query)
        if search_result.get("error"):
            if "not found" in search_result.get("error", "").lower() or "timeout" in search_result.get("error", "").lower():
                do_sync(wiki)
                search_result = qmd_search(query)
                sync_hint = False
            else:
                error = search_result["error"]

        if not error:
            for r in search_result.get("results", []):
                r["title_html"] = _highlight_text(r["title"], query)
                r["snippet_html"] = _highlight_text(r["snippet"], query)
                results.append(r)

        if not results and page_count > 0 and is_sync_needed(wiki):
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
        slug_exists = target_slug in {p["slug"] for p in get_all_wiki_pages(wiki)}
    else:
        raw_mentions_count = 0
        slug_exists = False

    return render(
        request, "search.html",
        active_page="search", wiki=wiki, wikis=list_wikis(),
        query=query, results=results, error=error, sync_hint=sync_hint,
        page_count=page_count,
        raw_mentions_count=raw_mentions_count if query else 0,
        slug_exists=slug_exists if query else False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Sprache
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/lang/{code}")
def switch_language(code: str, request: Request):
    from core.config import get_available_languages, load_app_config, CONFIG_FILE
    import json as _json

    available = get_available_languages()
    if code not in available:
        code = "en"
    referrer = request.headers.get("referer") or f"{BASE_PATH}/"
    response = redirect(referrer)
    response.set_cookie("llmwiki_lang", code, max_age=365 * 24 * 3600)
    # Sprache dauerhaft in config.json sichern (einzige Einstellungsquelle)
    try:
        data = load_app_config()
        data["language"] = code
        CONFIG_FILE.write_text(_json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass
    return response


# ═══════════════════════════════════════════════════════════════════════════════
# Über
# ═══════════════════════════════════════════════════════════════════════════════

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
def about(request: Request):
    from core.config import resolve_lang
    lang = resolve_lang(
        request.query_params.get("lang"),
        request.cookies.get("llmwiki_lang"),
    )
    template = "about_de.html" if lang == "de" else "about.html"
    try:
        qmd_ver = subprocess.run([QMD_BIN, "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        qmd_ver = "nicht gefunden"

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
        qmd_version=qmd_ver,
        uvicorn_version=_pv("uvicorn"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Admin / Sync / Status
# ═══════════════════════════════════════════════════════════════════════════════

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
def admin_sync(request: Request):
    from fastapi.responses import JSONResponse

    wiki = request.query_params.get("wiki") or _default_wiki()
    results = do_sync(wiki)
    fmt = request.query_params.get("format", "html")
    if fmt == "json":
        return JSONResponse({
            "success": results["qmd"] and results["index"],
            "qmd": results["qmd"],
            "index": results["index"],
            "messages": results["messages"],
        })
    status = "✅ Sync erfolgreich!" if (results["qmd"] and results["index"]) else "⚠ Sync teilweise fehlgeschlagen"
    messages = "; ".join(results["messages"])
    return redirect(f"{BASE_PATH}/?sync_status={urlencode(status)}&sync_msg={urlencode(messages)}")


@router.get("/admin/update")
def admin_update(request: Request):
    return redirect(f"{BASE_PATH}/settings?tab=update")


@router.post("/admin/update/run")
def admin_update_run(request: Request):
    return redirect(f"{BASE_PATH}/settings?tab=update")


@router.get("/admin/update/check")
def admin_update_check(request: Request):
    from fastapi.responses import JSONResponse
    import re
    github_token = request.query_params.get("github_token", "").strip()

    env = os.environ.copy()
    if github_token:
        env["GITHUB_TOKEN"] = github_token

    version_file = PROJECT_ROOT / "VERSION"
    local_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unbekannt"
    try:
        # Falls ein Token übergeben wurde, die Git Remote-URL anpassen
        if github_token:
            original_url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5, cwd=str(PROJECT_ROOT)).stdout.strip()
            clean_url = re.sub(r"https://[^@]+@", "https://", original_url)
            auth_url = clean_url.replace("https://", f"https://{github_token}@")
            subprocess.run(["git", "remote", "set-url", "origin", auth_url], timeout=5, cwd=str(PROJECT_ROOT))

        subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT), env=env)
        proc = subprocess.run(["git", "show", "origin/main:VERSION"], capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT), env=env)
        github_version = proc.stdout.strip()
        if not github_version or proc.returncode != 0:
            github_version = None
    except Exception:
        github_version = None

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
    for tool in ("qmd", "jq", "ollama", "agy", "opencode"):
        tools[tool] = subprocess.run(["command", "-v", tool], shell=True, capture_output=True).returncode == 0

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


# ═══════════════════════════════════════════════════════════════════════════════
# Lint
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/lint")
def lint_dashboard(request: Request):
    wiki = request.query_params.get("wiki") or _default_wiki()
    run_check = request.query_params.get("run", "0") == "1"
    if run_check:
        res = run_lint(wiki)
    else:
        res = {
            "orphans": [], "missing": [], "stale": [], "missing_raw": [],
            "missing_type": [], "broken_links": [], "issue_count": 0,
        }
    return render(
        request, "lint.html",
        active_page="lint", wiki=wiki, wikis=list_wikis(),
        run_check=run_check,
        orphans=res["orphans"],
        missing=res["missing"],
        stale=res["stale"],
        missing_raw=res["missing_raw"],
        missing_type=res["missing_type"],
        broken_links=res["broken_links"],
        issue_count=res["issue_count"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# E-Mail-Konfiguration (/config)
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# Einstellungen
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/settings")
def settings_get(request: Request):
    app_version_text = _read_version()
    update_available_flag = (PROJECT_ROOT / "update.sh").exists()
    update_log_output = request.query_params.get("update_log")

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

    return render(
        request, "settings.html",
        active_page="settings",
        smtp_config=smtp_config_data,
        env_user=env_user,
        env_pass_exists=env_pass_exists,
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
    )


@router.post("/settings")
async def settings_post(request: Request):
    form = await request.form()
    action = form.get("action", "")

    app_version_text = _read_version()
    update_available_flag = (PROJECT_ROOT / "update.sh").exists()
    update_log_output = None
    config_success_msg = None
    config_error_msg = None

    if action == "run_update":
        update_script = PROJECT_ROOT / "update.sh"
        github_token = (form.get("github_token") or "").strip()
        
        env = os.environ.copy()
        if github_token:
            env["GITHUB_TOKEN"] = github_token

        if not update_script.exists():
            update_log_output = "FEHLER: update.sh nicht gefunden."
        else:
            try:
                proc = subprocess.run(
                    [str(update_script)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(PROJECT_ROOT),
                    env=env
                )
                update_log_output = proc.stdout + proc.stderr
            except subprocess.TimeoutExpired:
                update_log_output = "FEHLER: Update-Skript hat 120 Sekunden überschritten."
            except Exception as e:
                update_log_output = f"FEHLER: {e}"
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
        registration_enabled = form.get("registration_enabled") == "1"
        new_config = {
            "smtp_host": smtp_host, "smtp_port": smtp_port, "smtp_user": smtp_user,
            "smtp_pass": smtp_pass, "use_tls": use_tls, "recipients": recipients,
            "registration_enabled": registration_enabled,
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

    return render(
        request, "settings.html",
        active_page="settings",
        smtp_config=smtp_config_data,
        env_user=env_user,
        env_pass_exists=env_pass_exists,
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
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Briefings
# ═══════════════════════════════════════════════════════════════════════════════

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
                mtime_date = date.fromtimestamp(stat.st_mtime)
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
            do_sync(wiki)
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


# ═══════════════════════════════════════════════════════════════════════════════
# Editor
# ═══════════════════════════════════════════════════════════════════════════════

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

    try:
        qmd_version = subprocess.run([QMD_BIN, "--version"], capture_output=True, text=True).stdout.strip()
    except Exception:
        qmd_version = "nicht installiert"

    return render(
        request, "editor.html",
        active_page="editor", wiki=wiki, wikis=list_wikis(),
        filename=filename,
        content=content,
        folder=folder,
        app_version=APP_VERSION,
        python_version=sys.version.split()[0],
        markdown_version=_pv("markdown"),
        qmd_version=qmd_version,
        jinja_version=_pv("jinja2"),
        error_msg=error_msg,
    )


@router.post("/edit/preview")
async def edit_preview(request: Request):
    form = await request.form()
    text = form.get("content", "")
    text = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)
    return render_markdown_preview(text)


@router.post("/edit/save")
async def edit_save(request: Request):
    form = await request.form()
    filename = (form.get("filename") or "").strip()
    content = form.get("content", "")
    folder = form.get("folder", "wiki")
    wiki = (request.query_params.get("wiki") or form.get("wiki") or _default_wiki())

    if not filename:
        return redirect(f"{BASE_PATH}/edit?folder={urlencode(folder)}&error_msg={urlencode('Dateiname erforderlich')}")

    if not filename.endswith(".md"):
        filename += ".md"

    target_dir = wiki_path(wiki) if folder == "wiki" else RAW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / filename

    try:
        if folder == "wiki":
            page_title = filename[:-3]
            content = ensure_okf_frontmatter(content, title=page_title)
        filepath.write_text(content, encoding="utf-8")

        try:
            action_type = "Update" if filepath.exists() else "Creation"
            append_okf_log(action_type, filename, f"Datei im Browser-Editor bearbeitet ({folder})", wiki)
            do_sync(wiki)
        except Exception:
            pass

        success_msg = f"Datei '{filename}' erfolgreich in {folder}/ gespeichert."
        if folder == "wiki":
            page_slug = filename[:-3]
            return redirect(f"{BASE_PATH}/wiki/{wiki}/{urlencode(page_slug)}?success_msg={urlencode(success_msg)}")
        return redirect(f"{BASE_PATH}/edit?wiki={urlencode(wiki)}&folder={urlencode(folder)}&success_msg={urlencode(success_msg)}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/edit?wiki={urlencode(wiki)}&filename={urlencode(filename)}&folder={urlencode(folder)}&error_msg={urlencode(f'Fehler beim Speichern: {e}')}")


# ═══════════════════════════════════════════════════════════════════════════════
# Admin: Logbuch leeren
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/clear-log")
def clear_log(request: Request):
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
        do_sync(wiki)
        return redirect(f"{BASE_PATH}/wiki/{wiki}/log?success_msg={urlencode('Logbuch erfolgreich geleert!')}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/wiki/{wiki}/log?error_msg={urlencode(f'Fehler beim Leeren des Logbuchs: {e}')}")


# ═══════════════════════════════════════════════════════════════════════════════
# Backup & Restore
# ═══════════════════════════════════════════════════════════════════════════════
from fastapi.responses import FileResponse
from fastapi import UploadFile, File

@router.get("/settings/backup")
def settings_backup(request: Request):
    from services.backup import create_backup_xz
    from datetime import datetime
    
    backup_filename = f"llmwiki_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.xz"
    backup_path = PROJECT_ROOT / "data" / backup_filename
    
    # Sicherstellen, dass der data/-Ordner existiert
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    
    create_backup_xz(backup_path)
    return FileResponse(
        path=backup_path,
        filename=backup_filename,
        media_type="application/x-xz",
    )

@router.post("/settings/restore")
async def settings_restore(request: Request, backup_file: UploadFile = File(...)):
    from services.backup import restore_backup_xz
    from core.storage import list_users, save_users
    from api.deps import get_current_user
    
    # Aktuelle Benutzer-Details sichern, um Session-Verlust vorzubeugen
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
        
        # Abgleich nach dem Restore
        if current_username and current_hash and current_uid:
            users = list_users()
            user_exists = False
            for u in users:
                if u.get("username") == current_username:
                    user_exists = True
                    # Gleicher Name -> ID anpassen, damit Session aktiv bleibt, aber Passwort aus Backup überschreibt
                    u["id"] = current_uid
                    break
            
            if not user_exists:
                # Name nicht vorhanden -> User anlegen, um Aussperren zu verhindern
                users.append({
                    "id": current_uid,
                    "username": current_username,
                    "password": current_hash,
                    "role": current_role,
                    "active": True
                })
            save_users(users)
            
        if temp_archive.exists():
            temp_archive.unlink()
            
        # qmd Suchindizes neu synchronisieren nach dem Restore
        from services.sync import do_sync
        do_sync("main")
            
        return redirect(f"{BASE_PATH}/settings?success_msg={urlencode('Backup erfolgreich wiederhergestellt!')}")
    except Exception as e:
        if temp_archive.exists():
            temp_archive.unlink()
        return redirect(f"{BASE_PATH}/settings?error_msg={urlencode(f'Restore fehlgeschlagen: {e}')}")


# ═══════════════════════════════════════════════════════════════════════════════
# Wiki-Seite (Catch-All – MUSS zuletzt stehen!)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/wiki/{wiki_name}/{page_name}")
def wiki_page(wiki_name: str, page_name: str, request: Request):
    return _render_page(wiki_name, page_name, request)
