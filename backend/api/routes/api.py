"""LLMWikiNG – Öffentliche JSON-API (geschützt durch API-Keys).

Alle Endpunkte erfordern einen gültigen API-Key (Header `X-API-Key` oder Query
`api_key`). Schlüssel mit `require_password` benötigen zusätzlich `X-API-Password`
bzw. `api_password` (Anforderung 4).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import re
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from core.config import BASE_PATH, wiki_path, list_wikis, RAW_DIR, EXPORT_DIR, PROJECT_ROOT, APP_VERSION, Path, DATA_DIR, WIKIS_ROOT, save_wiki_meta, slugify_wiki, delete_wiki, SCRATCH_DIR
from api.deps import get_api_user, require_api_admin
from core.storage import (
    list_users,
    create_user,
    delete_user,
    list_keys,
    create_key,
    delete_key,
    list_mcp_keys,
    create_mcp_key,
    update_mcp_key,
    delete_mcp_key,
)
from services.wiki import get_all_wiki_pages, get_wiki_stats, read_wiki_file, get_pending_files, slugify_german, run_ingest_async, run_sync_async
from services.search import local_search, qmd_search, run_qmd_search_async
from services.graph import build_graph_data, build_graph_data_paginated
from services.lint import run_lint
from services.tags import list_all_tags, get_tag_cloud, get_pages_by_tag, get_all_tags_aggregated
from services.editor import ensure_okf_frontmatter
from services.sync import append_okf_log, request_sync_background
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


@router.post("/wikis")
async def api_create_wiki(request: Request, admin: dict = Depends(require_api_admin)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiger JSON-Body")
    name = (body.get("name") or "").strip()
    slug = (body.get("slug") or "").strip()
    description = (body.get("description") or "").strip()
    if not name or not slug:
        raise HTTPException(status_code=400, detail="name und slug erforderlich")
    slug = slugify_wiki(slug)
    
    d = WIKIS_ROOT / slug
    if d.exists():
        raise HTTPException(status_code=409, detail="Wiki existiert bereits")
    d.mkdir(parents=True)
    save_wiki_meta(slug, name, description)
    return {"ok": True, "slug": slug}


@router.delete("/wikis/{wiki}")
def api_delete_wiki(wiki: str, admin: dict = Depends(require_api_admin)):
    if wiki == "main":
        raise HTTPException(status_code=400, detail="Standard-Wiki kann nicht gelöscht werden")
    d = WIKIS_ROOT / wiki
    if not d.exists():
        raise HTTPException(status_code=404, detail="Wiki nicht gefunden")
    delete_wiki(wiki)
    return {"ok": True}


@router.put("/wikis/{wiki}")
async def api_update_wiki(wiki: str, request: Request, admin: dict = Depends(require_api_admin)):
    """Bearbeitet die Metadaten eines bestehenden Wikis (Name, Beschreibung, Slug)."""
    d = WIKIS_ROOT / wiki
    if not d.exists():
        raise HTTPException(status_code=404, detail="Wiki nicht gefunden")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiger JSON-Body")
    name = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip()
    new_slug = (body.get("slug") or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Name ist erforderlich")

    if new_slug and new_slug != wiki:
        new_slug = slugify_wiki(new_slug)
        if new_slug == wiki:
            pass
        else:
            new_d = WIKIS_ROOT / new_slug
            if new_d.exists():
                raise HTTPException(status_code=409, detail="Ein Wiki mit diesem Slug existiert bereits")
            d.rename(new_d)
            wikis_file = DATA_DIR / "wikis.json"
            if wikis_file.exists():
                try:
                    wikis_data = json.loads(wikis_file.read_text(encoding="utf-8"))
                    wikis_data = [w for w in wikis_data if w.get("slug") != wiki]
                    wikis_data.append({
                        "slug": new_slug,
                        "name": name,
                        "description": description,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    wikis_file.write_text(json.dumps(wikis_data, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass
            meta = new_d / "wiki.json"
            try:
                meta.write_text(
                    json.dumps({"name": name, "description": description}, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass
            return {"ok": True, "slug": new_slug}

    save_wiki_meta(wiki, name, description)
    return {"ok": True, "slug": wiki}


@router.get("/wikis/{wiki}/pages")
def api_list_pages(wiki: str, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    return {"wiki": wiki, "pages": get_all_wiki_pages(wiki)}


@router.get("/wikis/{wiki}/page/{slug}")
@router.get("/wikis/{wiki}/pages/{slug}")
def api_get_page(wiki: str, slug: str, user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    slug = re.sub(r"\.md$", "", slug)
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
    tags = body.get("tags")
    if not slug:
        raise HTTPException(status_code=400, detail="slug erforderlich")
    slug = re.sub(r"\.md$", "", slug)
    if slug in ("index", "log", "ingestlater"):
        raise HTTPException(status_code=400, detail="System-Seite kann nicht überschrieben werden")
    from core.paths import safe_page_path, UnsafePathError
    try:
        filepath = safe_page_path(wiki, slug)
    except UnsafePathError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if filepath.exists():
        try:
            from services.history import save_version
            old_content = filepath.read_text(encoding="utf-8", errors="replace")
            save_version(wiki, slug, old_content)
        except Exception:
            pass
    filepath.write_text(ensure_okf_frontmatter(content, title=slug, tags=tags), encoding="utf-8")
    try:
        append_okf_log("api-create", f"{slug}.md", "Über API erstellt", wiki)
        request_sync_background(wiki)
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


@router.get("/wikis/{wiki}/tags")
async def api_tags(wiki: str, tag: str = "", user: dict = Depends(get_api_user)):
    _wiki_or_404(wiki)
    import asyncio
    if tag:
        pages = await asyncio.to_thread(get_pages_by_tag, tag, wiki)
        return {"wiki": wiki, "tag": tag, "pages": pages, "count": len(pages)}
    tags = await asyncio.to_thread(list_all_tags, wiki)
    stats = await asyncio.to_thread(get_all_tags_aggregated, wiki)
    return {"wiki": wiki, "tags": tags, "stats": stats}


@router.get("/search")
async def api_search(q: str = "", wiki: str = "main", user: dict = Depends(get_api_user)):
    if not q:
        return {"query": q, "results": [], "local": []}
    result = await run_qmd_search_async(q, wiki)
    local = local_search(q, wiki)
    return {"query": q, "wiki": wiki, "results": result.get("results", []), "local": local.get("results", [])}


@router.get("/status")
def api_status(user: dict = Depends(get_api_user)):
    return {
        "authenticated_user": user.get("username"),
        "wikis": [w["name"] for w in list_wikis()],
    }


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


@router.get("/mcp-keys")
def api_list_mcp_keys(admin: dict = Depends(require_api_admin)):
    return {"mcp_keys": [
        {
            "id": k["id"],
            "name": k["name"],
            "user_id": k["user_id"],
            "allowed_tools": k.get("allowed_tools", []),
            "active": k.get("active", True),
            "created_at": k.get("created_at"),
            "last_used": k.get("last_used"),
        }
        for k in list_mcp_keys()
    ]}


@router.get("/mcp-keys/tool-groups")
def api_list_mcp_tool_groups():
    """Listet alle verfügbaren MCP-Tool-Gruppen auf."""
    from core.config import MCP_TOOL_GROUPS
    return {"tool_groups": MCP_TOOL_GROUPS}


@router.post("/mcp-keys")
async def api_create_mcp_key(request: Request, admin: dict = Depends(require_api_admin)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiger JSON-Body")
    name = (body.get("name") or "").strip()
    target_user_id = body.get("user_id") or admin["id"]
    allowed_tools = body.get("allowed_tools")
    
    if allowed_tools is None:
        tool_groups = body.get("tool_groups") or []
        if tool_groups:
            from core.config import MCP_TOOL_GROUPS
            allowed_tools = []
            for g in tool_groups:
                if g in MCP_TOOL_GROUPS:
                    allowed_tools.extend(MCP_TOOL_GROUPS[g]["tools"])
            allowed_tools = sorted(set(allowed_tools))
        else:
            allowed_tools = []

    if not name:
        raise HTTPException(status_code=400, detail="name erforderlich")
    key_obj, raw = create_mcp_key(
        user_id=target_user_id,
        name=name,
        allowed_tools=allowed_tools,
    )
    return JSONResponse(status_code=201, content={
        "ok": True, "id": key_obj["id"], "name": name, "mcp_key": raw,
        "user_id": target_user_id, "allowed_tools": allowed_tools,
    })


@router.delete("/mcp-keys/{key_id}")
def api_delete_mcp_key(key_id: str, admin: dict = Depends(require_api_admin)):
    delete_mcp_key(key_id)
    return {"ok": True}


@router.put("/mcp-keys/{key_id}")
async def api_update_mcp_key(key_id: str, request: Request, admin: dict = Depends(require_api_admin)):
    """Aktualisiert einen MCP-Key (Name, User, Allowed Tools/Tool Groups, Status)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiger JSON-Body")
    
    changes = {}
    if "name" in body:
        name = str(body["name"]).strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
        changes["name"] = name
    if "user_id" in body:
        changes["user_id"] = str(body["user_id"])
    if "active" in body:
        changes["active"] = bool(body["active"])
    
    if "allowed_tools" in body:
        changes["allowed_tools"] = body["allowed_tools"] or []
    elif "tool_groups" in body:
        tool_groups = body["tool_groups"] or []
        from core.config import MCP_TOOL_GROUPS
        allowed = []
        for g in tool_groups:
            if g in MCP_TOOL_GROUPS:
                allowed.extend(MCP_TOOL_GROUPS[g]["tools"])
        changes["allowed_tools"] = sorted(set(allowed))

    updated = update_mcp_key(key_id, **changes)
    if not updated:
        raise HTTPException(status_code=404, detail="MCP-Key nicht gefunden")
    return {"ok": True, "mcp_key": updated}



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
async def api_ingest_process(wiki: str, user: dict = Depends(get_api_user)):
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
            result = await run_ingest_async(filepath, timeout=120, env=env)
            if result.returncode == 0:
                processed.append(item["name"])
                try:
                    if filepath.exists() and filepath.is_file():
                        filepath.unlink()
                except Exception:
                    pass
            else:
                errors.append(f"{item['name']}: {result.stderr.strip() or 'Fehler beim Ingest'}")
        except Exception as e:
            errors.append(f"{item['name']}: {str(e)}")
    try:
        await run_sync_async(wiki)
    except Exception:
        pass
    return {"ok": True, "wiki": wiki, "processed": processed, "errors": errors}


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
    stats = {w["slug"]: get_wiki_stats(w["slug"]) for w in wikis}
    return {
        "version": APP_VERSION,
        "authenticated_user": user.get("username"),
        "users": len(list_users()),
        "api_keys": len(list_keys()),
        "wikis": [{"name": w["name"], "slug": w["slug"], "stats": stats[w["slug"]]} for w in wikis],
    }


