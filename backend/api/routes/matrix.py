# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Projekt Matrix REST-API.

Endpunkte für die persistente Volltextsuche: Suchen, Ingestion, Rebuild,
Health-Check, Prune und Bulk-Ingest. Alle Schreibzugriffe laufen über den
sequentiellen Queue-Worker des ``MatrixIndexer``.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.config import BASE_PATH, WIKIS_ROOT, load_app_config

from services.matrix_indexer import MatrixIndexer
from services.matrix_searcher import MatrixSearcher

from api.deps import get_api_user, require_api_admin

log = logging.getLogger("llmwiking.matrix.api")

router = APIRouter(prefix="/matrix", tags=["matrix"])

SYSTEM_STEMS = {"index", "log", "ingestlater"}


class IngestPayload(BaseModel):
    wiki_id: str = "main"
    doc_id: str
    title: str = ""
    content: str = ""
    tags: str = ""
    md_path: str = ""
    doc_type: str = "concept"


class SearchQuery(BaseModel):
    query: str
    wikis: list[str] = Field(default_factory=lambda: ["main"])
    limit: int = 30
    tags: list[str] = Field(default_factory=list)


def _get_indexer(request: Request) -> MatrixIndexer:
    indexer = getattr(request.app.state, "matrix_indexer", None)
    if indexer is None or not getattr(indexer, "_running", False):
        raise HTTPException(status_code=503, detail="Matrix-Index nicht aktiv")
    return indexer


def _audit(action: str, details: str, actor: dict | None, request: Request) -> None:
    """Zeichnet Matrix-Operationen im Audit-Log auf (fehlerresistent)."""
    try:
        from services.audit import log_action

        log_action(
            action=action,
            details=details,
            username=(actor or {}).get("username"),
            user_id=(actor or {}).get("id"),
            request=request,
        )
    except Exception:
        pass


async def _index_markdown_file(indexer: MatrixIndexer, wiki_id: str, md_file: Path) -> None:
    from services.tags import extract_tags, normalize_tag

    try:
        content = md_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    import re

    body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else md_file.stem.title()
    tag_list = [normalize_tag(t) for t in extract_tags(content)]
    md_path = str(md_file.relative_to(WIKIS_ROOT / wiki_id)).replace("\\", "/")
    doc_id = md_path[:-3] if md_path.endswith(".md") else md_path
    indexer.index_document(
        wiki_id=wiki_id,
        doc_id=doc_id,
        title=title,
        content=content,
        tags=",".join(tag_list),
        md_path=md_path,
    )


async def _rebuild_index_async(wiki_id: str, app_state) -> None:
    """Baut den Matrix-Index aus allen Markdown-Dateien neu auf."""
    try:
        indexer: MatrixIndexer | None = getattr(app_state, "matrix_indexer", None)
        if indexer is None:
            return
        rebuild = {
            "state": "running",
            "wiki_id": wiki_id,
            "total": 0,
            "done": 0,
            "current": "",
        }
        app_state.matrix_rebuild = rebuild

        wikis = [wiki_id] if wiki_id != "all" else _wiki_slugs()
        total = 0
        files: list[tuple[str, Path]] = []
        for slug in wikis:
            root = WIKIS_ROOT / slug
            if not root.exists():
                continue
            for f in sorted(root.rglob("*.md")):
                rel = f.relative_to(root)
                if any(p.startswith(".") for p in rel.parts):
                    continue
                if f.stem in SYSTEM_STEMS:
                    continue
                files.append((slug, f))
        rebuild["total"] = total = len(files)
        rebuild["wiki_id"] = wiki_id

        for done, (slug, f) in enumerate(files, start=1):
            rebuild["done"] = done
            rebuild["current"] = str(f)
            try:
                await _index_markdown_file(indexer, slug, f)
            except Exception as exc:
                log.warning("Rebuild: Index-Fehler für %s: %s", f, exc)
        await indexer._write_queue.join()
        rebuild["state"] = "done"
    except Exception as exc:
        log.exception("Rebuild fehlgeschlagen")
        app_state.matrix_rebuild = {
            "state": "error",
            "wiki_id": wiki_id,
            "total": 0,
            "done": 0,
            "current": str(exc),
        }


def _wiki_slugs() -> list[str]:
    from core.config import list_wikis

    return [w.get("slug") or w.get("name") for w in list_wikis()]


