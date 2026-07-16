"""LLMWikiNG – Sicherheit: Passwort-Hashing, Session-Signing, API-Key-Verwaltung.

2026-Standard: Argon2id für Passwörter (OWASP-Empfehlung), signierte Session-Cookies
via itsdangerous, gehashte API-Keys (SHA-256, roher Key nur einmal sichtbar).
"""

from __future__ import annotations

import hashlib
import os
import secrets

import argon2
from itsdangerous import URLSafeTimedSerializer

SECRET = os.getenv("LLMWIKI_SECRET", secrets.token_hex(32))
_ph = argon2.PasswordHasher()
_signer = URLSafeTimedSerializer(SECRET, salt="llmwikisession")

SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 Tage


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hpw: str) -> bool:
    try:
        return _ph.verify(hpw, pw)
    except (argon2.exceptions.VerifyMismatchError, argon2.exceptions.VerificationError,
            argon2.exceptions.InvalidHashError):
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


def gen_api_key() -> tuple[str, str]:
    """Liefert (roher Key, Hash)."""
    raw = "llmw_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def verify_api_key(raw: str, stored_hash: str) -> bool:
    if not raw or not stored_hash:
        return False
    return hashlib.sha256(raw.encode()).hexdigest() == stored_hash


_key_cipher = URLSafeTimedSerializer(SECRET, salt="llmwikingapikey")

def encrypt_api_key(raw_key: str) -> str:
    """Verschlüsselt den rohen API-Schlüssel umkehrbar mit dem System-Secret."""
    return _key_cipher.dumps(raw_key)


def decrypt_api_key(encrypted_key: str) -> str | None:
    """Entschlüsselt den verschlüsselten API-Schlüssel."""
    try:
        return _key_cipher.loads(encrypted_key)
    except Exception:
        return None

