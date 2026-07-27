"""LLMWikiNG – Authentifizierungs-Routen (Login, Logout, User- & API-Key-Verwaltung)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

import json
import os

from core.config import BASE_PATH, CONFIG_FILE, load_app_config, APP_VERSION, PROJECT_ROOT
from web import render, redirect, urlencode
from api.deps import require_login, require_admin
from services.audit import log_action, ALL_CATEGORIES
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
    list_mcp_keys,
    create_mcp_key,
    delete_mcp_key,
    update_mcp_key,
)

router = APIRouter(prefix=BASE_PATH)


@router.get("/login")
def login_form(request: Request):
    if len(list_users()) == 0:
        return redirect(f"{BASE_PATH}/register")
    cfg = load_app_config()
    return render(
        request, "login.html",
        active_page="login",
        setup=False,
        error=request.query_params.get("error"),
        hide_nav=True,
        registration_enabled=cfg.get("registration_enabled", True),
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
        # Nach Erstanlage: Registrierung automatisch deaktivieren
        from core.config import save_app_config
        save_app_config({"registration_enabled": False})
        log_action(action="setup_admin", details=f"Erstes Administrator-Konto erstellt: {username}", user_id=user["id"], username=user["username"], request=request)
        return _set_session_and_redirect(user)

    user = get_user_by_name(username)
    if not user or not user.get("active", True) or not verify_password(password, user["password_hash"]):
        log_action(action="login_failed", details=f"Fehlgeschlagener Login-Versuch für Benutzer: {username}", request=request)
        return redirect(f"{BASE_PATH}/login?error=Login+fehlgeschlagen")

    log_action(action="login", details=f"Benutzer erfolgreich angemeldet", user_id=user["id"], username=user["username"], request=request)
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
def logout(request: Request, user: dict = Depends(require_login)):
    from fastapi.responses import RedirectResponse

    log_action(action="logout", details="Benutzer abgemeldet", user_id=user["id"], username=user["username"], request=request)
    resp = RedirectResponse(f"{BASE_PATH}/login", status_code=303)
    resp.delete_cookie("session")
    return resp


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
        log_action(action="user_create", details=f"Benutzer '{username}' mit Rolle '{role}' angelegt", user_id=admin["id"], username=admin["username"], request=request)
    except ValueError as e:
        return redirect(f"{BASE_PATH}/settings?tab=users&error={urlencode(str(e))}")
    return redirect(f"{BASE_PATH}/settings?tab=users&success=Benutzer+angelegt")


@router.get("/users/{user_id}/delete")
async def user_delete(user_id: str, request: Request, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        return redirect(f"{BASE_PATH}/settings?tab=users&error=Du+kannst+dich+nicht+selbst+löschen")
    target_user = get_user(user_id)
    target_username = target_user["username"] if target_user else user_id
    delete_user(user_id)
    log_action(action="user_delete", details=f"Benutzer '{target_username}' gelöscht", user_id=admin["id"], username=admin["username"], request=request)
    return redirect(f"{BASE_PATH}/settings?tab=users&success=Benutzer+gelöscht")


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
    log_action(action="api_key_create", details=f"API-Key '{name}' für Benutzer-ID '{target_user_id}' erzeugt", user_id=admin["id"], username=admin["username"], request=request)
    smtp_config = load_smtp_config()
    health = {"orphans": [], "missing": [], "stale": [], "missing_raw": [], "issue_count": 0}
    return render(
        request, "settings.html",
        active_page="settings",
        smtp_config=smtp_config,
        env_user=os.environ.get("GMAIL_USER", ""),
        env_pass_exists=bool(os.environ.get("GMAIL_APP_PASSWORD")),
        audit_config=load_app_config(),
        all_audit_categories=ALL_CATEGORIES,
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
        new_generated_mcp_key=None,
        new_generated_api_key=None,
        registration_enabled=load_app_config().get("registration_enabled", True),
    )


@router.post("/api-keys/{key_id}/delete")
async def api_key_delete(key_id: str, request: Request, admin: dict = Depends(require_admin)):
    delete_key(key_id)
    log_action(action="api_key_delete", details=f"API-Key-ID '{key_id}' gelöscht", user_id=admin["id"], username=admin["username"], request=request)
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

    if not verify_password(password, admin["password_hash"]):
        return JSONResponse({"error": "Ungültiges Passwort"}, status_code=403)

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
        return JSONResponse({"error": "Entschlüsselung fehlgeschlagen. Das kryptografische System-Secret (secret_key in config.json) unterscheidet sich vom Secret zum Zeitpunkt der Erstellung dieses Schlüssels."}, status_code=400)

    log_action(action="api_key_reveal", details=f"API-Key '{key_obj.get('name')}' (ID: {key_id}) entschlüsselt und angezeigt", user_id=admin["id"], username=admin["username"], request=request)
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
    log_action(action="system_secret_reveal", details="System-Secret angezeigt", user_id=admin["id"], username=admin["username"], request=request)
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
    core.security._key_cipher_mcp = URLSafeTimedSerializer(new_secret, salt="llmwikingmcpkey")

    log_action(action="system_secret_regenerate", details="System-Secret neu generiert", user_id=admin["id"], username=admin["username"], request=request)
    return JSONResponse({"secret": new_secret, "message": "Geheimnis erfolgreich neu generiert. Hinweis: Zuvor erstellte API-Keys und MCP-Keys sind nicht mehr entschlüsselbar und müssen neu angelegt werden."})



@router.post("/mcp-keys")
async def mcp_key_create(request: Request, admin: dict = Depends(require_admin)):
    form = await request.form()
    name = (form.get("name") or "").strip()
    target_user_id = form.get("user_id") or admin["id"]
    all_tools = form.get("all_tools") == "1"
    
    if all_tools:
        allowed_tools = []
    else:
        allowed_tools = form.getlist("allowed_tools")
        if not allowed_tools:
            selected_groups = form.getlist("tool_groups")
            if selected_groups:
                from core.config import MCP_TOOL_GROUPS
                for g in selected_groups:
                    if g in MCP_TOOL_GROUPS:
                        allowed_tools.extend(MCP_TOOL_GROUPS[g]["tools"])
                allowed_tools = sorted(set(allowed_tools))

    if not name:
        return redirect(f"{BASE_PATH}/settings?tab=apikeys&error=Name+für+MCP-Schlüssel+erforderlich")
    key_obj, raw = create_mcp_key(
        user_id=target_user_id,
        name=name,
        allowed_tools=allowed_tools,
    )
    log_action(action="mcp_key_create", details=f"MCP-Key '{name}' für Benutzer-ID '{target_user_id}' erzeugt ({len(allowed_tools)} Tools)", user_id=admin["id"], username=admin["username"], request=request)
    return redirect(f"{BASE_PATH}/settings?tab=apikeys&success=MCP-Schlüssel+erzeugt&mcp_new_key={raw}")


@router.post("/mcp-keys/{key_id}/delete")
async def mcp_key_delete(key_id: str, request: Request, admin: dict = Depends(require_admin)):
    delete_mcp_key(key_id)
    log_action(action="mcp_key_delete", details=f"MCP-Key-ID '{key_id}' gelöscht", user_id=admin["id"], username=admin["username"], request=request)
    return redirect(f"{BASE_PATH}/settings?tab=apikeys&success=MCP-Schlüssel+gelöscht")


@router.post("/mcp-keys/{key_id}/edit")
async def mcp_key_edit(key_id: str, request: Request, admin: dict = Depends(require_admin)):
    """Bearbeitet Name, Zugeordneten User und Tool-Berechtigungen eines MCP-Keys."""
    form = await request.form()
    name = (form.get("name") or "").strip()
    target_user_id = form.get("user_id") or admin["id"]
    all_tools = form.get("all_tools") == "1"
    active = form.get("active") == "1"
    
    if all_tools:
        allowed_tools = []
    else:
        allowed_tools = form.getlist("allowed_tools")
        if not allowed_tools:
            selected_groups = form.getlist("tool_groups")
            if selected_groups:
                from core.config import MCP_TOOL_GROUPS
                allowed_tools = []
                for g in selected_groups:
                    if g in MCP_TOOL_GROUPS:
                        allowed_tools.extend(MCP_TOOL_GROUPS[g]["tools"])
                allowed_tools = sorted(set(allowed_tools))

    if not name:
        return redirect(f"{BASE_PATH}/settings?tab=apikeys&error=Name+für+MCP-Schlüssel+erforderlich")
        
    updated = update_mcp_key(
        key_id,
        name=name,
        user_id=target_user_id,
        allowed_tools=allowed_tools,
        active=active
    )
    if updated:
        log_action(action="settings_change", details=f"MCP-Key '{name}' (ID: {key_id[:8]}) aktualisiert ({len(allowed_tools)} Tools)", user_id=admin["id"], username=admin["username"], request=request)
        return redirect(f"{BASE_PATH}/settings?tab=apikeys&success=MCP-Schlüssel+erfolgreich+aktualisiert")
    return redirect(f"{BASE_PATH}/settings?tab=apikeys&error=MCP-Schlüssel+nicht+gefunden")



@router.post("/mcp-keys/reveal")
async def mcp_key_reveal(request: Request, admin: dict = Depends(require_admin)):
    """Verifiziert das Admin-Passwort und gibt den entschlüsselten MCP-Schlüssel zurück."""
    try:
        data = await request.json()
        key_id = data.get("key_id")
        password = data.get("password")
    except Exception:
        return JSONResponse({"error": "Ungültiges JSON-Format"}, status_code=400)

    if not key_id or not password:
        return JSONResponse({"error": "Key ID und Passwort erforderlich"}, status_code=400)

    if not verify_password(password, admin["password_hash"]):
        return JSONResponse({"error": "Ungültiges Passwort"}, status_code=403)

    keys = list_mcp_keys()
    key_obj = next((k for k in keys if k["id"] == key_id), None)
    if not key_obj:
        return JSONResponse({"error": "Schlüssel nicht gefunden"}, status_code=404)

    encrypted = key_obj.get("encrypted_key")
    if not encrypted:
        return JSONResponse({"error": "Dieser Schlüssel wurde vor dem Sicherheitsupdate generiert und kann nicht angezeigt werden."}, status_code=400)

    from core.security import decrypt_mcp_key
    try:
        raw_key = decrypt_mcp_key(encrypted)
    except Exception:
        raw_key = None

    if not raw_key:
        return JSONResponse({"error": "Entschlüsselung fehlgeschlagen. Das System-Secret (secret_key in config.json) unterscheidet sich vom Erstellungszeitpunkt."}, status_code=400)

    log_action(action="mcp_key_reveal", details=f"MCP-Key '{key_obj.get('name')}' (ID: {key_id}) entschlüsselt und angezeigt", user_id=admin["id"], username=admin["username"], request=request)
    return JSONResponse({"raw_key": raw_key})


@router.get("/theme/set")
@router.post("/theme/set")
async def theme_set(request: Request, user: dict = Depends(require_login)):
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
    log_action(action="theme_change", details=f"Theme auf '{value}' geändert", user_id=user["id"], username=user["username"], request=request)
    if request.method == "POST":
        return redirect(f"{BASE_PATH}/settings?tab=theme")
    return JSONResponse({"theme": value})