@router.get("/search")
async def matrix_search_get(
    request: Request,
    q: str = "",
    wikis: str = "main",
    limit: int = 30,
    user: dict = Depends(get_api_user),
) -> dict:
    if len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Suchbegriff zu kurz (min. 2 Zeichen)")
    from services.search import parse_search_tags

    cleaned, tags = parse_search_tags(q)
    searcher = MatrixSearcher()
    wiki_ids = ["all"] if wikis == "all" else [w.strip() for w in wikis.split(",") if w.strip()]
    data = await searcher.search(wiki_ids=wiki_ids, query=cleaned or q, limit=limit, tags=tags)
    _audit(
        "matrix_search",
        f"Matrix-Suche '{cleaned or q}' in '{wikis}' – {len(data.get('results', []))} Treffer",
        user,
        request,
    )
    return data


@router.post("/search")
async def matrix_search_post(
    request: Request,
    payload: SearchQuery,
    user: dict = Depends(get_api_user),
) -> dict:
    if len(payload.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Suchbegriff zu kurz (min. 2 Zeichen)")
    searcher = MatrixSearcher()
    wiki_ids = ["all"] if "all" in payload.wikis else payload.wikis
    data = await searcher.search(
        wiki_ids=wiki_ids,
        query=payload.query,
        limit=payload.limit,
        tags=payload.tags,
    )
    _audit(
        "matrix_search",
        f"Matrix-Suche '{payload.query}' in '{','.join(payload.wikis)}' – {len(data.get('results', []))} Treffer",
        user,
        request,
    )
    return data


@router.post("/ingest", status_code=202)
async def matrix_ingest(
    request: Request,
    payload: IngestPayload,
    user: dict = Depends(get_api_user),
) -> dict:
    indexer = _get_indexer(request)
    if not payload.doc_id:
        raise HTTPException(status_code=400, detail="doc_id ist erforderlich")
    accepted = indexer.index_document(
        wiki_id=payload.wiki_id,
        doc_id=payload.doc_id,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
        md_path=payload.md_path,
        doc_type=payload.doc_type,
    )
    if not accepted:
        raise HTTPException(status_code=503, detail="Matrix-Index nicht aktiv")
    _audit(
        "matrix_ingest",
        f"Matrix-Ingest '{payload.doc_id}' in Wiki '{payload.wiki_id}'",
        user,
        request,
    )
    return {"accepted": True, "doc_id": payload.doc_id, "wiki_id": payload.wiki_id}


@router.post("/ingest/bulk", status_code=202)
async def matrix_ingest_bulk(
    request: Request,
    payloads: list[IngestPayload],
    user: dict = Depends(get_api_user),
) -> dict:
    indexer = _get_indexer(request)
    if not payloads:
        raise HTTPException(status_code=400, detail="Leere Bulk-Anfrage")
    accepted = 0
    for payload in payloads:
        if not payload.doc_id:
            continue
        if indexer.index_document(
            wiki_id=payload.wiki_id,
            doc_id=payload.doc_id,
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
            md_path=payload.md_path,
            doc_type=payload.doc_type,
        ):
            accepted += 1
    _audit(
        "matrix_bulk_ingest",
        f"Matrix-Bulk-Ingest: {accepted}/{len(payloads)} Dokumente angenommen",
        user,
        request,
    )
    return {"accepted": accepted, "total": len(payloads)}


@router.delete("/document/{wiki_id}/{doc_id:path}")
async def matrix_delete_document(
    request: Request,
    wiki_id: str,
    doc_id: str,
    admin: dict = Depends(require_api_admin),
) -> dict:
    indexer = _get_indexer(request)
    indexer.remove_document(wiki_id, doc_id)
    _audit(
        "matrix_document_delete",
        f"Matrix-Dokument '{doc_id}' in Wiki '{wiki_id}' entfernt",
        admin,
        request,
    )
    return {"removed": True, "doc_id": doc_id, "wiki_id": wiki_id}


@router.get("/stats")
async def matrix_stats(
    request: Request,
    user: dict = Depends(get_api_user),
) -> dict:
    indexer = getattr(request.app.state, "matrix_indexer", None)
    indexer_stats = indexer.get_stats() if indexer is not None else {}
    searcher = MatrixSearcher()
    searcher_stats = searcher.get_stats()

    # Zähle alle indizierten Dokumente aus der Registry
    indexed_doc_count = 0
    try:
        import sqlite3
        reg_path = searcher.data_root / "registry.db"
        if reg_path.exists():
            with sqlite3.connect(str(reg_path)) as conn:
                cur = conn.execute("SELECT COUNT(*) FROM doc_registry")
                indexed_doc_count = cur.fetchone()[0]
    except Exception:
        pass

    indexer_stats["indexed"] = indexed_doc_count

    cfg = load_app_config()
    matrix_cfg = cfg.get("matrix", {})
    matrix_cfg["enable_matrix"] = cfg.get("enable_matrix", True)

    combined = {**indexer_stats, **searcher_stats}
    combined["indexer"] = indexer_stats
    combined["searcher"] = searcher_stats
    combined["enabled"] = indexer is not None
    combined["healthy"] = indexer is not None and (searcher_stats.get("shard_count", 0) > 0 or indexed_doc_count >= 0)
    combined["config"] = matrix_cfg
    rebuild = getattr(request.app.state, "matrix_rebuild", None)
    if rebuild:
        combined["rebuild"] = rebuild
    else:
        combined["rebuild"] = {"state": "idle", "wiki_id": "", "total": 0, "done": 0, "current": ""}
    return combined




@router.get("/health")
async def matrix_health(
    request: Request,
    user: dict = Depends(get_api_user),
) -> dict:
    indexer = getattr(request.app.state, "matrix_indexer", None)
    healthy = False
    registry_rows = 0
    shard_readable = False
    try:
        if indexer is not None:
            registry_path = indexer._registry_path
            if registry_path.exists():
                conn = sqlite3.connect(str(registry_path), timeout=5)
                try:
                    registry_rows = conn.execute(
                        "SELECT COUNT(*) FROM doc_registry"
                    ).fetchone()[0]
                finally:
                    conn.close()
                shards = list(indexer.data_root.glob("*_shard_*.db"))
                if shards:
                    probe = shards[0]
                    conn = sqlite3.connect(str(probe), timeout=5)
                    try:
                        conn.execute("SELECT COUNT(*) FROM docs").fetchone()
                        shard_readable = True
                    finally:
                        conn.close()
                healthy = registry_rows >= 0 and (not shards or shard_readable)
    except Exception as exc:
        log.warning("Matrix-Health-Check Fehler: %s", exc)
    return {
        "status": "ok" if healthy else "degraded",
        "healthy": healthy,
        "registry_exists": indexer is not None and indexer._registry_path.exists(),
        "registry_rows": registry_rows,
        "shard_readable": shard_readable,
    }


@router.post("/rebuild", status_code=202)
async def matrix_rebuild(
    request: Request,
    background_tasks: BackgroundTasks,
    wiki_id: str = "all",
    admin: dict = Depends(require_api_admin),
) -> dict:
    indexer = getattr(request.app.state, "matrix_indexer", None)
    if indexer is None:
        raise HTTPException(status_code=503, detail="Matrix-Index nicht aktiv")
    background_tasks.add_task(_rebuild_index_async, wiki_id, request.app.state)
    _audit(
        "matrix_rebuild",
        f"Matrix-Index-Rebuild für Wiki '{wiki_id}' gestartet",
        admin,
        request,
    )
    return {"started": True, "wiki_id": wiki_id}


@router.post("/prune")
async def matrix_prune(
    request: Request,
    admin: dict = Depends(require_api_admin),
) -> dict:
    indexer = getattr(request.app.state, "matrix_indexer", None)
    if indexer is None:
        raise HTTPException(status_code=503, detail="Matrix-Index nicht aktiv")
    removed = 0
    registry_path = indexer._registry_path
    if not registry_path.exists():
        return {"removed": 0, "reason": "registry fehlt"}
    try:
        conn = sqlite3.connect(str(registry_path), timeout=10)
        try:
            rows = conn.execute(
                "SELECT doc_id, wiki_id, md_path FROM doc_registry"
            ).fetchall()
            for doc_id, wiki_id, md_path in rows:
                target = WIKIS_ROOT / wiki_id / md_path
                if not target.exists():
                    conn.execute("DELETE FROM doc_registry WHERE doc_id = ?", (doc_id,))
                    indexer.remove_document(wiki_id, doc_id)
                    removed += 1
            conn.commit()
        finally:
            conn.close()
        if removed:
            await indexer._write_queue.join()
    except Exception as exc:
        log.warning("Prune Fehler: %s", exc)
    _audit(
        "matrix_prune",
        f"Matrix-Prune: {removed} verwaiste Einträge entfernt",
        admin,
        request,
    )
    return {"removed": removed}
