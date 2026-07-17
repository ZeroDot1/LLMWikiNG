"""LLMWikiNG – Authentifizierungs-Routen (Login, Logout, User- & API-Key-Verwaltung)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

import json
import os

from core.config import BASE_PATH, CONFIG_FILE, load_app_config, APP_VERSION, PROJECT_ROOT
from web import render, redirect, urlencode
from api.deps import require_login, require_admin
from core.security import verify_password, create_session
from core.storage import (
    list_users,
    create_user,
    get_user,
    get_user_by_name,
    delete_user,
    list_keys,
    create_key,
    delete_key,
)

router = APIRouter(prefix=BASE_PATH)


# ═══════════════════════════════════════════════════════════════════════════════
# Login / Logout
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/login")
def login_form(request: Request):
    if len(list_users()) == 0:
        return redirect(f"{BASE_PATH}/register")
    return render(
        request, "login.html",
        active_page="login",
        setup=False,
        error=request.query_params.get("error"),
        hide_nav=True,
    )


@router.post("/login")
async def login_post(request: Request):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    users = list_users()

    # Erstinrichtung: ersten Admin anlegen
    if not users:
        if not username or not password:
            return redirect(f"{BASE_PATH}/login?error=Benutzername+und+Passwort+erforderlich")
        create_user(username, password, role="admin")
        user = get_user_by_name(username)
        return _set_session_and_redirect(user)

    user = get_user_by_name(username)
    if not user or not user.get("active", True) or not verify_password(password, user["password_hash"]):
        return redirect(f"{BASE_PATH}/login?error=Login+fehlgeschlagen")

    return _set_session_and_redirect(user)


def _set_session_and_redirect(user: dict) -> RedirectResponse:
    from fastapi.responses import RedirectResponse

    resp = RedirectResponse(f"{BASE_PATH}/", status_code=303)
    resp.set_cookie(
        "session", create_session(user["id"]),
        httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7,
    )
    return resp


@router.get("/logout")
def logout(request: Request):
    from fastapi.responses import RedirectResponse

    resp = RedirectResponse(f"{BASE_PATH}/login", status_code=303)
    resp.delete_cookie("session")
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# User-Verwaltung (nur Admin)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/users")
def users_list(request: Request, admin: dict = Depends(require_admin)):
    return render(request, "users.html", active_page="users", users=list_users())


@router.post("/users")
async def user_create(request: Request, admin: dict = Depends(require_admin)):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    role = form.get("role") or "editor"
    if not username or not password:
        return redirect(f"{BASE_PATH}/settings?tab=users&error=Benutzername+und+Passwort+erforderlich")
    try:
        create_user(username, password, role=role)
    except ValueError as e:
        return redirect(f"{BASE_PATH}/settings?tab=users&error={urlencode(str(e))}")
    return redirect(f"{BASE_PATH}/settings?tab=users&success=Benutzer+angelegt")


@router.get("/users/{user_id}/delete")
async def user_delete(user_id: str, request: Request, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        return redirect(f"{BASE_PATH}/settings?tab=users&error=Du+kannst+dich+nicht+selbst+löschen")
    delete_user(user_id)
    return redirect(f"{BASE_PATH}/settings?tab=users&success=Benutzer+gelöscht")


# ═══════════════════════════════════════════════════════════════════════════════
# API-Key-Verwaltung (nur Admin)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/api-keys")
def api_keys_list(request: Request, admin: dict = Depends(require_admin)):
    return render(
        request, "api_keys.html",
        active_page="apikeys",
        keys=list_keys(),
        new_key=None,
        error=request.query_params.get("error"),
        success=request.query_params.get("success"),
    )


@router.post("/api-keys")
async def api_key_create(request: Request, admin: dict = Depends(require_admin)):
    from services.email_sender import load_smtp_config
    from services.lint import run_lint

    form = await request.form()
    name = (form.get("name") or "").strip()
    target_user_id = form.get("user_id") or admin["id"]
    require_password = form.get("require_password") == "on"
    scopes = form.getlist("scopes")
    if not name:
        return redirect(f"{BASE_PATH}/settings?tab=apikeys&error=Name+erforderlich")
    key_obj, raw = create_key(
        user_id=target_user_id,
        name=name,
        require_password=require_password,
        scopes=scopes,
    )
    smtp_config = load_smtp_config()
    health = {"orphans": [], "missing": [], "stale": [], "missing_raw": [], "issue_count": 0}
    return render(
        request, "settings.html",
        active_page="settings",
        smtp_config=smtp_config,
        env_user=os.environ.get("GMAIL_USER", ""),
        env_pass_exists=bool(os.environ.get("GMAIL_APP_PASSWORD")),
        config_success_msg=None,
        config_error_msg=None,
        health_run_check=False,
        health_orphans=health["orphans"],
        health_missing=health["missing"],
        health_stale=health["stale"],
        health_missing_raw=health["missing_raw"],
        health_issue_count=health["issue_count"],
        app_version=APP_VERSION,
        update_available=(PROJECT_ROOT / "update.sh").exists(),
        update_log=None,
        users=list_users(),
        keys=list_keys(),
        new_key=raw,
    )


    return redirect(f"{BASE_PATH}/settings?tab=apikeys&success=API-Key+gelöscht")


@router.post("/api-keys/{key_id}/delete")
async def api_key_delete(key_id: str, request: Request, admin: dict = Depends(require_admin)):
    delete_key(key_id)
    return redirect(f"{BASE_PATH}/settings?tab=apikeys&success=API-Key+gelöscht")


@router.post("/api-keys/reveal")

async def api_key_reveal(request: Request, admin: dict = Depends(require_admin)):
    """Verifiziert das Admin-Passwort und gibt den entschlüsselten API-Schlüssel zurück."""
    try:
        data = await request.json()
        key_id = data.get("key_id")
        password = data.get("password")
    except Exception:
        return JSONResponse({"error": "Ungültiges JSON-Format"}, status_code=400)

    if not key_id or not password:
        return JSONResponse({"error": "Key ID und Passwort erforderlich"}, status_code=400)

    # Passwort des angemeldeten Administrators prüfen
    if not verify_password(password, admin["password_hash"]):
        return JSONResponse({"error": "Ungültiges Passwort"}, status_code=403)

    # API-Schlüssel suchen und entschlüsseln
    keys = list_keys()
    key_obj = next((k for k in keys if k["id"] == key_id), None)
    if not key_obj:
        return JSONResponse({"error": "Schlüssel nicht gefunden"}, status_code=404)

    encrypted = key_obj.get("encrypted_key")
    if not encrypted:
        return JSONResponse({"error": "Dieser Schlüssel wurde vor dem Sicherheitsupdate generiert und kann nicht angezeigt werden. Bitte erstelle einen neuen Schlüssel."}, status_code=400)

    from core.security import decrypt_api_key
    try:
        raw_key = decrypt_api_key(encrypted)
    except Exception:
        raw_key = None

    if not raw_key:
        return JSONResponse({"error": "Entschlüsselung fehlgeschlagen. Das kryptografische System-Secret (LLMWIKI_SECRET) wurde seit der Erstellung des Schlüssels geändert oder zurückgesetzt."}, status_code=500)

    return JSONResponse({"raw_key": raw_key})


@router.post("/system-secret/reveal")
async def system_secret_reveal(request: Request, admin: dict = Depends(require_admin)):
    """Verifiziert das Admin-Passwort und gibt das kryptografische System-Secret zurück."""
    try:
        data = await request.json()
        password = data.get("password")
    except Exception:
        return JSONResponse({"error": "Ungültiges JSON-Format"}, status_code=400)

    if not password:
        return JSONResponse({"error": "Passwort erforderlich"}, status_code=400)

    if not verify_password(password, admin["password_hash"]):
        return JSONResponse({"error": "Ungültiges Passwort"}, status_code=403)

    from core.security import SECRET
    return JSONResponse({"secret": SECRET})


@router.post("/system-secret/regenerate")
async def system_secret_regenerate(request: Request, admin: dict = Depends(require_admin)):
    """Verifiziert das Admin-Passwort, generiert ein neues kryptografisches Secret und speichert es."""
    try:
        data = await request.json()
        password = data.get("password")
    except Exception:
        return JSONResponse({"error": "Ungültiges JSON-Format"}, status_code=400)

    if not password:
        return JSONResponse({"error": "Passwort erforderlich"}, status_code=400)

    if not verify_password(password, admin["password_hash"]):
        return JSONResponse({"error": "Ungültiges Passwort"}, status_code=403)

    import secrets
    from core.config import save_app_config
    import core.security

    new_secret = secrets.token_hex(32)
    try:
        save_app_config({"secret_key": new_secret})
    except Exception as e:
        return JSONResponse({"error": f"Fehler beim Speichern in config.json: {str(e)}"}, status_code=500)

    # In-Memory-Secret aktualisieren, damit die App das neue Secret direkt verwendet
    core.security.SECRET = new_secret
    # Neue Verschlüsselungsobjekte mit dem neuen Secret instanziieren
    from itsdangerous import URLSafeTimedSerializer
    core.security._signer = URLSafeTimedSerializer(new_secret, salt="llmwikisession")
    core.security._key_cipher = URLSafeTimedSerializer(new_secret, salt="llmwikingapikey")

    return JSONResponse({"secret": new_secret, "message": "Geheimnis erfolgreich neu generiert. Hinweis: Zuvor erstellte API-Keys sind nicht mehr entschlüsselbar und müssen neu angelegt werden."})



# ═══════════════════════════════════════════════════════════════════════════════
# Theme (in config.json persistieren, Default = dunkel)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/theme/set")
@router.post("/theme/set")
async def theme_set(request: Request, _: None = Depends(require_login)):
    if request.method == "POST":
        form = await request.form()
        value = form.get("value", "dark")
    else:
        value = request.query_params.get("value", "dark")
    if value not in ("dark", "light"):
        value = "dark"
    data = load_app_config()
    data["theme"] = value
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if request.method == "POST":
        return redirect(f"{BASE_PATH}/settings?tab=theme")
    return JSONResponse({"theme": value})
