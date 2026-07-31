"""LLMWikiNG – Persistenz für Benutzer, API-Keys und MCP-Keys.

Einfacher JSON-Store (passend zum bestehenden config.json-Ansatz). Bei vielen
Benutzern später auf SQLite wechselbar, ohne die storage-API zu ändern.
"""

from __future__ import annotations

import fcntl
import json
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.config import DATA_DIR
from core.security import hash_password, gen_api_key

USERS_FILE = DATA_DIR / "users.json"
KEYS_FILE = DATA_DIR / "api_keys.json"
MCP_KEYS_FILE = DATA_DIR / "mcp_keys.json"

_storage_thread_lock = threading.Lock()


@contextmanager
def _locked_write(path: Path):
    """Atomares Schreiben mit Process- und Thread-Lock."""
    with _storage_thread_lock:
        lock_path = path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(lock_path, "w") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            yield


def _load(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _save(p: Path, data) -> None:
    with _locked_write(p):
        _write(p, data)


def list_users() -> list[dict]:
    return _load(USERS_FILE, [])


def save_users(users: list[dict]) -> None:
    _save(USERS_FILE, users)


def get_user(user_id: str) -> dict | None:
    return next((u for u in list_users() if u.get("id") == user_id), None)


def get_user_by_name(username: str) -> dict | None:
    return next((u for u in list_users() if u.get("username", "").lower() == username.lower()), None)


def create_user(username: str, password: str, role: str = "admin") -> dict:
    with _locked_write(USERS_FILE):
        users = list_users()
        if any(u.get("username", "").lower() == username.lower() for u in users):
            raise ValueError("Benutzer existiert bereits")
        user = {
            "id": secrets.token_hex(8),
            "username": username,
            "password_hash": hash_password(password),
            "role": role,
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        users.append(user)
        _write(USERS_FILE, users)
        return user


def update_user(user_id: str, **changes) -> dict | None:
    with _locked_write(USERS_FILE):
        users = list_users()
        for u in users:
            if u.get("id") == user_id:
                if "password" in changes:
                    u["password_hash"] = hash_password(changes.pop("password"))
                u.update(changes)
                _write(USERS_FILE, users)
                return u
    return None


def delete_user(user_id: str) -> None:
    with _locked_write(USERS_FILE):
        users = [u for u in list_users() if u.get("id") != user_id]
        _write(USERS_FILE, users)


def list_keys() -> list[dict]:
    return _load(KEYS_FILE, [])


def save_keys(keys: list[dict]) -> None:
    _save(KEYS_FILE, keys)


def create_key(user_id: str, name: str, require_password: bool = False,
                scopes: list[str] | None = None) -> tuple[dict, str]:
    from core.security import encrypt_api_key
    raw, h = gen_api_key()
    key = {
        "id": secrets.token_hex(8),
        "hash": h,
        "encrypted_key": encrypt_api_key(raw),
        "user_id": user_id,
        "name": name,
        "require_password": require_password,
        "scopes": scopes or ["read", "write"],
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_used": None,
    }
    with _locked_write(KEYS_FILE):
        keys = list_keys()
        keys.append(key)
        _write(KEYS_FILE, keys)
    return key, raw



def delete_key(key_id: str) -> None:
    keys = [k for k in list_keys() if k["id"] != key_id]
    save_keys(keys)


def delete_all_keys() -> int:
    """Löscht alle REST-API-Keys. Gibt die Anzahl gelöschter Keys zurück."""
    keys = list_keys()
    count = len(keys)
    save_keys([])
    return count


def get_key_by_hash(h: str) -> dict | None:
    return next((k for k in list_keys() if k["hash"] == h and k["active"]), None)


# ═══════════════════════════════════════════════════════════════════
# MCP-Key-Verwaltung
# ═══════════════════════════════════════════════════════════════════

def _load_mcp_data() -> dict:
    """Lädt die MCP-Key-Datenstruktur (Keys-Liste + Legacy-Key)."""
    raw = _load(MCP_KEYS_FILE, {"mcp_keys": [], "legacy_mcp_key": ""})
    if isinstance(raw, list):
        return {"mcp_keys": raw, "legacy_mcp_key": ""}
    if not isinstance(raw, dict):
        return {"mcp_keys": [], "legacy_mcp_key": ""}
    return raw


def _save_mcp_data(data: dict) -> None:
    """Speichert die MCP-Key-Datenstruktur."""
    _save(MCP_KEYS_FILE, data)


def list_mcp_keys() -> list[dict]:
    """Gibt die Liste aller MCP-Keys zurück."""
    return _load_mcp_data().get("mcp_keys", [])


def get_mcp_key(key_id: str) -> dict | None:
    """Sucht einen MCP-Key anhand der ID."""
    return next((k for k in list_mcp_keys() if k["id"] == key_id), None)


def get_mcp_key_by_hash(h: str) -> dict | None:
    """Sucht einen MCP-Key anhand des Hashes (aktive Keys nur)."""
    return next((k for k in list_mcp_keys() if k["hash"] == h and k.get("active", True)), None)


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
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "last_used": None,
    }
    data = _load_mcp_data()
    data.setdefault("mcp_keys", []).append(key)
    _save_mcp_data(data)
    return key, raw


def delete_mcp_key(key_id: str) -> bool:
    """Löscht einen MCP-Key anhand der ID. Gibt True zurück wenn gefunden und gelöscht."""
    data = _load_mcp_data()
    old_len = len(data.get("mcp_keys", []))
    data["mcp_keys"] = [k for k in data.get("mcp_keys", []) if k["id"] != key_id]
    deleted = len(data["mcp_keys"]) < old_len
    if deleted:
        _save_mcp_data(data)
    return deleted


def delete_all_mcp_keys() -> int:
    """Löscht alle MCP-Keys. Gibt Anzahl gelöschter Keys zurück."""
    data = _load_mcp_data()
    count = len(data.get("mcp_keys", []))
    data["mcp_keys"] = []
    _save_mcp_data(data)
    return count


def update_mcp_key(key_id: str, **changes) -> dict | None:
    """Aktualisiert ein MCP-Key-Feld. Gibt das aktualisierte Objekt zurück."""
    data = _load_mcp_data()
    for k in data.get("mcp_keys", []):
        if k["id"] == key_id:
            k.update(changes)
            _save_mcp_data(data)
            return k
    return None


def get_legacy_mcp_key() -> str:
    """Gibt den legacy globalen MCP-Key zurück (für Rückwärtskompatibilität)."""
    return _load_mcp_data().get("legacy_mcp_key", "")


def set_legacy_mcp_key(key: str) -> None:
    """Speichert den legacy globalen MCP-Key."""
    data = _load_mcp_data()
    data["legacy_mcp_key"] = key
    _save_mcp_data(data)
