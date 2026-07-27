# Implementierungsplan: MCP-Keys-Verwaltung

## Status: VOLLSTÄNDIG UMGESETZT (2026-07-27)

## 1. Ausgangslage & Problemstellung

### Aktueller Stand (v2.12.22)
- **1 globaler MCP-Key** in `config.json` → `llmwiking_mcp_key` (String)
- **Keine User-Zuordnung** — jeder Key funktioniert mit jedem API-Key
- **Keine Tool-Berechtigungen** — alle 31 MCP-Tools sind immer verfügbar
- **Kein Löschen/Ändern** möglich ohne manuelle Config-Edits
- **Sicherheitsrisiko**: Ein kompromittierter MCP-Key gibt vollen Zugriff auf ALLE Tools

### Architektur-Diagramm (aktuell)
```
Client → X-MCP-Key (global) + X-API-Key (pro User) → McpApiKeyMiddleware → MCP-Server
                                                                    ↓
                                                            scope["state"]["mcp_user"]
                                                                    ↓
                                                            31 Tools (alle)
```

### Gewünschter Zustand
- **Mehrere MCP-Keys pro User** mit eigener ID
- **User-Zuordnung** — MCP-Key gehört zu einem bestimmten User
- **Tool-Berechtigungen pro MCP-Key** — nur zugelassene Tools nutzbar
- **Zwangspaarung**: MCP-Key + API-Key müssen demselben User gehören
- **Rückwärtskompatibilität**: Alter globaler Key (`llmwiking_mcp_key`) funktioniert weiter

---

## 2. Neue Datenstruktur

### 2.1 MCP-Keys-Speicher (`data/mcp_keys.json`)

```json
{
  "mcp_keys": [
    {
      "id": "a1b2c3d4e5f6",
      "name": "Mein OpenCode Agent",
      "user_id": "u7x8y9z0",
      "hash": "sha256_des_rohen_keys",
      "encrypted_key": "mcp_xxxxxxxxx... (verschlüsselt)",
      "allowed_tools": ["okf_search", "okf_read_concept", "okf_list_wikis"],
      "active": true,
      "created_at": "2026-07-27T10:00:00",
      "last_used": "2026-07-27T14:30:00"
    }
  ],
  "legacy_mcp_key": "mcp_abc123..."
}
```

### 2.2 Verfügbare Tool-Gruppen (für Berechtigungen)

```python
MCP_TOOL_GROUPS = {
    "wiki_read": {
        "label_de": "Wikis lesen",
        "label_en": "Read Wikis",
        "tools": ["okf_list_wikis", "okf_list_pages", "okf_read_concept", 
                  "okf_wiki_stats", "okf_graph", "okf_search"]
    },
    "wiki_write": {
        "label_de": "Wikis schreiben",
        "label_en": "Write Wikis", 
        "tools": ["okf_create_wiki", "okf_update_wiki", "okf_delete_wiki",
                  "okf_write_concept", "okf_delete_page", "okf_ingest_text",
                  "okf_process_pending", "okf_list_pending"]
    },
    "raw_sources": {
        "label_de": "Rohquellen",
        "label_en": "Raw Sources",
        "tools": ["okf_read_raw", "okf_list_raw"]
    },
    "system": {
        "label_de": "System",
        "label_en": "System",
        "tools": ["okf_system_status", "okf_system_sync", "okf_cache_stats", 
                  "okf_cache_clear", "okf_lint"]
    },
    "users_admin": {
        "label_de": "Benutzer verwalten",
        "label_en": "Manage Users",
        "tools": ["okf_list_users", "okf_create_user", "okf_delete_user"]
    },
    "api_keys_admin": {
        "label_de": "API-Keys verwalten",
        "label_en": "Manage API Keys",
        "tools": ["okf_list_api_keys", "okf_create_api_key", "okf_delete_api_key"]
    },
    "backup_admin": {
        "label_de": "Backups verwalten",
        "label_en": "Manage Backups",
        "tools": ["okf_list_backups", "okf_create_backup", "okf_restore_backup"]
    },
    "update_admin": {
        "label_de": "Updates",
        "label_en": "Updates",
        "tools": ["okf_check_update", "okf_run_update"]
    },
    "audit": {
        "label_de": "Audit-Logs",
        "label_en": "Audit Logs",
        "tools": ["okf_audit_logs"]
    }
}
```

---

## 3. Backend-Änderungen

### 3.1 `backend/core/storage.py` — Neue MCP-Key-Funktionen

