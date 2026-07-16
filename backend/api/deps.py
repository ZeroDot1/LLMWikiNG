"""LLMWikiNG – FastAPI-Dependencies für Authentifizierung.

- get_current_user / require_login: signierte Session-Cookies (Browser-UI)
- get_api_user: API-Key via Header/Query (optional mit Passwort)
"""

from __future__ import annotations

import hashlib

from fastapi import HTTPException, Request, BackgroundTasks

from core.config import wiki_path, slugify_wiki, BASE_PATH
from core.security import read_session, verify_password
from core.storage import get_user, get_key_by_hash, list_users

def update_key_last_used(key_id: str):
    from core.storage import list_keys, save_keys
    import datetime
    keys = list_keys()
    for k in keys:
        if k["id"] == key_id:
            k["last_used"] = datetime.datetime.now().isoformat(timespec="seconds")
            save_keys(keys)
            break

def get_current_user(request: Request) -> dict | None:
    uid = read_session(request.cookies.get("session"))
    if not uid:
        return None
    return get_user(uid)


def require_login(request: Request) -> dict:
    user = get_current_user(request)
    # Erstinrichtung: Gibt es noch keine User, zum Login (Setup) durchlassen
    if not user or not user.get("active", True):
        target = f"{BASE_PATH}/register" if len(list_users()) == 0 else f"{BASE_PATH}/login"
        raise HTTPException(status_code=307, headers={"Location": target})
    return user


def require_admin(request: Request) -> dict:
    user = require_login(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administratorrechte erforderlich")
    return user


def require_api_admin(request: Request, background_tasks: BackgroundTasks) -> dict:
    """API-Variante: Benutzer muss über gültigen API-Key mit Admin-Rolle kommen."""
    user = get_api_user(request, background_tasks)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administratorrechte erforderlich")
    return user


def get_api_user(request: Request, background_tasks: BackgroundTasks) -> dict:
    raw = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not raw:
        raise HTTPException(status_code=401, detail="API-Key erforderlich")
    h = hashlib.sha256(raw.encode()).hexdigest()
    key = get_key_by_hash(h)
    if not key:
        raise HTTPException(status_code=403, detail="Ungültiger API-Key")
    user = get_user(key["user_id"])
    if not user or not user.get("active", True):
        raise HTTPException(status_code=403, detail="Benutzer inaktiv")
    # Optionale Passwort-Pflicht pro Key (Anforderung 4)
    if key.get("require_password"):
        pw = request.headers.get("X-API-Password") or request.query_params.get("api_password")
        if not (pw and verify_password(pw, user["password_hash"])):
            raise HTTPException(status_code=401, detail="API-Passwort erforderlich")
    
    # Asynchrones Update im Hintergrund
    background_tasks.add_task(update_key_last_used, key["id"])
    return user


def require_wiki(wiki_name: str) -> str:
    """Normalisiert den Wiki-Namen und prüft Existenz."""
    slug = slugify_wiki(wiki_name)
    if not (wiki_path(slug)).exists():
        raise HTTPException(status_code=404, detail=f"Wiki '{wiki_name}' nicht gefunden")
    return slug