@router.post("/system/sync")
async def api_system_sync(user: dict = Depends(get_api_user)):
    results = {}
    for w in list_wikis():
        try:
            await run_sync_async(w["name"], force=True)
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
    from services.audit import get_logs, get_category_stats, get_total_count
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
    return {
        "logs": logs,
        "total": total,
        "total_all": get_total_count(),
        "category_stats": get_category_stats(),
        "limit": limit,
        "offset": offset,
    }



@router.get("/system/health")
def api_system_health(user: dict = Depends(get_api_user)):
    """Gesundheitscheck des gesamten Systems.
    
    Prüft kritische Komponenten und gibt Status für jedes Wiki zurück.
    Nutzt persistente SyncStatus-Daten (Plan §6).
    """
    import shutil
    from services.cache import get_cache
    from services.sync import SyncStatus, is_sync_needed
    
    wikis_data = []
    all_ok = True
    for w in list_wikis():
        w_slug = w["slug"]
        root = wiki_path(w_slug)
        sync_status = SyncStatus.load(w_slug)
        wiki_info = {
            "name": w["name"],
            "slug": w_slug,
            "exists": root.exists(),
            "page_count": 0,
            "sync_needed": False,
            "status": "unknown",
            "sync": sync_status.to_dict() if root.exists() else None,
        }
        if root.exists():
            pages = [p for p in root.rglob("*.md") if p.stem not in ("index", "log", "ingestlater")]
            wiki_info["page_count"] = len(pages)
            try:
                wiki_info["sync_needed"] = is_sync_needed(w_slug)
            except Exception:
                wiki_info["sync_needed"] = True
            wiki_info["status"] = "ok" if not wiki_info["sync_needed"] else "sync_pending"
        wikis_data.append(wiki_info)
        if wiki_info["status"] != "ok":
            all_ok = False

    return {
        "status": "healthy" if all_ok else "degraded",
        "version": APP_VERSION,
        "wikis": wikis_data,
        "tools": {
            "qmd": shutil.which("qmd") is not None,
            "git": shutil.which("git") is not None,
        },
        "cache_entries": get_cache().stats().get("entries", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/system/backups")
async def api_list_backups(admin: dict = Depends(require_api_admin)):
    """Listet alle auf dem Server gespeicherten Backup-Dateien auf."""
    from services.backup import list_server_backups
    backups = list_server_backups()
    return {"backups": backups, "count": len(backups)}


@router.post("/system/backups")
async def api_create_backup(admin: dict = Depends(require_api_admin)):
    """Erstellt ein neues Backup auf dem Server."""
    from services.backup import create_backup_xz
    from services.audit import log_action
    b_path = create_backup_xz()
    log_action(action="api_backup_create", details=f"Backup via API erstellt: {b_path.name}", user_id=admin.get("id"), username=admin.get("username"))
    return {"ok": True, "filename": b_path.name, "path": str(b_path)}


@router.post("/system/backups/{filename}/restore")
async def api_restore_backup(filename: str, request: Request, admin: dict = Depends(require_api_admin)):
    """Stellt ein auf dem Server vorhandenes Backup wieder her."""
    from services.backup import get_backup_filepath, restore_backup_xz
    from services.audit import log_action
    from core.storage import list_users, save_users
    
    b_path = get_backup_filepath(filename)
    if not b_path:
        raise HTTPException(status_code=404, detail="Backup-Datei nicht gefunden")

    current_uid = admin.get("id")
    current_username = admin.get("username")
    current_hash = admin.get("password")
    current_role = admin.get("role", "admin")

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

        log_action(action="api_backup_restore", details=f"Backup via API wiederhergestellt: {b_path.name}", user_id=current_uid, username=current_username, request=request)
        try:
            from services.sync import request_sync_background
            request_sync_background("main")
        except Exception:
            pass
        return {"ok": True, "restored": b_path.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore fehlgeschlagen: {e}")


@router.delete("/system/backups/{filename}")
async def api_delete_backup(filename: str, request: Request, admin: dict = Depends(require_api_admin)):
    """Löscht eine Server-Backup-Datei."""
    from services.backup import delete_server_backup
    from services.audit import log_action
    ok = delete_server_backup(filename)
    if not ok:
        raise HTTPException(status_code=404, detail="Backup-Datei nicht gefunden oder konnte nicht gelöscht werden")
    log_action(action="api_backup_delete", details=f"Backup via API gelöscht: {filename}", user_id=admin.get("id"), username=admin.get("username"), request=request)
    return {"ok": True, "deleted": filename}



@router.get("/system/update/check")
async def api_update_check(admin: dict = Depends(require_api_admin)):
    """Prueft, ob ein Update auf GitHub verfuegbar ist.

    Nutzt ``git ls-remote`` (read-only) und vergleicht den lokalen Commit-Hash
    mit ``origin/main``. Nur bei Hash-Differenz wird ``git fetch`` ausgefuehrt,
    um die VERSION-Datei auszulesen.
    """
    version_file = PROJECT_ROOT / "VERSION"
    local_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unbekannt"

    try:
        # 1. Read-only Hash-Vergleich
        ls_proc = await asyncio.to_thread(
            subprocess.run,
            ["git", "ls-remote", "origin", "main"],
            capture_output=True, text=True, timeout=15,
            cwd=str(PROJECT_ROOT),
        )
        if ls_proc.returncode != 0 or not ls_proc.stdout.strip():
            err_detail = ls_proc.stderr.strip() or "Konnte Version von GitHub nicht abrufen."
            if any(term in err_detail for term in ("Authentication failed", "401", "Bad credentials", "could not read Username")):
                err_detail = "GitHub-Authentifizierung fehlgeschlagen: Der angegebene Personal Access Token ist ungültig oder abgelaufen."
            raise HTTPException(status_code=502, detail=err_detail)

        remote_hash = ls_proc.stdout.strip().split()[0]
        local_hash_proc = await asyncio.to_thread(
            subprocess.run,
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(PROJECT_ROOT),
        )
        local_hash = local_hash_proc.stdout.strip() if local_hash_proc.returncode == 0 else ""

        if remote_hash == local_hash:
            return {
                "ok": True,
                "local_version": local_version,
                "remote_version": local_version,
                "update_available": False,
                "up_to_date": True,
            }

        # 2. Hash-Differenz -> fetch noetig um VERSION zu lesen
        await asyncio.to_thread(
            subprocess.run,
            ["git", "fetch", "origin"],
            capture_output=True, text=True, timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        proc = await asyncio.to_thread(
            subprocess.run,
            ["git", "show", "origin/main:VERSION"],
            capture_output=True, text=True, timeout=15,
            cwd=str(PROJECT_ROOT),
        )
        remote_version = proc.stdout.strip() if proc.returncode == 0 else None
    except HTTPException:
        raise
    except Exception:
        remote_version = None

    if not remote_version:
        raise HTTPException(status_code=502, detail="Konnte Version von GitHub nicht abrufen.")

    return {
        "ok": True,
        "local_version": local_version,
        "remote_version": remote_version,
        "update_available": local_version != remote_version,
        "up_to_date": local_version == remote_version,
    }


@router.post("/system/update/run")
async def api_update_run(admin: dict = Depends(require_api_admin)):
    """Führt das Update via ``update.sh`` aus.

    Das Skript sichert Benutzerdaten, führt ``git reset --hard origin/main``
    aus und installiert Python-Abhängigkeiten. Der Output wird bereinigt
    (ANSI-Farbcodes entfernt) zurückgegeben.
    """
    update_script = PROJECT_ROOT / "update.sh"
    if not update_script.exists():
        raise HTTPException(status_code=404, detail="update.sh nicht gefunden.")

    version_file = PROJECT_ROOT / "VERSION"
    old_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unbekannt"

    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [str(update_script)],
            capture_output=True, text=True, timeout=300,
            cwd=str(PROJECT_ROOT),
        )
        raw_output = proc.stdout + proc.stderr
        clean_output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw_output)

        new_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unbekannt"

        log_action(
            action="system_update",
            details=f"Update von {old_version} nach {new_version} ausgeführt",
            username=admin.get("username"),
            user_id=admin.get("id"),
        )

        return {
            "ok": True,
            "old_version": old_version,
            "new_version": new_version,
            "updated": old_version != new_version,
            "output": clean_output,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Update-Skript hat 300 Sekunden überschritten.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update fehlgeschlagen: {e}")


import signal as _signal
import threading as _threading


@router.post("/system/restart")
async def api_system_restart(admin: dict = Depends(require_api_admin)):
    """Startet den Webserver neu, damit neuer Code aktiv wird.

    Beendet den aktuellen uvicorn-Worker nach kurzer Verzögerung per
    ``SIGTERM`` (im Hintergrund-Thread, damit die Response gesendet wird).
    Im Docker-Container (``restart: unless-stopped``) oder via Systemd/start.sh
    fährt der Prozess mit dem NEUEN Code neu hoch. Nützlich nach einem Update,
    wenn der laufende Prozess noch alten Code im Speicher hat.

    ACHTUNG: Der Aufruf beendet den Server kurzzeitig – die Antwort wird aber
    noch vor dem Beenden zugestellt.
    """
    def _kill():
        import time
        time.sleep(1)
        try:
            os.kill(os.getpid(), _signal.SIGTERM)
        except Exception:
            pass

    _threading.Thread(target=_kill, daemon=True).start()
    return {"ok": True, "message": "Server-Neustart eingeleitet. Bitte in 5 Sekunden neu laden."}


from core.config import slugify_wiki

wiki_api_router = APIRouter(prefix=f"{BASE_PATH}/wiki/{{wiki_name}}/api")


@wiki_api_router.post("/ingest")
async def api_direct_ingest(
    wiki_name: str,
    request: Request,
    user: dict = Depends(get_api_user),
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

    temp_dir = SCRATCH_DIR
    temp_dir.mkdir(parents=True, exist_ok=True)
    
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
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='replace')
            try:
                import html2text
                h = html2text.HTML2Text()
                h.ignore_links = False
                md_content = h.handle(html)
            except (ImportError, Exception):
                import re as _re
                _text = _re.sub(r'<[^>]+>', ' ', html)
                _text = _re.sub(r'\s+', ' ', _text).strip()
                md_content = f"# {title or url}\n\nDownloaded from {url}\n\n{_text[:5000]}"
                
            temp_filepath = temp_dir / "downloaded_url.md"
            temp_filepath.write_text(md_content, encoding="utf-8")
            
            cmd = ["./wiki.sh", "ingest", str(temp_filepath)]
            if title:
                cmd += ["--title", title]
            result = await run_ingest_async(temp_filepath, title=title or None, timeout=120, env=env)
            if result.returncode == 0:
                processed.append(url)
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
            result = await run_ingest_async(temp_filepath, title=title or None, timeout=120, env=env)
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
                    result = await run_ingest_async(temp_filepath, title=title or None, timeout=120, env=env)
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
            await run_sync_async(slug)
        except Exception:
            pass
            
    view_urls = [f"{BASE_PATH}/wiki/{slug}/{s}" for s in new_slugs]
    return {"ok": True, "wiki": slug, "processed": processed, "view_urls": view_urls, "errors": errors}


@wiki_api_router.post("/sync")
async def api_direct_sync(wiki_name: str, user: dict = Depends(get_api_user)):
    """Direktes Syncen (Embedding-Updates) für ein spezifisches Wiki."""
    slug = slugify_wiki(wiki_name)
    _wiki_or_404(slug)
    try:
        await run_sync_async(slug, force=True)
        return {"ok": True, "wiki": slug, "message": f"Sync für Wiki '{slug}' abgeschlossen."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync fehlgeschlagen: {e}")


@router.delete("/raw/{filename:path}")
def api_delete_raw(filename: str, admin: dict = Depends(require_api_admin)):
    """Loescht eine Rohquellen-Datei aus dem raw/-Verzeichnis (Admin only)."""
    filepath = (RAW_DIR / filename).resolve()
    if not str(filepath).startswith(str(RAW_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Pfad-Traversale nicht erlaubt")
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="Rohquelle nicht gefunden")
    try:
        filepath.unlink()
        return {"ok": True, "deleted": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Loeschen: {e}")


@router.post("/raw/delete")
def api_delete_raw_batch(body: dict, admin: dict = Depends(require_api_admin)):
    """Loescht mehrere Rohquellen-Dateien auf einmal (Admin only)."""
    filenames = body.get("filenames", [])
    if not filenames:
        raise HTTPException(status_code=400, detail="Keine Dateinamen angegeben")
    deleted = []
    errors = []
    for filename in filenames:
        filepath = (RAW_DIR / filename).resolve()
        if not str(filepath).startswith(str(RAW_DIR.resolve())):
            errors.append(f"{filename}: Ungueltiger Pfad")
        elif not filepath.exists() or not filepath.is_file():
            errors.append(f"{filename}: Nicht gefunden")
        else:
            try:
                filepath.unlink()
                deleted.append(filename)
            except Exception as e:
                errors.append(f"{filename}: {e}")
    return {"ok": True, "deleted": deleted, "errors": errors, "deleted_count": len(deleted), "error_count": len(errors)}


@router.get("/raw")
def api_list_raw(user: dict = Depends(get_api_user)):
    """Listet alle Rohdateien auf."""
    files = []
    if RAW_DIR.exists():
        for p in RAW_DIR.rglob("*"):
            if p.is_file() and not p.name.startswith("."):
                files.append(str(p.relative_to(RAW_DIR)))
    return {"raw_files": sorted(files), "count": len(files)}


@router.get("/export")
def api_list_export(user: dict = Depends(get_api_user)):
    """Listet alle exportierten Dateien auf."""
    files = []
    if EXPORT_DIR.exists():
        for p in EXPORT_DIR.rglob("*"):
            if p.is_file() and not p.name.startswith("."):
                files.append(str(p.relative_to(EXPORT_DIR)))
    return {"export_files": sorted(files), "count": len(files)}


@router.get("/system/users")
def api_system_users(admin: dict = Depends(require_api_admin)):
    """Gibt alle registrierten Benutzer zurück (Admin-only)."""
    return {"users": list_users()}


@router.get("/system/api-keys")
def api_system_apikeys(admin: dict = Depends(require_api_admin)):
    """Gibt alle API-Keys zurück (Admin-only)."""
    return {"api_keys": list_keys()}


# ═══════════════════════════════════════════════════════════════════
# Tailscale & Funnel Integration Endpoints (Admin only)
# ═══════════════════════════════════════════════════════════════════

@router.get("/system/tailscale")
async def api_get_tailscale_config(admin: dict = Depends(require_api_admin)):
    """Returns Tailscale configuration (without raw auth key) and current status."""
    from services.tailscale import load_config, get_status
    cfg = load_config()
    status = await get_status()
    # Strip raw/encrypted keys from public response
    safe_cfg = {
        "enabled": cfg.get("enabled", False),
        "hostname": cfg.get("hostname", "zerodot1sllmwiking"),
        "has_auth_key": bool(cfg.get("auth_key_encrypted")),
        "auth_key_hint": cfg.get("auth_key_hint"),
        "app_port": cfg.get("app_port", 8080),
        "funnel_port": cfg.get("funnel_port", 443),
        "funnel_enabled": cfg.get("funnel_enabled", False),
        "serve_enabled": cfg.get("serve_enabled", True),
        "serve_path": cfg.get("serve_path", "/"),
        "extra_args": cfg.get("extra_args", ""),
        "last_status": cfg.get("last_status", {}),
        "updated_at": cfg.get("updated_at"),
        "updated_by": cfg.get("updated_by"),
    }
    return {"config": safe_cfg, "status": status}


@router.post("/system/tailscale")
async def api_save_tailscale_config(request: Request, admin: dict = Depends(require_api_admin)):
    """Saves Tailscale configuration parameters without changing daemon state."""
    from services.tailscale import load_config, save_config, encrypt_tailscale_key
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiges JSON-Format")

    cfg = load_config()
    cfg["hostname"] = (data.get("hostname") or "zerodot1sllmwiking").strip()
    cfg["app_port"] = int(data.get("app_port") or cfg.get("app_port", 8080))
    cfg["funnel_port"] = int(data.get("funnel_port") or cfg.get("funnel_port", 443))
    cfg["funnel_enabled"] = bool(data.get("funnel_enabled", cfg.get("funnel_enabled", False)))
    cfg["serve_enabled"] = bool(data.get("serve_enabled", cfg.get("serve_enabled", True)))
    cfg["extra_args"] = (data.get("extra_args") or "").strip()
    cfg["updated_by"] = admin.get("username")

    auth_key = data.get("auth_key")
    if auth_key and auth_key.strip():
        clean_key = auth_key.strip()
        cfg["auth_key_encrypted"] = encrypt_tailscale_key(clean_key)
        hint_start = clean_key[:12] if len(clean_key) >= 12 else clean_key[:4]
        hint_end = clean_key[-4:] if len(clean_key) >= 4 else ""
        cfg["auth_key_hint"] = f"{hint_start}…{hint_end}"

    save_config(cfg)
    log_action("tailscale_save", details=f"Tailscale-Konfiguration gespeichert (Hostname: {cfg['hostname']})", user_id=admin.get("id"), username=admin.get("username"), request=request)
    return {"ok": True, "message": "Tailscale-Konfiguration gespeichert."}


@router.post("/system/tailscale/setup")
async def api_setup_tailscale(request: Request, admin: dict = Depends(require_api_admin)):
    """One-Click setup: saves parameters, connects to Tailnet and applies serve/funnel."""
    from services.tailscale import setup_all
    try:
        data = await request.json()
    except Exception:
        data = {}

    res = await setup_all(
        hostname=data.get("hostname", "zerodot1sllmwiking"),
        auth_key=data.get("auth_key"),
        app_port=data.get("app_port", 8080),
        funnel_port=data.get("funnel_port", 443),
        funnel_enabled=data.get("funnel_enabled", False),
        serve_enabled=data.get("serve_enabled", True),
        extra_args=data.get("extra_args", ""),
        actor=admin.get("username") or "admin",
    )
    log_action("tailscale_setup", details=f"Tailscale One-Click Setup ausgeführt (ok={res.get('ok')})", user_id=admin.get("id"), username=admin.get("username"), request=request)
    return res


@router.post("/system/tailscale/up")
async def api_tailscale_up(request: Request, admin: dict = Depends(require_api_admin)):
    """Executes tailscale up."""
    from services.tailscale import load_config, up
    cfg = load_config()
    res = await up(cfg)
    log_action("tailscale_up", details=f"tailscale up (ok={res.get('ok')})", user_id=admin.get("id"), username=admin.get("username"), request=request)
    return res


@router.post("/system/tailscale/down")
async def api_tailscale_down(request: Request, admin: dict = Depends(require_api_admin)):
    """Executes tailscale down."""
    from services.tailscale import down
    res = await down()
    log_action("tailscale_down", details=f"tailscale down (ok={res.get('ok')})", user_id=admin.get("id"), username=admin.get("username"), request=request)
    return res


@router.post("/system/tailscale/apply")
async def api_tailscale_apply(request: Request, admin: dict = Depends(require_api_admin)):
    """Applies serve and funnel settings."""
    from services.tailscale import load_config, apply_serve_funnel
    cfg = load_config()
    res = await apply_serve_funnel(cfg)
    log_action("tailscale_apply", details=f"tailscale serve/funnel angewendet (ok={res.get('ok')})", user_id=admin.get("id"), username=admin.get("username"), request=request)
    return res


@router.post("/system/tailscale/cert")
async def api_tailscale_cert(request: Request, admin: dict = Depends(require_api_admin)):
    """Executes tailscale cert to provision Let's Encrypt SSL/TLS certificate."""
    from services.tailscale import fetch_cert
    res = await fetch_cert()
    log_action("tailscale_cert", details=f"tailscale cert ausgeführt (ok={res.get('ok')})", user_id=admin.get("id"), username=admin.get("username"), request=request)
    return res


@router.post("/system/tailscale/reset")
async def api_tailscale_reset(request: Request, admin: dict = Depends(require_api_admin)):
    """Resets tailscale funnel and serve settings."""
    from services.tailscale import reset_funnel_serve
    res = await reset_funnel_serve()
    log_action("tailscale_reset", details="tailscale funnel & serve zurückgesetzt", user_id=admin.get("id"), username=admin.get("username"), request=request)
    return res


@router.post("/system/tailscale/restart")
async def api_tailscale_restart(request: Request, admin: dict = Depends(require_api_admin)):
    """Restarts Tailscale daemon independently from the main web server."""
    from services.tailscale import restart_tailscale
    res = await restart_tailscale()
    log_action("tailscale_restart", details=f"Tailscale Daemon neugestartet (ok={res.get('ok')})", user_id=admin.get("id"), username=admin.get("username"), request=request)
    return res


@router.get("/system/tailscale/status")
async def api_tailscale_status(admin: dict = Depends(require_api_admin)):
    """Fetches live tailscale status."""
    from services.tailscale import get_status
    return await get_status()


@router.post("/system/tailscale/reveal")
async def api_tailscale_reveal(request: Request, admin: dict = Depends(require_api_admin)):
    """Verifies admin password and decrypts stored Tailscale auth key."""
    from services.tailscale import reveal_auth_key
    try:
        data = await request.json()
        password = data.get("password")
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiges JSON-Format")

    if not password:
        raise HTTPException(status_code=400, detail="Passwort erforderlich")

    raw_key = reveal_auth_key(password, admin.get("password_hash", ""))
    if not raw_key:
        raise HTTPException(status_code=403, detail="Ungültiges Passwort oder kein Key konfiguriert")

    log_action("tailscale_reveal", details="Tailscale Auth-Key entschlüsselt und angezeigt", user_id=admin.get("id"), username=admin.get("username"), request=request)
    return {"raw_key": raw_key}