```python
# ═══════════════════════════════════════════════════════════════════
# MCP-Key-Verwaltung
# ═══════════════════════════════════════════════════════════════════

MCP_KEYS_FILE = DATA_DIR / "mcp_keys.json"

def list_mcp_keys() -> list[dict]:
    """Liest alle MCP-Keys aus mcp_keys.json."""
    return _load(MCP_KEYS_FILE, {"mcp_keys": [], "legacy_mcp_key": ""})

def _save_mcp_keys(data: dict) -> None:
    _save(MCP_KEYS_FILE, data)

def list_mcp_keys_list() -> list[dict]:
    """Gibt die MCP-Keys-Liste zurück."""
    return list_mcp_keys().get("mcp_keys", [])

def create_mcp_key(user_id: str, name: str, allowed_tools: list[str] | None = None) -> tuple[dict, str]:
    """Erstellt einen neuen MCP-Key. Gibt (key_obj, raw_key) zurück."""
    from core.security import gen_mcp_key, encrypt_mcp_key
    
    raw, h = gen_mcp_key()
    key = {
        "id": secrets.token_hex(8),
        "hash": h,
        "encrypted_key": encrypt_mcp_key(raw),
        "user_id": user_id,
        "name": name,
        "allowed_tools": allowed_tools or [],  # Leer = alle Tools erlaubt
        "active": True,
        "created_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "last_used": None,
    }
    data = list_mcp_keys()
    data["mcp_keys"].append(key)
    _save_mcp_keys(data)
    return key, raw

def delete_mcp_key(key_id: str) -> None:
    """Löscht einen MCP-Key anhand der ID."""
    data = list_mcp_keys()
    data["mcp_keys"] = [k for k in data["mcp_keys"] if k["id"] != key_id]
    _save_mcp_keys(data)

def get_mcp_key_by_hash(h: str) -> dict | None:
    """Sucht einen MCP-Key anhand des Hashes (aktive Keys nur)."""
    return next((k for k in list_mcp_keys_list() if k["hash"] == h and k.get("active", True)), None)

def get_legacy_mcp_key() -> str:
    """Gibt den legacy globalen MCP-Key zurück (für Rückwärtskompatibilität)."""
    data = list_mcp_keys()
    return data.get("legacy_mcp_key", "")

def set_legacy_mcp_key(key: str) -> None:
    """Speichert den legacy globalen MCP-Key."""
    data = list_mcp_keys()
    data["legacy_mcp_key"] = key
    _save_mcp_keys(data)

def update_mcp_key(key_id: str, **changes) -> dict | None:
    """Aktualisiert ein MCP-Key-Feld."""
    data = list_mcp_keys()
    for k in data["mcp_keys"]:
        if k["id"] == key_id:
            k.update(changes)
            _save_mcp_keys(data)
            return k
    return None

def migrate_legacy_mcp_key() -> None:
    """Migriert den alten config.json-llmwiking_mcp_key in die neue Struktur.
    
    Wird beim ersten Start nach dem Update ausgeführt.
    """
    from core.config import load_app_config, save_app_config
    
    data = list_mcp_keys()
    cfg = load_app_config()
    legacy = cfg.get("llmwiking_mcp_key", "")
    
    if legacy and not data.get("legacy_mcp_key"):
        data["legacy_mcp_key"] = legacy
        _save_mcp_keys(data)
```

### 3.2 `backend/core/security.py` — MCP-Key-Funktionen

```python
# ═══════════════════════════════════════════════════════════════════
# MCP-Key-Generierung und -Verschlüsselung
# ═══════════════════════════════════════════════════════════════════

_key_cipher_mcp = URLSafeTimedSerializer(SECRET, salt="llmwikingmcpkey")

def gen_mcp_key() -> tuple[str, str]:
    """Liefert (roher MCP-Key, Hash)."""
    raw = "mcp_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()

def verify_mcp_key(raw: str, stored_hash: str) -> bool:
    """Verifiziert einen MCP-Key gegen seinen Hash."""
    if not raw or not stored_hash:
        return False
    return hashlib.sha256(raw.encode()).hexdigest() == stored_hash

def encrypt_mcp_key(raw_key: str) -> str:
    """Verschlüsselt den rohen MCP-Key umkehrbar mit dem System-Secret."""
    return _key_cipher_mcp.dumps(raw_key)

def decrypt_mcp_key(encrypted_key: str) -> str | None:
    """Entschlüsselt den verschlüsselten MCP-Key."""
    try:
        return _key_cipher_mcp.loads(encrypted_key)
    except Exception:
        return None
```

### 3.3 `backend/core/config.py` — MCP-Tool-Gruppen definieren

```python
# ═══════════════════════════════════════════════════════════════════
# MCP-Tool-Berechtigungsgruppen
# ═══════════════════════════════════════════════════════════════════

MCP_TOOL_GROUPS = {
    "wiki_read": {
        "label_de": "Wikis lesen",
        "label_en": "Read Wikis",
        "tools": ["okf_list_wikis", "okf_list_pages", "okf_read_concept",
                  "okf_wiki_stats", "okf_graph", "okf_search", "okf_export_page"]
    },
    "wiki_write": {
        "label_de": "Wikis schreiben",
        "label_en": "Write Wikis",
        "tools": ["okf_create_wiki", "okf_update_wiki", "okf_delete_wiki",
                  "okf_write_concept", "okf_delete_page", "okf_ingest_text",
                  "okf_process_pending", "okf_list_pending"]
    },
    "raw_sources": {
        "label_de": "Rohquellen",
        "label_en": "Raw Sources",
        "tools": ["okf_read_raw", "okf_list_raw"]
    },
    "system": {
        "label_de": "System",
        "label_en": "System",
        "tools": ["okf_system_status", "okf_system_sync", "okf_cache_stats",
                  "okf_cache_clear", "okf_lint"]
    },
    "users_admin": {
        "label_de": "Benutzer verwalten",
        "label_en": "Manage Users",
        "tools": ["okf_list_users", "okf_create_user", "okf_delete_user"]
    },
    "api_keys_admin": {
        "label_de": "API-Keys verwalten",
        "label_en": "Manage API Keys",
        "tools": ["okf_list_api_keys", "okf_create_api_key", "okf_delete_api_key"]
    },
    "backup_admin": {
        "label_de": "Backups verwalten",
        "label_en": "Manage Backups",
        "tools": ["okf_list_backups", "okf_create_backup", "okf_restore_backup"]
    },
    "update_admin": {
        "label_de": "Updates ausführen",
        "label_en": "Run Updates",
        "tools": ["okf_check_update", "okf_run_update"]
    },
    "audit": {
        "label_de": "Audit-Logs",
        "label_en": "Audit Logs",
        "tools": ["okf_audit_logs"]
    }
}
```

