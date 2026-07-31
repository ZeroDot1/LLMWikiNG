"""LLMWikiNG – Sicherheit: Passwort-Hashing, Session-Signing, API-Key-Verwaltung.

2026-Standard: Argon2id für Passwörter (OWASP-Empfehlung), signierte Session-Cookies
via itsdangerous, gehashte API-Keys (SHA-256, roher Key nur einmal sichtbar).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

import argon2
from cryptography.fernet import Fernet
from itsdangerous import URLSafeTimedSerializer

def _get_persistent_secret() -> str:
    """Holt das kryptografische System-Secret ausschließlich aus config.json.

    Falls noch kein Secret in config.json existiert (z. B. vor der Ersterstellung),
    wird ein neues erzeugt und sofort in config.json gesichert.
    """
    from core.config import load_app_config, save_app_config
    try:
        cfg = load_app_config()
        if cfg.get("secret_key"):
            return str(cfg["secret_key"])
    except Exception:
        pass

    # Wenn noch kein Secret existiert, neu generieren und in config.json persistieren
    new_secret = secrets.token_hex(32)
    try:
        save_app_config({"secret_key": new_secret})
    except Exception:
        pass
    return new_secret

SECRET = _get_persistent_secret()
_ph = argon2.PasswordHasher()
_signer = URLSafeTimedSerializer(SECRET, salt="llmwikisession")

SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 Tage


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hpw: str) -> bool:
    try:
        return _ph.verify(hpw, pw)
    except (argon2.exceptions.VerifyMismatchError, argon2.exceptions.VerificationError,
            argon2.exceptions.InvalidHashError, TypeError, ValueError, UnicodeEncodeError):
        return False


def needs_rehash(hpw: str) -> bool:
    try:
        return _ph.check_needs_rehash(hpw)
    except Exception:
        return False


def create_session(user_id: str) -> str:
    return _signer.dumps({"uid": user_id})


def read_session(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _signer.loads(token, max_age=SESSION_MAX_AGE).get("uid")
    except Exception:
        return None


def create_csrf_token(session_uid: str) -> str:
    return _signer.dumps({"csrf": session_uid, "t": "csrf"}, salt="llmwikicsrf")


def verify_csrf_token(token: str | None, session_uid: str) -> bool:
    if not token or not session_uid:
        return False
    try:
        data = _signer.loads(token, max_age=SESSION_MAX_AGE, salt="llmwikicsrf")
        return data.get("csrf") == session_uid and data.get("t") == "csrf"
    except Exception:
        return False


def gen_api_key() -> tuple[str, str]:
    """Liefert (roher Key, Hash)."""
    raw = "llmw_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def verify_api_key(raw: str, stored_hash: str) -> bool:
    if not raw or not stored_hash:
        return False
    computed = hashlib.sha256(raw.encode()).hexdigest()
    return hmac.compare_digest(computed, stored_hash)


import base64
from cryptography.fernet import Fernet

_key_cipher = URLSafeTimedSerializer(SECRET, salt="llmwikingapikey")
_key_cipher_mcp = URLSafeTimedSerializer(SECRET, salt="llmwikingmcpkey")
_key_cipher_tailscale = URLSafeTimedSerializer(SECRET, salt="llmwikingtailscale")


def _get_fernet(salt: str = "llmwiking") -> Fernet:
    """Leitet einen Fernet-Key aus dem System-Secret ab."""
    key = hashlib.sha256(f"{SECRET}:{salt}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_api_key(raw_key: str) -> str:
    """Verschlüsselt den rohen API-Schlüssel umkehrbar mit Fernet (AES-128-CBC + HMAC)."""
    return _get_fernet("llmwikingapikey").encrypt(raw_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str | None:
    """Entschlüsselt den verschlüsselten API-Schlüssel mit Abwärtskompatibilität."""
    if not encrypted_key:
        return None
    try:
        return _get_fernet("llmwikingapikey").decrypt(encrypted_key.encode()).decode()
    except Exception:
        try:
            return _key_cipher.loads(encrypted_key, max_age=None)
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════
# MCP-Key-Generierung und -Verschlüsselung
# ═══════════════════════════════════════════════════════════════════

def gen_mcp_key() -> tuple[str, str]:
    """Liefert (rohen MCP-Key, Hash)."""
    raw = "mcp_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def verify_mcp_key(raw: str, stored_hash: str) -> bool:
    """Verifiziert einen MCP-Key gegen seinen Hash (timing-safe)."""
    if not raw or not stored_hash:
        return False
    computed = hashlib.sha256(raw.encode()).hexdigest()
    return hmac.compare_digest(computed, stored_hash)


def encrypt_mcp_key(raw_key: str) -> str:
    """Verschlüsselt den rohen MCP-Key umkehrbar mit Fernet."""
    return _get_fernet("llmwikingmcpkey").encrypt(raw_key.encode()).decode()


def decrypt_mcp_key(encrypted_key: str) -> str | None:
    """Entschlüsselt den verschlüsselten MCP-Key mit Abwärtskompatibilität."""
    if not encrypted_key:
        return None
    try:
        return _get_fernet("llmwikingmcpkey").decrypt(encrypted_key.encode()).decode()
    except Exception:
        try:
            return _key_cipher_mcp.loads(encrypted_key, max_age=None)
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════
# Tailscale-Key-Verschlüsselung
# ═══════════════════════════════════════════════════════════════════

def encrypt_tailscale_key(raw_key: str) -> str:
    """Encrypts raw Tailscale auth key with Fernet."""
    return _get_fernet("llmwikingtailscale").encrypt(raw_key.encode()).decode()


def decrypt_tailscale_key(encrypted_key: str) -> str | None:
    """Decrypts Tailscale auth key with backwards compatibility."""
    if not encrypted_key:
        return None
    try:
        return _get_fernet("llmwikingtailscale").decrypt(encrypted_key.encode()).decode()
    except Exception:
        try:
            return _key_cipher_tailscale.loads(encrypted_key, max_age=None)
        except Exception:
            return None


