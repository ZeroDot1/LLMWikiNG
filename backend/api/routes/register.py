"""LLMWikiNG – Benutzerregistrierung (GET/POST /register).

Erlaubt die Registrierung des ersten Administrators sowie optionaler weiterer Benutzer (wenn aktiviert).
Generiert automatisch einen Default-API-Key für den neu registrierten Benutzer.
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from core.config import BASE_PATH, load_app_config, save_app_config, APP_VERSION
from core.storage import list_users, create_user, create_key
from web import render, redirect

router = APIRouter(prefix=BASE_PATH)

@router.get("/register")
def register_form(request: Request):
    users = list_users()
    is_first = len(users) == 0
    cfg = load_app_config()
    
    # Wenn nicht die erste Registrierung und Registrierung in Config deaktiviert ist -> Fehler
    if not is_first and not cfg.get("registration_enabled", True):
        return render(
            request, "error.html",
            active_page="error",
            content="<h1>403 – Registrierung deaktiviert</h1><p>Die Registrierung für neue Benutzer wurde vom Administrator deaktiviert.</p>",
            hide_nav=True
        )

    return render(
        request, "register.html",
        active_page="register",
        is_first=is_first,
        error=request.query_params.get("error"),
        hide_nav=True,
    )


@router.post("/register")
async def register_submit(request: Request):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = (form.get("password") or "").strip()
    
    if not username or not password:
        return redirect(f"{BASE_PATH}/register?error=Benutzername und Passwort sind Pflichtfelder")
        
    users = list_users()
    is_first = len(users) == 0
    cfg = load_app_config()
    
    # Sicherheitsprüfung
    if not is_first and not cfg.get("registration_enabled", True):
        raise HTTPException(status_code=403, detail="Registrierung deaktiviert")
        
    try:
        # Erster User ist Admin, alle weiteren standardmäßig Editor (oder Admin falls gewünscht)
        role = "admin" if is_first else "editor"
        user = create_user(username, password, role=role)
        
        # Automatisch einen Standard-API-Key erstellen
        _, raw_key = create_key(user["id"], "Standard API-Key")
        
        # Wenn dies der erste Admin war, Registrierung direkt automatisch deaktivieren
        if is_first:
            save_app_config({"registration_enabled": False})
            
        # Erfolgsseite mit API-Key anzeigen (wird nur einmal angezeigt)
        return render(
            request, "register_success.html",
            active_page="register",
            username=username,
            raw_key=raw_key,
            role=role,
            hide_nav=True
        )
    except ValueError as e:
        return redirect(f"{BASE_PATH}/register?error={str(e)}")
    except Exception as e:
        return redirect(f"{BASE_PATH}/register?error=Interner Registrierungsfehler: {str(e)}")