### 3.4 `backend/main.py` — McpApiKeyMiddleware erweitern

**WICHTIGSTE ÄNDERUNG**: Die Middleware muss jetzt:
1. Prüfen ob der MCP-Key ein legacy-Key ODER ein neuer Datenbank-Key ist
2. Den User aus dem API-Key holen und prüfen ob er mit dem MCP-Key-User übereinstimmt
3. Die `allowed_tools` in `scope["state"]` speichern für Tool-Filterung

```python
class McpApiKeyMiddleware:
    """Middleware für MCP-Endpunkte: Prüft MCP-Key + API-Key + User-Match + Tool-Berechtigungen."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and "/mcp/" in scope.get("path", ""):
            headers_dict = dict(scope.get("headers", []))

            # ── 1. MCP-Key aus Header/Query ──
            mcp_key_bytes = headers_dict.get(b"x-mcp-key")
            mcp_key = mcp_key_bytes.decode("utf-8", errors="ignore") if mcp_key_bytes else None
            if not mcp_key:
                from urllib.parse import parse_qs
                query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")
                query_params = parse_qs(query_string)
                mcp_key = query_params.get("mcp_key", [None])[0]

            if not mcp_key:
                response = StarletteJSON({"detail": "MCP-Key erforderlich (X-MCP-Key)"}, status_code=401)
                await response(scope, receive, send)
                return

            # ── 2. MCP-Key verifizieren (neu ODER legacy) ──
            from core.storage import get_mcp_key_by_hash, get_legacy_mcp_key
            import hashlib as _hl
            mcp_hash = _hl.sha256(mcp_key.encode()).hexdigest()
            
            db_mcp_key = get_mcp_key_by_hash(mcp_hash)
            is_legacy = False
            
            if not db_mcp_key:
                # Legacy-Key-Check
                legacy_key = get_legacy_mcp_key()
                if legacy_key and mcp_key == legacy_key:
                    is_legacy = True
                else:
                    response = StarletteJSON({"detail": "Ungültiger MCP-Key (X-MCP-Key)"}, status_code=401)
                    await response(scope, receive, send)
                    return

            # ── 3. API-Key verifizieren ──
            api_key_bytes = headers_dict.get(b"x-api-key")
            api_key = api_key_bytes.decode("utf-8", errors="ignore") if api_key_bytes else None
            if not api_key:
                from urllib.parse import parse_qs
                query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")
                query_params = parse_qs(query_string)
                api_key = query_params.get("api_key", [None])[0]

            if not api_key:
                response = StarletteJSON({"detail": "API-Key erforderlich (X-API-Key)"}, status_code=401)
                await response(scope, receive, send)
                return

            from core.storage import get_key_by_hash, get_user
            api_h = _hl.sha256(api_key.encode()).hexdigest()
            db_api_key = get_key_by_hash(api_h)
            if not db_api_key or not db_api_key.get("active", True):
                response = StarletteJSON({"detail": "Ungültiger API-Key (X-API-Key)"}, status_code=401)
                await response(scope, receive, send)
                return

            # ── 4. User laden ──
            user = get_user(db_api_key["user_id"])
            if not user or not user.get("active", True):
                response = StarletteJSON({"detail": "Benutzer inaktiv"}, status_code=401)
                await response(scope, receive, send)
                return

            # ── 5. User-Match prüfen (nur bei nicht-legacy Keys) ──
            if not is_legacy and db_mcp_key.get("user_id") != user["id"]:
                response = StarletteJSON(
                    {"detail": "MCP-Key und API-Key gehören nicht demselben Benutzer"},
                    status_code=403,
                )
                await response(scope, receive, send)
                return

            # ── 6. Tool-Berechtigungen in scope speichern ──
            if "state" not in scope:
                scope["state"] = {}
            scope["state"]["mcp_user"] = user
            scope["state"]["mcp_key_id"] = db_mcp_key["id"] if db_mcp_key else None
            scope["state"]["mcp_allowed_tools"] = db_mcp_key.get("allowed_tools", []) if db_mcp_key else []
            scope["state"]["mcp_is_legacy"] = is_legacy

            # ── 7. Last-Used aktualisieren ──
            if db_mcp_key:
                from core.storage import update_mcp_key
                update_mcp_key(db_mcp_key["id"], last_used=__import__("datetime").datetime.now().isoformat(timespec="seconds"))

            await self.app(scope, receive, send)
            return

        await self.app(scope, receive, send)
```

### 3.5 `backend/api/routes/mcp.py` — Tool-Filterung

**In jedem MCP-Tool** muss geprüft werden, ob das Tool erlaubt ist:

