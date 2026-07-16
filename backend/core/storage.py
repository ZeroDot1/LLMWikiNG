"""LLMWikiNG – Persistenz für Benutzer und API-Keys.

Einfacher JSON-Store (passend zum bestehenden config.json-Ansatz). Bei vielen
Benutzern später auf SQLite wechselbar, ohne die storage-API zu ändern.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from core.config import DATA_DIR
from core.security import hash_password, gen_api_key

USERS_FILE = DATA_DIR / "users.json"
KEYS_FILE = DATA_DIR / "api_keys.json"


def _load(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def _save(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def list_users() -> list[dict]:
    return _load(USERS_FILE, [])


def save_users(users: list[dict]) -> None:
    _save(USERS_FILE, users)


def get_user(user_id: str) -> dict | None:
    return next((u for u in list_users() if u["id"] == user_id), None)


def get_user_by_name(username: str) -> dict | None:
    return next((u for u in list_users() if u["username"].lower() == username.lower()), None)


def create_user(username: str, password: str, role: str = "admin") -> dict:
    users = list_users()
    if any(u["username"].lower() == username.lower() for u in users):
        raise ValueError("Benutzer existiert bereits")
    user = {
        "id": secrets.token_hex(8),
        "username": username,
        "password_hash": hash_password(password),
        "role": role,
        "active": True,
        "created_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }
    users.append(user)
    save_users(users)
    return user


def update_user(user_id: str, **changes) -> dict | None:
    users = list_users()
    for u in users:
        if u["id"] == user_id:
            if "password" in changes:
                u["password_hash"] = hash_password(changes.pop("password"))
            u.update(changes)
            save_users(users)
            return u
    return None


def delete_user(user_id: str) -> None:
    users = [u for u in list_users() if u["id"] != user_id]
    save_users(users)


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
        "created_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "last_used": None,
    }
    keys = list_keys()
    keys.append(key)
    save_keys(keys)
    return key, raw



def delete_key(key_id: str) -> None:
    keys = [k for k in list_keys() if k["id"] != key_id]
    save_keys(keys)


def get_key_by_hash(h: str) -> dict | None:
    return next((k for k in list_keys() if k["hash"] == h and k["active"]), None)
