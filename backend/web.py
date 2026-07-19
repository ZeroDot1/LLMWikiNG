"""LLMWikiNG – Gemeinsame Web-Helfer (Templates, Redirect, Context).

Stellt die Jinja2Templates-Instanz, Hilfsfunktionen für Redirects/Aborts und
den globalen Template-Context bereit, der jedem Render-Call mitgegeben wird
(Äquivalent zum Flask @app.context_processor).
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from core.config import (
    PROJECT_ROOT,
    APP_NAME,
    APP_EDITION,
    APP_VERSION,
    BASE_PATH,
    load_app_config,
    get_available_languages,
    resolve_lang,
    Translator,
    list_wikis,
)
from services.wiki import get_all_wiki_pages
from services.sync import is_sync_needed
from api.deps import get_current_user


templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))


def abort(status_code: int, detail: str = "") -> None:
    """Äquivalent zu Flask abort()."""
    raise HTTPException(status_code=status_code, detail=str(detail))


def redirect(url: str, status_code: int = 302) -> RedirectResponse:
    """Äquivalent zu Flask redirect()."""
    return RedirectResponse(url, status_code=status_code)


def urlencode(value: str) -> str:
    return quote(value)


def base_context(request: Request, wiki: str = "main") -> dict:
    """Globaler Template-Context (Sprache, App-Infos, Wiki-Liste, Sync-Status)."""
    from core.config import wiki_path

    lang = resolve_lang(
        request.query_params.get("lang"),
        request.cookies.get("llmwiki_lang"),
    )
    _t = Translator(lang)
    current_user = get_current_user(request)
    return {
        "request": request,
        "all_pages": get_all_wiki_pages(wiki),
        "wikis": list_wikis(),
        "current_wiki": wiki,
        "wiki_exists": wiki_path(wiki).exists(),
        "now": datetime.now(),
        "app_name": APP_NAME,
        "app_edition": APP_EDITION,
        "app_version": APP_VERSION,
        "base_path": BASE_PATH,
        "theme": load_app_config().get("theme", "dark"),
        "syntax_highlighting": load_app_config().get("syntax_highlighting", True),
        "sync_needed": is_sync_needed(wiki),
        "current_user": current_user,
        "_": _t,
        "current_lang": lang,
        "available_languages": get_available_languages(),
    }


def render(request: Request, template: str, status_code: int = 200, wiki: str = "main", **ctx: object) -> object:
    context = base_context(request, wiki=wiki)
    context.update(ctx)
    return templates.TemplateResponse(request, template, context, status_code=status_code)