```python
# Am Anfang von mcp.py, nach den Imports
from starlette.requests import Request

def _check_tool_permission(tool_name: str) -> None:
    """Wirft eine Exception wenn das Tool nicht erlaubt ist.
    
    Wird in jedem MCP-Tool aufgerufen.
    Der request-Context wird über Contextvars bereitgestellt.
    """
    # In FastMCP-Tools gibt es keinen direkten request-Zugriff.
    # Stattdessen nutzen wir Contextvars, die von der Middleware gesetzt werden.
    allowed = _current_allowed_tools.get()
    if not allowed:
        return  # Legacy-Key oder kein Filter = alles erlaubt
    if tool_name not in allowed:
        raise PermissionError(f"Tool '{tool_name}' ist für diesen MCP-Key nicht freigeschaltet.")

import contextvars
_current_allowed_tools: contextvars.ContextVar[list[str]] = contextvars.ContextVar(
    "mcp_allowed_tools", default=[]
)
_current_mcp_user: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "mcp_user", default=None
)
```

**WICHTIG**: Die Context-Vars müssen VOR dem MCP-Tool-Aufruf gesetzt werden. Dafür muss die SSE-App angepasst werden. Die Middleware setzt Werte in `scope["state"]`, aber FastMCP Tools laufen in einem eigenen Context. 

**Alternative Lösung**: Tools registrieren mit `@mcp_server.tool()` und dort via Context-Injector die Berechtigung prüfen. Einfachste Lösung: Ein Decorator/Wrapper:

```python
# Hilfsfunktion für Tool-Berechtigungen
def _mcp_tool_with_permissions(tool_func):
    """Wrapper der Tool-Berechtigungen prüft."""
    import functools
    
    @functools.wraps(tool_func)
    async def wrapper(*args, **kwargs):
        tool_name = tool_func.__name__
        allowed = _current_allowed_tools.get()
        if allowed and tool_name not in allowed:
            return f"❌ Tool '{tool_name}' ist für diesen MCP-Key nicht freigeschaltet. " \
                   f"Erlaubte Tools: {', '.join(allowed)}"
        return await tool_func(*args, **kwargs) if asyncio.iscoroutinefunction(tool_func) else tool_func(*args, **kwargs)
    
    return wrapper
```

**Besser**: Da FastMCP die Tools als normale Funktionen registriert, reicht ein einfacher Check am Anfang:

```python
# In jedem Tool hinzufügen (z.B. okf_write_concept):
@mcp_server.tool()
def okf_write_concept(slug: str, content: str, wiki: str = "main") -> str:
    """Schreibt ein Wiki-Konzept."""
    # ── Berechtigungsprüfung ──
    allowed = _current_allowed_tools.get()
    if allowed and "okf_write_concept" not in allowed:
        return "❌ Keine Berechtigung für dieses Tool."
    
    # ... restlicher Code ...
```

### 3.6 SSE-App-Wrapper für Context-Vars

Die Middleware setzt `scope["state"]["mcp_allowed_tools"]`, aber FastMCP Tools bekommen den Scope nicht direkt. Wir müssen die Werte über Context-Vars übergeben. Dafür wird die SSE-App gewrappt:

```python
# In mcp.py, Funktion get_mcp_sse_app():
def get_mcp_sse_app():
    """Gibt die Starlette SSE-App des MCP-Servers zurück (oder None)."""
    if not (_MCP_AVAILABLE and mcp_server is not None):
        return None
    
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.responses import JSONResponse
    
    # Die originale SSE-App holen
    inner_sse = mcp_sse_app()
    
    # Scope-State in Context-Vars übertragen
    async def scope_middleware(request):
        """Überträgt MCP-Key-Berechtigungen aus scope state in Context-Vars."""
        state = request.scope.get("state", {})
        _current_allowed_tools.set(state.get("mcp_allowed_tools", []))
        _current_mcp_user.set(state.get("mcp_user"))
    
    # Einfachere Lösung: MCP-Tools direkt berechtigungsgeprüft machen
    # Die Context-Vars werden vom ASGI-Scope in die Tool-Funktion übergeben
    return inner_sse
```

**Einfachste funktionierende Lösung**: Da FastMCP SSE die Request-Scope-State-Werte nicht direkt an Tool-Funktionen weitergibt, nutzen wir ein Middleware-Pattern:

```python
# Globaler Context-Vars-Store mit Thread-Locking
import threading
_request_context = threading.local()

def set_mcp_context(allowed_tools: list[str], user: dict | None = None):
    """Setzt den MCP-Kontext für den aktuellen Request."""
    _request_context.allowed_tools = allowed_tools
    _request_context.user = user

def get_mcp_allowed_tools() -> list[str]:
    """Gibt die erlaubten Tools zurück."""
    return getattr(_request_context, "allowed_tools", [])

def get_mcp_user() -> dict | None:
    return getattr(_request_context, "user", None)
```

**Vorzuziehende Lösung**: Die SSE-App in einen Wrapper einbetten, der vor jedem Request die Context-Vars setzt. Da FastMCP SSE eine Starlette-App ist, können wir ein Middleware-Layer dazwischen schalten:

