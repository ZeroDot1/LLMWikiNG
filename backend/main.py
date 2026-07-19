"""LLMWikiNG – FastAPI-Anwendung und CLI-Entrypoint.

Vollständiger Port von llmWiki.py (Flask) auf FastAPI. Die bestehenden
Jinja-Templates werden wiederverwendet.
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import asynccontextmanager
from html import escape as h_escape
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.responses import HTMLResponse, RedirectResponse

from core.config import (
    PROJECT_ROOT,
    APP_NAME,
    APP_EDITION,
    APP_VERSION,
    BASE_PATH,
    set_default_lang,
    load_app_config,
    get_available_languages,
    migrate_legacy_wiki,
)
from web import templates, render

# Statisches Verzeichnis
STATIC_DIR = PROJECT_ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App-Lebenszyklus: beim Start alle Wiki-Indizes neu aufbauen.

    Nach einem Container-/Server-Neustart kann der auf Platte liegende
    ``index.md`` veraltet sein (z. B. weil der letzte Sync den Index nicht
    neu gebaut hat, oder weil ``is_sync_needed`` keine Änderung erkannt hat).
    Da die Web-UI den Index direkt rendert, fehlen dann ingestierte Seiten
    in der Anzeige – obwohl sie auf der Platte vorhanden sind.

    Wir regenerieren daher beim Start **alle** Wiki-Indizes aus den physisch
    vorhandenen Dateien (``regenerate_index`` nutzt die un-cached Variante),
    damit der Index nach jedem Neustart garantiert mit der Realität auf der
    Platte übereinstimmt.
    """
    try:
        from core.config import list_wikis
        from services.sync import regenerate_index

        wikis = list_wikis() or [{"slug": "main"}]
        for w in wikis:
            slug = w.get("slug") or "main"
            try:
                regenerate_index(slug)
            except Exception as e:  # ein fehlerhaftes Wiki darf den Start nicht blockieren
                print(f"[lifespan] WARN: Index-Regeneration für '{slug}' fehlgeschlagen: {e}", flush=True)
        print(f"[lifespan] Wiki-Indizes für {len(wikis)} Wiki(s) neu aufgebaut.", flush=True)
    except Exception as e:
        print(f"[lifespan] WARN: Index-Regeneration übersprungen: {e}", flush=True)

    yield


