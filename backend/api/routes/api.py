"""LLMWikiNG – Öffentliche JSON-API (geschützt durch API-Keys).

Alle Endpunkte erfordern einen gültigen API-Key (Header `X-API-Key` oder Query
`api_key`). Schlüssel mit `require_password` benötigen zusätzlich `X-API-Password`
bzw. `api_password` (Anforderung 4).
"""

from __future__ import annotations

import os
import re
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from core.config import BASE_PATH, wiki_path, list_wikis, RAW_DIR, EXPORT_DIR, PROJECT_ROOT, APP_VERSION, Path
from api.deps import get_api_user, require_api_admin
from core.storage import (
    list_users,
    create_user,
    delete_user,
    list_keys,
    create_key,
    delete_key,
)
from services.wiki import get_all_wiki_pages, get_wiki_stats, read_wiki_file, get_pending_files, slugify_german
from services.search import local_search, qmd_search
from services.graph import build_graph_data, build_graph_data_paginated
from services.lint import run_lint
from services.editor import ensure_okf_frontmatter
from services.sync import do_sync, append_okf_log
from services.audit import log_action

router = APIRouter(prefix=f"{BASE_PATH}/api/v1")


def _wiki_or_404(wiki: str):
    root = wiki_path(wiki)
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Wiki '{wiki}' nicht gefunden")
    return root


@router.get("/wikis")
def api_list_wikis(user: dict = Depends(get_api_user)):
    return {"wikis": list_wikis()}