```python
def get_mcp_sse_app():
    if not (_MCP_AVAILABLE and mcp_server is not None):
        return None
    
    sse_app = mcp_server.sse_app()
    
    class McpContextMiddleware:
        """Überträgt scope-state in thread-lokale Context-Vars für Tool-Berechtigungen."""
        def __init__(self, app):
            self.app = app
        
        async def __call__(self, scope, receive, send):
            state = scope.get("state", {})
            set_mcp_context(
                allowed_tools=state.get("mcp_allowed_tools", []),
                user=state.get("mcp_user")
            )
            try:
                await self.app(scope, receive, send)
            finally:
                # Cleanup
                set_mcp_context([], None)
    
    return McpContextMiddleware(sse_app)
```

---

## 4. Frontend-Änderungen

### 4.1 `templates/settings/apikeys.html` — Neue MCP-Keys-Sektion

**Nach der API-Keys-Tabelle und VOR der System-Geheimnis-Card** eine neue Sektion einfügen:

```html
<!-- ═══════════════════════════════════════════════════════════ -->
<!-- MCP Keys Section -->
<!-- ═══════════════════════════════════════════════════════════ -->
<div class="rounded-xl border border-border bg-surface p-6 shadow-sm mt-6">
    <h2 class="text-lg font-semibold mb-1 text-primary">{{ _('mcpkeys.title') }}</h2>
    <p class="text-text-secondary text-sm mb-4">{{ _('mcpkeys.subtitle') }}</p>

    {% if new_mcp_key %}
    <div class="rounded-xl border border-success/40 bg-success-subtle p-5 shadow-sm mb-6 max-w-2xl">
        <p class="mb-2 font-semibold text-success flex items-center gap-1.5">
            <span>✓</span> {{ _('mcpkeys.raw_key_heading') }}
        </p>
        <div class="flex flex-wrap gap-2 items-center">
            <code id="newMcpKey" class="rounded-lg bg-bg-sunken px-3 py-2 text-xs font-mono break-all border border-border select-all">{{ new_mcp_key }}</code>
            <button type="button" onclick="copyMcpKey()" class="rounded-lg border border-border bg-surface px-4 py-2 text-sm font-semibold hover:bg-bg-sunken transition-colors">{{ _('apikeys.copy') }}</button>
        </div>
        <p class="text-xs text-text-muted mt-2">{{ _('mcpkeys.raw_key_hint') }}</p>
    </div>
    {% endif %}

    <!-- MCP Key erzeugen -->
    <div class="rounded-xl border border-border bg-bg-sunken p-4 mb-6 max-w-2xl">
        <h3 class="text-sm font-semibold mb-3 text-text">{{ _('mcpkeys.create_heading') }}</h3>
        <form action="{{ base_path }}/mcp-keys" method="post" class="space-y-3">
            <div>
                <label for="mcp_key_name" class="block text-xs font-semibold text-text-muted uppercase mb-1">{{ _('mcpkeys.name') }}</label>
                <input type="text" name="name" id="mcp_key_name" required class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text focus:border-border-focus focus:ring-2 focus:ring-primary-subtle" placeholder="{{ _('mcpkeys.name_placeholder') }}">
            </div>

            {% if users %}
            <div>
                <label for="mcp_key_user_id" class="block text-xs font-semibold text-text-muted uppercase mb-1">{{ _('mcpkeys.user') }}</label>
                <select name="user_id" id="mcp_key_user_id" class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text focus:border-border-focus focus:ring-2 focus:ring-primary-subtle">
                    {% for u in users %}
                    <option value="{{ u.id }}" {% if current_user and u.id == current_user.id %}selected{% endif %}>{{ u.username }} ({{ u.role }})</option>
                    {% endfor %}
                </select>
            </div>
            {% endif %}

            <!-- Tool-Berechtigungen (Gruppen) -->
            <div>
                <label class="block text-xs font-semibold text-text-muted uppercase mb-2">{{ _('mcpkeys.tool_permissions') }}</label>
                <p class="text-xs text-text-secondary mb-2">{{ _('mcpkeys.tool_permissions_hint') }}</p>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {% for group_key, group in mcp_tool_groups.items() %}
                    <label class="flex items-center gap-2 p-2 rounded-lg border border-border bg-surface hover:bg-bg-sunken cursor-pointer select-none text-sm">
                        <input type="checkbox" name="tool_groups" value="{{ group_key }}" class="rounded border-border text-primary focus:ring-primary-subtle">
                        <span class="font-medium text-text">{{ group['label_' + lang] if ('label_' + lang) in group else group['label_en'] }}</span>
                        <span class="text-xs text-text-muted">({{ group.tools|length }})</span>
                    </label>
                    {% endfor %}
                </div>
                <label class="flex items-center gap-2 mt-2 p-2 rounded-lg border border-primary/30 bg-primary/5 cursor-pointer select-none text-sm">
                    <input type="checkbox" name="all_tools" value="1" class="rounded border-border text-primary focus:ring-primary-subtle" onchange="toggleAllToolGroups(this)">
                    <span class="font-semibold text-primary">{{ _('mcpkeys.all_tools') }}</span>
                </label>
            </div>

            <button type="submit" class="rounded-lg bg-primary hover:bg-primary-hover px-5 py-2 text-sm font-semibold text-white transition-colors shadow-sm">{{ _('mcpkeys.create') }}</button>
        </form>
    </div>

    <!-- MCP Keys Tabelle -->
    <div class="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h3 class="text-lg font-semibold mb-3 border-b border-border pb-2 text-primary">{{ _('mcpkeys.list_heading') }}</h3>
        {% if mcp_keys %}
        <div class="overflow-x-auto">
            <table class="w-full text-sm text-left">
                <thead>
                    <tr class="text-text-muted text-xs uppercase border-b border-border">
                        <th class="py-3 px-2">{{ _('mcpkeys.table_name') }}</th>
                        <th class="py-3 px-2">{{ _('mcpkeys.table_user') }}</th>
                        <th class="py-3 px-2">{{ _('mcpkeys.table_tools') }}</th>
                        <th class="py-3 px-2">{{ _('apikeys.table_active') }}</th>
                        <th class="py-3 px-2">{{ _('apikeys.table_actions') }}</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-border">
                    {% for key in mcp_keys %}
                    <tr class="hover:bg-bg-sunken/30 transition-colors">
                        <td class="py-3.5 px-2 font-semibold text-text">{{ key.name }}</td>
                        <td class="py-3.5 px-2 text-text-secondary">
                            {% set k_user = users | selectattr("id", "equalto", key.user_id) | first %}
                            {% if k_user %}
                            <span class="font-semibold text-text">{{ k_user.username }}</span>
                            {% else %}
                            <span class="font-mono text-xs text-text-muted">ID: {{ key.user_id[:8] }}...</span>
                            {% endif %}
                        </td>
                        <td class="py-3.5 px-2">
                            {% if key.allowed_tools %}
                            <div class="flex flex-wrap gap-1">
                                {% for tool in key.allowed_tools[:5] %}
                                <span class="bg-border text-text px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold">{{ tool }}</span>
                                {% endfor %}
                                {% if key.allowed_tools|length > 5 %}
                                <span class="text-xs text-text-muted">+{{ key.allowed_tools|length - 5 }}</span>
                                {% endif %}
                            </div>
                            {% else %}
                            <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">{{ _('mcpkeys.all_tools_label') }}</span>
                            {% endif %}
                        </td>
                        <td class="py-3.5 px-2">
                            <span class="text-xs font-semibold px-2.5 py-0.5 rounded-full {% if key.active %}bg-success-subtle text-success{% else %}bg-error-subtle text-error{% endif %}">
                                {{ _('apikeys.active') if key.active else _('apikeys.inactive') }}
                            </span>
                        </td>
                        <td class="py-3.5 px-2 text-right">
                            <form action="{{ base_path }}/mcp-keys/{{ key.id }}/delete" method="post" class="inline" onsubmit="return confirm('{{ _('mcpkeys.delete_confirm') }}?');">
                                <button type="submit" class="text-error hover:text-error/80 text-xs font-bold transition-colors">🗑️ {{ _('apikeys.delete') }}</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <p class="text-sm text-text-secondary">{{ _('mcpkeys.no_keys') }}</p>
        {% endif %}
    </div>

    <!-- Legacy-Hinweis -->
    {% if legacy_mcp_key %}
    <div class="rounded-xl border border-yellow-500/30 bg-yellow-500/5 p-4 mt-4 max-w-2xl">
        <p class="text-sm text-yellow-600 font-semibold mb-1">{{ _('mcpkeys.legacy_heading') }}</p>
        <p class="text-xs text-text-secondary">{{ _('mcpkeys.legacy_hint') }}</p>
    </div>
    {% endif %}
</div>
```