def create_app() -> FastAPI:
    app = FastAPI(title=f"{APP_NAME} {APP_EDITION}", version=APP_VERSION, lifespan=lifespan)

    # Templates immer neu laden (auch im Produktionsmodus)
    templates.env.auto_reload = True

    # Statische Dateien (unter BASE_PATH, damit portabel verschiebbar)
    if STATIC_DIR.exists():
        app.mount(f"{BASE_PATH}/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    
    # Skills-Ordner zum direkten Download bereitstellen
    SKILLS_DIR = PROJECT_ROOT / "skills"
    if SKILLS_DIR.exists():
        app.mount(f"{BASE_PATH}/skills", StaticFiles(directory=str(SKILLS_DIR)), name="skills")

    # Routen registrieren
    from api.routes.pages import router as pages_router
    from api.routes.auth import router as auth_router
    from api.routes.api import router as api_router, wiki_api_router
    from api.routes.register import router as register_router

    app.include_router(auth_router)
    app.include_router(register_router)
    app.include_router(api_router)
    app.include_router(wiki_api_router)
    app.include_router(pages_router)

    # ═════════════════════════════════════════════════════════════════════════
    # MCP-Server (Model Context Protocol) – SSE-Transport
    # ═════════════════════════════════════════════════════════════════════════
    from core.config import ENABLE_MCP_SERVER, LLMWIKING_MCP_KEY

    if ENABLE_MCP_SERVER:
        from api.routes.mcp import get_mcp_sse_app, _MCP_AVAILABLE

        if _MCP_AVAILABLE:
            mcp_sse_app = get_mcp_sse_app()
            if mcp_sse_app is not None:
                # MCP API-Key Middleware: Prueft X-API-Key Header auf allen
                # /mcp/ Routen, bevor die SSE-App den Request verarbeitet.
                from starlette.middleware.base import BaseHTTPMiddleware
                from starlette.responses import JSONResponse as StarletteJSON

                class McpApiKeyMiddleware(BaseHTTPMiddleware):
                    """Middleware fuer MCP-Endpunkte: Prueft API-Key.

                    Liest LLMWIKING_MCP_KEY zur Laufzeit aus core.config,
                    damit Monkeypatches in Tests wirksam werden.
                    """

                    async def dispatch(self, request, call_next):
                        if "/mcp/" in request.url.path:
                            from core.config import LLMWIKING_MCP_KEY as _KEY
                            # 1. MCP Key check
                            mcp_key = request.headers.get("X-MCP-Key") or request.headers.get("x-mcp-key") or request.query_params.get("mcp_key")
                            if not _KEY:
                                return StarletteJSON(
                                    {"detail": "MCP nicht konfiguriert (LLMWIKING_MCP_KEY fehlt)"},
                                    status_code=503,
                                )
                            if mcp_key != _KEY:
                                return StarletteJSON(
                                    {"detail": "Ungueltiger oder fehlender MCP-Key (X-MCP-Key)"},
                                    status_code=401,
                                )
                            
                            # 2. Database API-Key check (X-API-Key)
                            api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key") or request.query_params.get("api_key")
                            if not api_key:
                                return StarletteJSON(
                                    {"detail": "API-Key erforderlich (X-API-Key)"},
                                    status_code=401,
                                )
                            
                            import hashlib
                            from core.storage import get_key_by_hash, get_user
                            h = hashlib.sha256(api_key.encode()).hexdigest()
                            db_key = get_key_by_hash(h)
                            if not db_key or not db_key.get("active", True):
                                return StarletteJSON(
                                    {"detail": "Ungueltiger API-Key (X-API-Key)"},
                                    status_code=401,
                                )
                            user = get_user(db_key["user_id"])
                            if not user or not user.get("active", True):
                                return StarletteJSON(
                                    {"detail": "Benutzer inaktiv"},
                                    status_code=401,
                                )
                            request.state.mcp_user = user
                        return await call_next(request)

                app.add_middleware(McpApiKeyMiddleware)
                app.mount(f"{BASE_PATH}/mcp", mcp_sse_app, name="mcp")
        else:
            # MCP-Paket nicht installiert – stille Deaktivierung
            pass

    # Komfort: Root auf BASE_PATH umleiten (App liegt unter /LLMWikiNG)
    @app.get("/")
    async def _root_redirect():
        return RedirectResponse(url=f"{BASE_PATH}/")

    @app.get("/favicon.ico")
    async def _favicon():
        from starlette.responses import Response

        return Response(status_code=204)

    # Bestehendes wiki/ → wikis/main/ migrieren (einmalig)
    try:
        migrate_legacy_wiki()
    except Exception:
        pass

    # Alle Konfigurationsstandards dauerhaft in config.json sicherstellen,
    # damit jeder Schlüssel (inkl. audit_enabled, audit_disabled_categories)
    # sofort auf Disk vorhanden ist und nicht nur als In-Memory-Default existiert.
    try:
        from core.config import save_app_config
        save_app_config({})   # leeres Dict → load_app_config() füllt alle Defaults ein
    except Exception:
        pass

    # ═════════════════════════════════════════════════════════════════════════
    # Fehlerseiten
    # ═════════════════════════════════════════════════════════════════════════

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # Redirect-Statuscodes (301/302/303/307/308) mit Location-Header ausführen
        if exc.status_code in (301, 302, 303, 307, 308) and exc.headers:
            location = exc.headers.get("location") or exc.headers.get("Location")
            if location:
                return RedirectResponse(url=location, status_code=exc.status_code)

        # JSON response for api routes
        if request.url.path.startswith(f"{BASE_PATH}/api/v1"):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        if exc.status_code == 404:
            return render(
                request,
                "page.html",
                status_code=exc.status_code,
                active_page="404",
                page_title="Seite nicht gefunden",
                content=(
                    f"<h1>404 – Seite nicht gefunden</h1>"
                    f"<p>{h_escape(str(exc.detail))}</p>"
                    f'<p><a href="{BASE_PATH}/">Zur Startseite</a></p>'
                ),
            )
        return HTMLResponse(
            f"<h1>{exc.status_code}</h1><p>{h_escape(str(exc.detail))}</p>",
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def server_error_handler(request: Request, exc: Exception):
        import traceback
        from pathlib import Path
        tb = traceback.format_exc()
        print(f"Exception caught in server_error_handler:\n{tb}", flush=True)
        try:
            log_file = Path(__file__).resolve().parent.parent / "data" / "error.log"
            with open(log_file, "a", encoding="utf-8") as f:
                import datetime
                f.write(f"=== {datetime.datetime.now()} ===\n{tb}\n")
        except Exception as log_ex:
            print(f"Failed to write to error.log: {log_ex}", flush=True)

        if request.url.path.startswith(f"{BASE_PATH}/api/v1"):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=500, content={"detail": "Interner Server-Fehler"})

        from core.config import resolve_lang, Translator
        lang = resolve_lang(
            request.query_params.get("lang"),
            request.cookies.get("llmwiki_lang"),
        )
        _t = Translator(lang)
        title = _t("500_title") or "Server-Fehler"
        heading = _t("500_heading") or "500 – Interner Server-Fehler"
        detail = _t("500_detail") or "Bitte Logs prüfen."

        return render(
            request,
            "page.html",
            status_code=500,
            active_page="500",
            page_title=title,
            content=f"<h1>{heading}</h1><p>{detail}</p><pre style='font-size:10px; text-align:left; background:#222; color:#fff; p:10px; overflow:auto;'>{tb}</pre>",
        )

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} {APP_EDITION} – Lokaler Wiki-Webserver (FastAPI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  python3 run.py                  # Port 8080, Sprache aus config.json\n"
            "  python3 run.py --port 9090      # Anderer Port\n"
            "  python3 run.py -p 9090 -d        # Debug + Port 9090\n"
            "  python3 run.py --lang en         # Englisch als Startsprache\n"
            "  python3 run.py --lang de -H 127.0.0.1\n"
        ),
    )
    parser.add_argument("--port", "-p", type=int, default=8080, help="Port (Standard: 8080)")
    parser.add_argument("--host", "-H", default="0.0.0.0", help="Host (Standard: 0.0.0.0)")
    parser.add_argument("--debug", "-d", action="store_true", help="Debug-Modus (Auto-Reload)")
    parser.add_argument("--lang", "-l", default=None, help="Startsprache (z. B. de, en) – überschreibt config.json")
    parser.add_argument(
        "--forwarded-allow-ips",
        default="*",
        help="IPs/Netze, denen Proxy-Header (X-Forwarded-*) vertraut wird "
             "(Standard: '*' = alle, z. B. für LAN/Reverse-Proxy). "
             "Setze auf die Proxy-IP für mehr Sicherheit.",
    )
    args = parser.parse_args()

    # Sprache ermitteln: CLI-Argument überschreibt config.json
    cfg = load_app_config()
    if args.lang:
        lang = args.lang
    else:
        lang = cfg.get("language") or "de"
    available = get_available_languages()
    if lang not in available:
        print(f"  ⚠ Sprache '{lang}' nicht in lang/ gefunden, Fallback auf Deutsch.")
        lang = "de"
    set_default_lang(lang)

    print(f"\n{'='*60}")
    print(f"  {APP_NAME}")
    print(f"  {APP_EDITION}")
    print(f"  Version {APP_VERSION}")
    print(f"{'='*60}")
    print(f"  Wiki-Verzeichnis:  {PROJECT_ROOT / 'wiki'}")
    print(f"  Rohquellen:        {PROJECT_ROOT / 'raw'}")
    print(f"  Startsprache:      {lang} ({available.get(lang, lang)})")
    print(f"  Betriebsmodus:     {'Entwicklung (Auto-Reload)' if args.debug else 'Produktion (uvicorn)'}")
    print(f"  Server startet     http://{args.host}:{args.port}")
    print(f"  Drücke Strg+C zum Beenden")
    print(f"{'='*60}\n")

    import uvicorn

    # Stellt sicher, dass der (Reloader-)Subprozess das backend/-Paket findet
    backend_dir = str(PROJECT_ROOT / "backend")
    existing = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = backend_dir + (f"{os.pathsep}{existing}" if existing else "")

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        log_level="debug" if args.debug else "info",
        reload=args.debug,
        # Proxy-Header (X-Forwarded-For/Host/Proto) verarbeiten, damit der
        # Server korrekt hinter einem Reverse-Proxy (nginx, Traefik, Synology)
        # läuft. forwarded_allow_ips="*" akzeptiert LAN-/Docker-Hosts und
        # verhindert den harten 421-"Invalid Host header"-Fehler bei Zugriff
        # über die LAN-IP (z. B. 192.168.x.x) – wichtig für MCP-SSE-Clients.
        proxy_headers=True,
        forwarded_allow_ips=args.forwarded_allow_ips,
    )


if __name__ == "__main__":
    main()
