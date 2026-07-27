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
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse

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
                from starlette.responses import JSONResponse as StarletteJSON

                class McpApiKeyMiddleware:
                    """Middleware fuer MCP-Endpunkte: Prueft API-Key + MCP-Key.

                    Unterstuetzt zwei Modi:
                    1. Legacy: X-MCP-Key == globale LLMWIKING_MCP_KEY + X-API-Key
                    2. Neu: X-MCP-Key passt zu MCP-Key in mcp_keys.json + X-API-Key desselben Users
                    """
                    def __init__(self, app):
                        self.app = app
                        # Imports auf Modulebene (nur einmalig beim Start)
                        import hashlib as _hl
                        from urllib.parse import parse_qs as _pqs
                        from core.config import LLMWIKING_MCP_KEY as _mcp_global_key
                        from core.storage import get_key_by_hash as _gkbh
                        from core.storage import get_user as _gu
                        from core.storage import get_mcp_key_by_hash as _gmkbh
                        from core.storage import update_mcp_key as _umk
                        from api.routes.mcp import mcp_allowed_tools_ctx as _mac
                        from datetime import datetime as _dt
                        self._hashlib = _hl
                        self._parse_qs = _pqs
                        self._mcp_global_key = _mcp_global_key
                        self._get_key_by_hash = _gkbh
                        self._get_user = _gu
                        self._get_mcp_key_by_hash = _gmkbh
                        self._update_mcp_key = _umk
                        self._mcp_allowed_tools_ctx = _mac
                        self._datetime = _dt

                    async def __call__(self, scope, receive, send):
                        if scope["type"] == "http" and "/mcp/" in scope.get("path", ""):
                            headers_dict = dict(scope.get("headers", []))

                            # MCP-Key aus Header oder Query lesen
                            mcp_key_bytes = headers_dict.get(b"x-mcp-key")
                            mcp_key = mcp_key_bytes.decode("utf-8", errors="ignore") if mcp_key_bytes else None
                            if not mcp_key:
                                query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")
                                query_params = self._parse_qs(query_string)
                                mcp_key = query_params.get("mcp_key", [None])[0]

                            if not mcp_key:
                                res = JSONResponse({"detail": "MCP-Key erforderlich (X-MCP-Key)"}, status_code=401)
                                await res(scope, receive, send)
                                return

                            # API-Key aus Header oder Query lesen
                            api_key_bytes = headers_dict.get(b"x-api-key")
                            api_key = api_key_bytes.decode("utf-8", errors="ignore") if api_key_bytes else None
                            if not api_key:
                                query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")
                                query_params = self._parse_qs(query_string)
                                api_key = query_params.get("api_key", [None])[0]

                            if not api_key:
                                res = JSONResponse({"detail": "API-Key erforderlich (X-API-Key)"}, status_code=401)
                                await res(scope, receive, send)
                                return

                            # Modus 1: Per-User MCP-Key aus mcp_keys.json
                            mcp_key_obj = self._get_mcp_key_by_hash(self._hashlib.sha256(mcp_key.encode()).hexdigest())

                            if mcp_key_obj:
                                # API-Key muss demselben User gehören wie der MCP-Key
                                api_h = self._hashlib.sha256(api_key.encode()).hexdigest()
                                api_key_obj = self._get_key_by_hash(api_h)
                                if not api_key_obj or not api_key_obj.get("active", True):
                                    res = JSONResponse({"detail": "Ungueltiger API-Key (X-API-Key)"}, status_code=401)
                                    await res(scope, receive, send)
                                    return

                                if api_key_obj["user_id"] != mcp_key_obj["user_id"]:
                                    res = JSONResponse({"detail": "API-Key und MCP-Key gehoeren nicht demselben Benutzer"}, status_code=403)
                                    await res(scope, receive, send)
                                    return

                                user = self._get_user(mcp_key_obj["user_id"])
                                if not user or not user.get("active", True):
                                    res = JSONResponse({"detail": "Benutzer inaktiv"}, status_code=401)
                                    await res(scope, receive, send)
                                    return

                                # allowed_tools in scopeState + ContextVar speichern
                                if "state" not in scope:
                                    scope["state"] = {}
                                scope["state"]["mcp_user"] = user
                                scope["state"]["mcp_allowed_tools"] = mcp_key_obj.get("allowed_tools", [])

                                # ContextVar fuer Tool-Berechtigung in mcp.py setzen
                                _allowed_token = self._mcp_allowed_tools_ctx.set(mcp_key_obj.get("allowed_tools", []))

                                # last_used aktualisieren (stumme Aktualisierung)
                                try:
                                    self._update_mcp_key(mcp_key_obj["id"], last_used=self._datetime.now().isoformat(timespec="seconds"))
                                except Exception:
                                    pass

                                try:
                                    await self.app(scope, receive, send)
                                finally:
                                    self._mcp_allowed_tools_ctx.reset(_allowed_token)
                                return

                            # Modus 2: Legacy-Key (Rueckwaertskompatibilitaet)
                            if self._mcp_global_key and mcp_key == self._mcp_global_key:
                                api_h = self._hashlib.sha256(api_key.encode()).hexdigest()
                                db_key = self._get_key_by_hash(api_h)
                                if not db_key or not db_key.get("active", True):
                                    res = JSONResponse({"detail": "Ungueltiger API-Key (X-API-Key)"}, status_code=401)
                                    await res(scope, receive, send)
                                    return

                                user = self._get_user(db_key["user_id"])
                                if not user or not user.get("active", True):
                                    res = JSONResponse({"detail": "Benutzer inaktiv"}, status_code=401)
                                    await res(scope, receive, send)
                                    return

                                if "state" not in scope:
                                    scope["state"] = {}
                                scope["state"]["mcp_user"] = user
                                scope["state"]["mcp_allowed_tools"] = []  # Legacy = alle Tools

                                # ContextVar: Legacy = alle Tools erlaubt
                                _allowed_token = self._mcp_allowed_tools_ctx.set([])

                                try:
                                    await self.app(scope, receive, send)
                                finally:
                                    self._mcp_allowed_tools_ctx.reset(_allowed_token)
                                return

                            # Weder gueltiger MCP-Key noch Legacy-Key
                            res = JSONResponse({"detail": "Ungueltiger MCP-Key (X-MCP-Key)"}, status_code=401)
                            await res(scope, receive, send)
                            return

                        await self.app(scope, receive, send)

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