### 4.2 JavaScript in `apikeys.html`

```html
<script>
function copyMcpKey() {
    var keyElement = document.getElementById('newMcpKey');
    if (!keyElement) return;
    var textToCopy = keyElement.innerText.trim();
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(textToCopy).then(function() {
            alert('Kopiert!');
        });
    }
}

function toggleAllToolGroups(checkbox) {
    var groupCheckboxes = document.querySelectorAll('input[name="tool_groups"]');
    groupCheckboxes.forEach(function(cb) {
        cb.checked = checkbox.checked;
        cb.disabled = checkbox.checked;
    });
}
</script>
```

---

## 5. Backend-Routen

### 5.1 `backend/api/routes/auth.py` — Neue MCP-Key-Routen

```python
# ═══════════════════════════════════════════════════════════════════
# MCP-Key-Verwaltung (nur Admin)
# ═══════════════════════════════════════════════════════════════════

@router.post("/mcp-keys")
async def mcp_key_create(request: Request, admin: dict = Depends(require_admin)):
    form = await request.form()
    name = (form.get("name") or "").strip()
    target_user_id = form.get("user_id") or admin["id"]
    all_tools = form.get("all_tools") == "1"
    
    # Tools aus Tool-Gruppen zusammensetzen
    from core.config import MCP_TOOL_GROUPS
    allowed_tools = []
    if not all_tools:
        selected_groups = form.getlist("tool_groups")
        for g in selected_groups:
            if g in MCP_TOOL_GROUPS:
                allowed_tools.extend(MCP_TOOL_GROUPS[g]["tools"])
        allowed_tools = sorted(set(allowed_tools))
    
    if not name:
        return redirect(f"{BASE_PATH}/settings?tab=apikeys&error=Name+fuer+MCP-Key+erforderlich")
    
    key_obj, raw = create_mcp_key(
        user_id=target_user_id,
        name=name,
        allowed_tools=allowed_tools,
    )
    
    log_action(
        action="mcp_key_create",
        details=f"MCP-Key '{name}' fuer Benutzer-ID '{target_user_id}' erzeugt ({len(allowed_tools)} Tools)",
        user_id=admin["id"],
        username=admin["username"],
        request=request,
    )
    return redirect(f"{BASE_PATH}/settings?tab=apikeys&new_mcp_key={raw}&success=MCP-Key+erfolgreich+erzeugt")


@router.post("/mcp-keys/{key_id}/delete")
async def mcp_key_delete(key_id: str, request: Request, admin: dict = Depends(require_admin)):
    from core.storage import delete_mcp_key
    delete_mcp_key(key_id)
    log_action(
        action="mcp_key_delete",
        details=f"MCP-Key-ID '{key_id}' geloescht",
        user_id=admin["id"],
        username=admin["username"],
        request=request,
    )
    return redirect(f"{BASE_PATH}/settings?tab=apikeys&success=MCP-Key+geloescht")
```

