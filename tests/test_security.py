"""Tests für core.security – Passwort-Hashing, Sessions, API-Keys."""

from __future__ import annotations

import hashlib
import secrets

import pytest


class TestPasswordHashing:
    """Tests für Argon2id-Passwort-Hashing."""

    def test_hash_password_returns_string(self):
        from core.security import hash_password
        h = hash_password("meinpasswort")
        assert isinstance(h, str)
        assert len(h) > 20

    def test_verify_correct_password(self):
        from core.security import hash_password, verify_password
        pw = "SicheresPasswort123!"
        h = hash_password(pw)
        assert verify_password(pw, h) is True

    def test_verify_wrong_password(self):
        from core.security import hash_password, verify_password
        h = hash_password("richtigesPasswort")
        assert verify_password("falschesPasswort", h) is False

    def test_hash_different_each_time(self):
        """Argon2 Should produces different hashes for the same password (random salt)."""
        from core.security import hash_password
        h1 = hash_password("test123")
        h2 = hash_password("test123")
        # Hashes should differ (random salt)
        assert h1 != h2

    def test_verify_empty_password(self):
        from core.security import hash_password, verify_password
        h = hash_password("")
        assert verify_password("", h) is True
        assert verify_password("nichtleer", h) is False

    def test_verify_invalid_hash(self):
        from core.security import verify_password
        assert verify_password("test", "ungültiger-hash") is False

    def test_verify_none_like_hash(self):
        from core.security import verify_password
        assert verify_password("test", "") is False


class TestRehash:
    """Tests für needs_rehash."""

    def test_needs_rehash_returns_bool(self):
        from core.security import hash_password, needs_rehash
        h = hash_password("test")
        result = needs_rehash(h)
        assert isinstance(result, bool)

    def test_needs_rehash_invalid_returns_false(self):
        from core.security import needs_rehash
        assert needs_rehash("ungültig") is False


class TestSessions:
    """Tests für signierte Session-Cookies."""

    def test_create_and_read_session(self):
        from core.security import create_session, read_session
        token = create_session("user123")
        assert isinstance(token, str)
        uid = read_session(token)
        assert uid == "user123"

    def test_read_session_none_token(self):
        from core.security import read_session
        assert read_session(None) is None

    def test_read_session_empty_token(self):
        from core.security import read_session
        assert read_session("") is None

    def test_read_session_invalid_token(self):
        from core.security import read_session
        assert read_session("total_bullshit_token") is None

    def test_session_different_users(self):
        from core.security import create_session, read_session
        t1 = create_session("alice")
        t2 = create_session("bob")
        assert read_session(t1) == "alice"
        assert read_session(t2) == "bob"
        assert t1 != t2


class TestAPIKeys:
    """Tests für API-Key-Generierung und -Verifikation."""

    def test_gen_api_key_format(self):
        from core.security import gen_api_key
        raw, h = gen_api_key()
        assert raw.startswith("llmw_")
        assert len(raw) > 10

    def test_gen_api_key_hash_is_sha256(self):
        from core.security import gen_api_key
        raw, h = gen_api_key()
        expected_hash = hashlib.sha256(raw.encode()).hexdigest()
        assert h == expected_hash

    def test_verify_api_key_correct(self):
        from core.security import gen_api_key, verify_api_key
        raw, h = gen_api_key()
        assert verify_api_key(raw, h) is True

    def test_verify_api_key_wrong(self):
        from core.security import gen_api_key, verify_api_key
        raw, h = gen_api_key()
        assert verify_api_key("falscher_key", h) is False

    def test_verify_api_key_empty(self):
        from core.security import verify_api_key
        assert verify_api_key("", "hash") is False
        assert verify_api_key("key", "") is False
        assert verify_api_key("", "") is False

    def test_gen_unique_keys(self):
        """Jeder Aufruf sollte einen einzigartigen Key erzeugen."""
        from core.security import gen_api_key
        keys = set()
        for _ in range(20):
            raw, _ = gen_api_key()
            keys.add(raw)
        assert len(keys) == 20


class TestAPIKeyEncryption:
    """Tests für reversible API-Key-Verschlüsselung."""

    def test_encrypt_decrypt_roundtrip(self):
        from core.security import encrypt_api_key, decrypt_api_key
        raw = "llmw_test_key_12345"
        encrypted = encrypt_api_key(raw)
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == raw

    def test_decrypt_invalid_token(self):
        from core.security import decrypt_api_key
        assert decrypt_api_key("ungültiger_token") is None

    def test_different_keys_produce_different_ciphertext(self):
        from core.security import encrypt_api_key
        e1 = encrypt_api_key("key1")
        e2 = encrypt_api_key("key2")
        assert e1 != e2