@router.get("/wikis/{wiki}/pages")
def api_list_pages(wiki: str, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    return {"wiki": wiki, "pages": get_all_wiki_pages(wiki)}


@router.get("/wikis/{wiki}/pages/{slug}")
def api_get_page(wiki: str, slug: str, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    data = read_wiki_file(f"{slug}.md", wiki)
    if not data:
        raise HTTPException(status_code=404, detail="Seite nicht gefunden")
    return {"wiki": wiki, "slug": slug, "content": data["content"], "frontmatter": data.get("frontmatter", {})}


@router.post("/wikis/{wiki}/pages")
async def api_create_page(wiki: str, request: Request, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    body = await request.json()
    slug = (body.get("slug") or "").strip()
    content = body.get("content", "")
    if not slug:
        raise HTTPException(status_code=400, detail="slug erforderlich")
    slug = re.sub(r"\.md$", "", slug)
    if slug in ("index", "log", "ingestlater"):
        raise HTTPException(status_code=400, detail="System-Seite kann nicht überschrieben werden")
    filepath = wiki_path(wiki) / f"{slug}.md"
    filepath.write_text(ensure_okf_frontmatter(content, title=slug), encoding="utf-8")
    try:
        append_okf_log("api-create", f"{slug}.md", "Über API erstellt", wiki)
        do_sync(wiki)
    except Exception:
        pass
    return {"ok": True, "wiki": wiki, "slug": slug}


@router.get("/wikis/{wiki}/graph")
def api_graph(wiki: str, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    return build_graph_data(wiki)


@router.get("/wikis/{wiki}/graph/paginated")
def api_graph_paginated(
    wiki: str,
    page: int = 0,
    page_size: int = 200,
    tag: str = "",
    user: dict = Depends(get_api_user),
):
    """Paginierter Graph-Endpunkt für große Wikis (>500 Knoten).

    Query-Parameter:
        page: Null-basierter Seitenindex (default 0).
        page_size: Knoten pro Seite (default 200, max 1000).
        tag: Optionaler Tag-Filter.
    """
    _wiki_or_404(wiki)
    page_size = min(max(1, page_size), 1000)
    return build_graph_data_paginated(
        wiki,
        page=page,
        page_size=page_size,
        tag_filter=tag or None,
    )


@router.get("/cache/stats")
def api_cache_stats(admin: dict = Depends(require_api_admin)):
    """Gibt aktuelle Cache-Statistiken zurück (nur Admin)."""
    from services.cache import get_cache
    return get_cache().stats()


@router.post("/cache/clear")
def api_cache_clear(admin: dict = Depends(require_api_admin)):
    """Leert den gesamten In-Memory-Cache (nur Admin)."""
    from services.cache import get_cache
    get_cache().clear()
    return {"ok": True, "message": "Cache geleert"}


@router.get("/wikis/{wiki}/stats")
def api_stats(wiki: str, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    return {"wiki": wiki, **get_wiki_stats(wiki)}


@router.get("/wikis/{wiki}/lint")
def api_lint(wiki: str, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    return run_lint(wiki)


@router.get("/search")
def api_search(q: str = "", wiki: str = "main", user: dict = Depends(get_api_user)):
    if not q:
        return {"query": q, "results": [], "local": []}
    result = qmd_search(q, wiki)
    local = local_search(q, wiki)
    return {"query": q, "wiki": wiki, "results": result.get("results", []), "local": local.get("results", [])}


@router.get("/status")
def api_status(user: dict = Depends(get_api_user)):
    return {
        "authenticated_user": user.get("username"),
        "wikis": [w["name"] for w in list_wikis()],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# A. Security & User Management (nur Admin)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/users")
def api_list_users(admin: dict = Depends(require_api_admin)):
    return {"users": [{"id": u["id"], "username": u["username"], "role": u["role"], "active": u.get("active", True)} for u in list_users()]}


@router.post("/users")
async def api_create_user(request: Request, admin: dict = Depends(require_api_admin)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiger JSON-Body")
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = body.get("role") or "editor"
    if not username or not password:
        raise HTTPException(status_code=400, detail="username und password erforderlich")
    try:
        create_user(username, password, role=role)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return JSONResponse(status_code=201, content={"ok": True, "username": username})


@router.delete("/users/{user_id}")
def api_delete_user(user_id: str, admin: dict = Depends(require_api_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Du kannst dich nicht selbst löschen")
    delete_user(user_id)
    return {"ok": True}


@router.get("/api-keys")
def api_list_keys(admin: dict = Depends(require_api_admin)):
    return {"api_keys": [{"id": k["id"], "name": k["name"], "scopes": k.get("scopes"), "require_password": k.get("require_password", False), "active": k.get("active", True)} for k in list_keys()]}


@router.post("/api-keys")
async def api_create_key(request: Request, admin: dict = Depends(require_api_admin)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiger JSON-Body")
    name = (body.get("name") or "").strip()
    require_password = bool(body.get("require_password", False))
    scopes = body.get("scopes") or ["read", "write"]
    if not name:
        raise HTTPException(status_code=400, detail="name erforderlich")
    key_obj, raw = create_key(user_id=admin["id"], name=name, require_password=require_password, scopes=scopes)
    return JSONResponse(status_code=201, content={"ok": True, "id": key_obj["id"], "name": name, "api_key": raw})


@router.delete("/api-keys/{key_id}")
def api_delete_key(key_id: str, admin: dict = Depends(require_api_admin)):
    delete_key(key_id)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# B. Ingest & Dateiverwaltung
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/wikis/{wiki}/ingest")
async def api_ingest_upload(wiki: str, request: Request, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    saved = []
    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=400, detail="Multipart-Formulardaten erforderlich")
    files = form.getlist("files") if hasattr(form, "getlist") else []
    if not files:
        # Einzelne Datei unter 'file'
        f = form.get("file")
        if f:
            files = [f]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for upload in files:
        if hasattr(upload, "filename") and upload.filename:
            dest = RAW_DIR / os.path.basename(upload.filename)
            dest.write_bytes(await upload.read())
            saved.append(upload.filename)
    if saved:
        log_action(action="api_ingest_upload", details=f"{len(saved)} Datei(en) via API nach raw/ hochgeladen: {', '.join(saved)} (Wiki: {wiki})", user_id=user.get("id"), username=user.get("username"), request=request)
    return {"ok": True, "wiki": wiki, "saved": saved}


@router.get("/wikis/{wiki}/pending")
def api_pending(wiki: str, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    return {"wiki": wiki, "pending": get_pending_files()}


@router.post("/wikis/{wiki}/ingest/process")
def api_ingest_process(wiki: str, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    pending = get_pending_files()
    processed = []
    errors = []
    backend = os.environ.get("LLM_BACKEND", "ollama")
    from core.config import load_app_config
    cfg = load_app_config()
    env = os.environ.copy()
    env["LLM_BACKEND"] = backend
    env["OLLAMA_HOST"] = cfg.get("ollama_host", "http://localhost:11434")
    env["OLLAMA_MODEL"] = cfg.get("ollama_model", "llama3.2:3b")

    for item in pending:
        filepath = RAW_DIR / item["name"]
        if not filepath.exists():
            continue
        try:
            result = subprocess.run(
                ["./wiki.sh", "ingest", str(filepath)],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(PROJECT_ROOT),
                env=env,
            )
            if result.returncode == 0:
                processed.append(item["name"])
            else:
                errors.append(f"{item['name']}: {result.stderr.strip() or 'Fehler beim Ingest'}")
        except Exception as e:
            errors.append(f"{item['name']}: {str(e)}")
    try:
        do_sync(wiki)
    except Exception:
        pass
    return {"ok": True, "wiki": wiki, "processed": processed, "errors": errors}


# ═══════════════════════════════════════════════════════════════════════════════
# C. Export & System-Management
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/wikis/{wiki}/pages/{slug}/export")
def api_export_page(wiki: str, slug: str, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    slug = re.sub(r"\.md$", "", slug)
    src = wiki_path(wiki) / f"{slug}.md"
    if not src.exists():
        raise HTTPException(status_code=404, detail="Seite nicht gefunden")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    dest = EXPORT_DIR / f"{wiki}__{slug}.md"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return {"ok": True, "wiki": wiki, "slug": slug, "exported_to": str(dest.relative_to(PROJECT_ROOT))}


@router.get("/system/status")
def api_system_status(user: dict = Depends(get_api_user)):
    wikis = list_wikis()
    stats = {w["name"]: get_wiki_stats(w["name"]) for w in wikis}
    return {
        "version": APP_VERSION,
        "authenticated_user": user.get("username"),
        "users": len(list_users()),
        "api_keys": len(list_keys()),
        "wikis": [{"name": w["name"], "stats": stats[w["name"]]} for w in wikis],
    }


@router.post("/system/sync")
def api_system_sync(user: dict = Depends(get_api_user)):
    results = {}
    for w in list_wikis():
        try:
            do_sync(w["name"])
            results[w["name"]] = "ok"
        except Exception as e:
            results[w["name"]] = f"fehler: {e}"
    return {"ok": True, "results": results}


@router.get("/system/audit")
def api_system_audit(
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    category: str | None = None,
    username: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
    admin: dict = Depends(require_api_admin),
):
    from services.audit import get_logs
    logs, total = get_logs(
        limit=limit,
        offset=offset,
        action=action,
        category=category,
        username=username,
        start_date=start_date,
        end_date=end_date,
        search=search
    )
    return {"logs": logs, "total": total, "limit": limit, "offset": offset}


# ═══════════════════════════════════════════════════════════════════════════════
# D. Direct Wiki API Endpoints (e.g. /LLMWikiNG/wiki/{wiki_name}/api/...)
# ═══════════════════════════════════════════════════════════════════════════════

from core.config import slugify_wiki

wiki_api_router = APIRouter(prefix=f"{BASE_PATH}/wiki/{{wiki_name}}/api")


@wiki_api_router.post("/ingest")
async def api_direct_ingest(
    wiki_name: str,
    request: Request,
    user: dict = Depends(get_api_user)
):
    """Direkter Ingest von Dateien, URLs oder reinem Text für ein spezifisches Wiki."""
    slug = slugify_wiki(wiki_name)
    root = wiki_path(slug)
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Wiki '{wiki_name}' nicht gefunden")
        
    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=400, detail="Formulardaten erforderlich (multipart/form-data oder urlencoded)")
        
    title = (form.get("title") or "").strip()
    url = (form.get("url") or "").strip()
    text = (form.get("text") or "").strip()
    
    files = form.getlist("files") if hasattr(form, "getlist") else []
    if not files:
        f = form.get("file")
        if f:
            files = [f]

    # Temporäres Ingest-Verzeichnis
    temp_dir = PROJECT_ROOT / "backend" / "scratch"
    temp_dir.mkdir(exist_ok=True)
    
    backend = os.environ.get("LLM_BACKEND", "ollama")
    from core.config import load_app_config
    cfg = load_app_config()
    env = os.environ.copy()
    env["LLM_BACKEND"] = backend
    env["OLLAMA_HOST"] = cfg.get("ollama_host", "http://localhost:11434")
    env["OLLAMA_MODEL"] = cfg.get("ollama_model", "llama3.2:3b")
    env["WIKI_DIR"] = str(root)
    env["RAW_DIR"] = str(RAW_DIR)
    env["COLLECTION_NAME"] = f"wiki_{slug}"

    processed = []
    errors = []
    new_slugs = []

    # Fall 1: URL-Ingest (Herunterladen und in Markdown umwandeln)
    if url:
        try:
            import urllib.request
            # Einfacher Download
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='replace')
            # Zu Markdown konvertieren (sehr einfach oder roher Text)
            import html2text # Falls vorhanden, sonst Fallback
            try:
                h = html2text.HTML2Text()
                h.ignore_links = False
                md_content = h.handle(html)
            except ImportError:
                md_content = f"# {title or url}\n\nDownloaded from {url}\n\n{html[:5000]}"
                
            temp_filepath = temp_dir / "downloaded_url.md"
            temp_filepath.write_text(md_content, encoding="utf-8")
            
            cmd = ["./wiki.sh", "ingest", str(temp_filepath)]
            if title:
                cmd += ["--title", title]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(PROJECT_ROOT), env=env)
            if result.returncode == 0:
                processed.append(url)
                # Slug ermitteln
                ns = slugify_german(title or "downloaded-url")
                new_slugs.append(ns)
            else:
                errors.append(f"{url}: {result.stderr.strip()}")
            if temp_filepath.exists():
                temp_filepath.unlink()
        except Exception as e:
            errors.append(f"{url}: {str(e)}")

    # Fall 2: Reiner Text-Ingest
    elif text:
        try:
            safe_title = title or "Paste"
            temp_filepath = temp_dir / "paste_text.md"
            if not text.startswith("#"):
                text = f"# {safe_title}\n\n{text}"
            temp_filepath.write_text(text, encoding="utf-8")
            
            cmd = ["./wiki.sh", "ingest", str(temp_filepath)]
            if title:
                cmd += ["--title", title]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(PROJECT_ROOT), env=env)
            if result.returncode == 0:
                processed.append(safe_title)
                new_slugs.append(slugify_german(safe_title))
            else:
                errors.append(f"{safe_title}: {result.stderr.strip()}")
            if temp_filepath.exists():
                temp_filepath.unlink()
        except Exception as e:
            errors.append(f"Text Ingest: {str(e)}")

    # Fall 3: Datei-Uploads
    elif files:
        for upload in files:
            if hasattr(upload, "filename") and upload.filename:
                temp_filepath = temp_dir / os.path.basename(upload.filename)
                temp_filepath.write_bytes(await upload.read())
                
                try:
                    cmd = ["./wiki.sh", "ingest", str(temp_filepath)]
                    if title:
                        cmd += ["--title", title]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(PROJECT_ROOT), env=env)
                    if result.returncode == 0:
                        processed.append(upload.filename)
                        new_slugs.append(slugify_german(title or Path(upload.filename).stem))
                    else:
                        errors.append(f"{upload.filename}: {result.stderr.strip() or 'Fehler beim Ingest'}")
                except Exception as e:
                    errors.append(f"{upload.filename}: {str(e)}")
                finally:
                    if temp_filepath.exists():
                        temp_filepath.unlink()
                        
    if processed:
        try:
            do_sync(slug)
        except Exception:
            pass
            
    # URLs zum direkten Anschauen im Wiki zurückgeben
    view_urls = [f"{BASE_PATH}/wiki/{slug}/{s}" for s in new_slugs]
    return {"ok": True, "wiki": slug, "processed": processed, "view_urls": view_urls, "errors": errors}


@wiki_api_router.post("/sync")
def api_direct_sync(wiki_name: str, user: dict = Depends(get_api_user)):
    """Direktes Syncen (Embedding-Updates) für ein spezifisches Wiki."""
    slug = slugify_wiki(wiki_name)
    _wiki_or_404(slug)
    try:
        do_sync(slug)
        return {"ok": True, "wiki": slug}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