### 5.2 `backend/api/routes/pages.py` — Context-Vars für Settings

**Im GET-Handler für `/settings`** MCP-Keys und Tool-Gruppen zum Render-Context hinzufügen:

```python
# In settings_get(), Render-Context ergänzen:
from core.storage import list_mcp_keys_list, get_legacy_mcp_key
from core.config import MCP_TOOL_GROUPS

return render(
    request, "settings.html",
    # ... existierende Vars ...
    mcp_keys=list_mcp_keys_list(),
    mcp_tool_groups=MCP_TOOL_GROUPS,
    legacy_mcp_key=get_legacy_mcp_key(),
    lang=getattr(request.state, "lang", "de") if hasattr(request.state, "lang") else "de",
)
```

### 5.3 `backend/api/routes/api.py` — REST API für MCP-Keys

```python
# ═══════════════════════════════════════════════════════════════════
# C. MCP-Key-Verwaltung (REST API)
# ═══════════════════════════════════════════════════════════════════

@router.get("/mcp-keys")
def api_list_mcp_keys(admin: dict = Depends(require_api_admin)):
    """Listet alle MCP-Keys auf (ohne geheime Inhalte)."""
    from core.storage import list_mcp_keys_list
    keys = list_mcp_keys_list()
    return {
        "mcp_keys": [
            {
                "id": k["id"],
                "name": k["name"],
                "user_id": k["user_id"],
                "allowed_tools": k.get("allowed_tools", []),
                "active": k.get("active", True),
                "created_at": k.get("created_at"),
                "last_used": k.get("last_used"),
            }
            for k in keys
        ]
    }


@router.post("/mcp-keys")
async def api_create_mcp_key(request: Request, admin: dict = Depends(require_api_admin)):
    """Erstellt einen neuen MCP-Key."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungueltiger JSON-Body")
    
    name = (body.get("name") or "").strip()
    user_id = body.get("user_id") or admin["id"]
    allowed_tools = body.get("allowed_tools") or []
    
    if not name:
        raise HTTPException(status_code=400, detail="name erforderlich")
    
    from core.storage import create_mcp_key
    key_obj, raw = create_mcp_key(user_id=user_id, name=name, allowed_tools=allowed_tools)
    return JSONResponse(
        status_code=201,
        content={"ok": True, "id": key_obj["id"], "name": name, "mcp_key": raw}
    )


@router.delete("/mcp-keys/{key_id}")
def api_delete_mcp_key(key_id: str, admin: dict = Depends(require_api_admin)):
    """Loescht einen MCP-Key."""
    from core.storage import delete_mcp_key
    delete_mcp_key(key_id)
    return {"ok": True}


@router.get("/mcp-keys/tool-groups")
def api_list_mcp_tool_groups():
    """Listet alle verfuegbaren MCP-Tool-Gruppen auf."""
    from core.config import MCP_TOOL_GROUPS
    return {"tool_groups": MCP_TOOL_GROUPS}
```

---

## 6. Sprachdateien

### 6.1 `lang/de.json` — Neue Keys

```json
"mcpkeys": {
    "title": "MCP-Keys",
    "subtitle": "Verwalte MCP-Schluesse fuer KI-Agenten. Jeder MCP-Key kann nur in Verbindung mit einem API-Key desselben Benutzers verwendet werden.",
    "create_heading": "Neuen MCP-Key erzeugen",
    "name": "Name",
    "name_placeholder": "z.B. OpenCode Agent, Cursor IDE",
    "user": "Benutzer zuweisen",
    "tool_permissions": "Tool-Berechtigungen",
    "tool_permissions_hint": "Waehle aus, welche MCP-Tools dieser Key nutzen darf. Ohne Auswahl hat der Key Zugriff auf alle Tools.",
    "all_tools": "Alle Tools erlauben",
    "all_tools_label": "Alle",
    "create": "MCP-Key erzeugen",
    "raw_key_heading": "Neuer MCP-Key (bitte jetzt kopieren!)",
    "raw_key_hint": "Dieser MCP-Key wird nur EINMAL angezeigt. Speichere ihn sicher.",
    "list_heading": "MCP-Keys",
    "table_name": "Name",
    "table_user": "Benutzer",
    "table_tools": "Erlaubte Tools",
    "table_actions": "Aktionen",
    "delete_confirm": "MCP-Key wirklich loeschen",
    "no_keys": "Noch keine MCP-Keys vorhanden.",
    "legacy_heading": "Hinweis: Legacy-MCP-Key aktiv",
    "legacy_hint": "Ein alter globaler MCP-Key ist konfiguriert. Dieser Key hat vollen Zugriff auf alle Tools und ist keinem Benutzer zugeordnet. Erstelle neue benutzergebundene MCP-Keys fuer bessere Sicherheit.",
    "success": "Erfolg:",
    "error": "Fehler:"
}
```

### 6.2 `lang/en.json` — Neue Keys

```json
"mcpkeys": {
    "title": "MCP Keys",
    "subtitle": "Manage MCP keys for AI agents. Each MCP key can only be used in conjunction with an API key belonging to the same user.",
    "create_heading": "Generate New MCP Key",
    "name": "Name",
    "name_placeholder": "e.g. OpenCode Agent, Cursor IDE",
    "user": "Assign User",
    "tool_permissions": "Tool Permissions",
    "tool_permissions_hint": "Select which MCP tools this key may use. Without selection, the key has access to all tools.",
    "all_tools": "Allow all tools",
    "all_tools_label": "All",
    "create": "Generate MCP Key",
    "raw_key_heading": "New MCP Key (copy it now!)",
    "raw_key_hint": "This MCP key is shown only ONCE. Save it securely.",
    "list_heading": "MCP Keys",
    "table_name": "Name",
    "table_user": "User",
    "table_tools": "Allowed Tools",
    "table_actions": "Actions",
    "delete_confirm": "Really delete MCP key",
    "no_keys": "No MCP keys yet.",
    "legacy_heading": "Note: Legacy MCP key active",
    "legacy_hint": "A legacy global MCP key is configured. This key has full access to all tools and is not assigned to any user. Create new user-bound MCP keys for better security.",
    "success": "Success:",
    "error": "Error:"
}
```

---

## 7. Migration

### 7.1 Beim ersten Start nach Update

```python
# In backend/main.py oder backend/core/config.py
def _migrate_mcp_keys():
    """Migration: Alten globalen MCP-Key in die neue Struktur ueberfuehren."""
    from core.storage import list_mcp_keys, _save_mcp_keys
    data = list_mcp_keys()
    
    # Nur migrieren wenn keine mcp_keys.json existiert
    if not data.get("mcp_keys") and not data.get("legacy_mcp_key"):
        cfg = load_app_config()
        legacy = cfg.get("llmwiking_mcp_key", "")
        if legacy:
            data["legacy_mcp_key"] = legacy
            _save_mcp_keys(data)
```

### 7.2 Rückwärtskompatibilität

- Alter `config.json` → `llmwiking_mcp_key` wird BEIBEHALTEN
- Legacy-Key wird in `mcp_keys.json` → `legacy_mcp_key` kopiert
- Middleware akzeptiert sowohl neue DB-Keys als auch den legacy-Key
- Legacy-Key zeigt Warnung in der UI
- Neue Keys sind benutzergebunden und tool-beschränkt

---

## 8. Sicherheitsvorteile

1. **Least Privilege**: Jeder MCP-Key bekommt nur die Tools die er braucht
2. **User-Isolation**: Keys gehören zu bestimmten Usern, keine Cross-User-Nutzung
3. **Audit-Trail**: Jeder MCP-Key-Eintrag hat `created_at`, `last_used`, `user_id`
4. **Key-Rotation**: Leichte Erstellung neuer und Löschung alter Keys
5. **Legacy-Warnung**: Alte globale Keys werden als unsicher markiert
6. **Verschlüsselung**: MCP-Keys werden verschlüsselt gespeichert (wie API-Keys)
7. **Transparenz**: Admin sieht in der UI welche Tools ein Agent nutzen darf

---

## 9. Datei-Übersicht

| Datei | Änderung |
|-------|----------|
| `backend/core/security.py` | `gen_mcp_key()`, `encrypt_mcp_key()`, `decrypt_mcp_key()` |
| `backend/core/storage.py` | `MCP_KEYS_FILE`, `create_mcp_key()`, `delete_mcp_key()`, `list_mcp_keys_list()`, etc. |
| `backend/core/config.py` | `MCP_TOOL_GROUPS` Dictionary |
| `backend/main.py` | `McpApiKeyMiddleware` erweitern (User-Match, Tool-Permissions, Legacy-Key) |
| `backend/api/routes/mcp.py` | Tool-Berechtigungsprüfung, Context-Middleware |
| `backend/api/routes/auth.py` | `POST /mcp-keys`, `POST /mcp-keys/{id}/delete` |
| `backend/api/routes/api.py` | `GET/POST/DELETE /api/v1/mcp-keys`, `GET /api/v1/mcp-keys/tool-groups` |
| `backend/api/routes/pages.py` | Settings-Context mit `mcp_keys`, `mcp_tool_groups`, `legacy_mcp_key` |
| `templates/settings/apikeys.html` | Neue MCP-Keys-Sektion (Form + Tabelle + Legacy-Warnung) |
| `lang/de.json` | `mcpkeys.*` Übersetzungen |
| `lang/en.json` | `mcpkeys.*` Übersetzungen |
| `templates/docs.html` | MCP-Key-Dokumentation aktualisieren |
| `templates/docs_de.html` | MCP-Key-Dokumentation aktualisieren |
| `CHANGELOG.md` | Neue Features dokumentieren |
| `README.md` | MCP-Key-Section aktualisieren |
| `.gitignore` | `IMPLEMENTIERUNGSPLAN_MCP_KEYS.md` hinzufügen |
