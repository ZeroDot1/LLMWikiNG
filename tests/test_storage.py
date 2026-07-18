"""Tests für core.storage – User und API-Key CRUD."""

from __future__ import annotations

import pytest


class TestUserCRUD:
    """Tests für Benutzer-Operationen."""

    def test_create_user(self, tmp_project):
        from core.storage import create_user
        user = create_user("max", "Passwort123!", role="admin")
        assert user["username"] == "max"
        assert user["role"] == "admin"
        assert user["active"] is True
        assert "id" in user
        assert "password_hash" in user
        assert user["password_hash"] != "Passwort123!"  # Passwort nicht im Klartext

    def test_create_duplicate_user_raises(self, tmp_project):
        from core.storage import create_user
        create_user("max", "Passwort123!")
        with pytest.raises(ValueError, match="existiert bereits"):
            create_user("max", "AnderesPasswort!")

    def test_create_duplicate_case_insensitive(self, tmp_project):
        from core.storage import create_user
        create_user("Max", "Passwort123!")
        with pytest.raises(ValueError):
            create_user("max", "AnderesPasswort!")

    def test_list_users_empty(self, tmp_project):
        from core.storage import list_users
        assert list_users() == []

    def test_list_users(self, tmp_project):
        from core.storage import create_user, list_users
        create_user("alice", "pw1")
        create_user("bob", "pw2")
        users = list_users()
        assert len(users) == 2

    def test_get_user(self, tmp_project):
        from core.storage import create_user, get_user
        user = create_user("max", "pw")
        found = get_user(user["id"])
        assert found is not None
        assert found["username"] == "max"

    def test_get_user_not_found(self, tmp_project):
        from core.storage import get_user
        assert get_user("nonexistent") is None

    def test_get_user_by_name(self, tmp_project):
        from core.storage import create_user, get_user_by_name
        create_user("Max", "pw")
        found = get_user_by_name("max")  # case-insensitive
        assert found is not None

    def test_get_user_by_name_not_found(self, tmp_project):
        from core.storage import get_user_by_name
        assert get_user_by_name("nobody") is None

    def test_update_user(self, tmp_project):
        from core.storage import create_user, update_user
        user = create_user("max", "altes_passwort")
        updated = update_user(user["id"], username="max_neu")
        assert updated is not None
        assert updated["username"] == "max_neu"

    def test_update_user_password(self, tmp_project):
        from core.security import verify_password
        from core.storage import create_user, update_user, get_user
        user = create_user("max", "altes_passwort")
        update_user(user["id"], password="neues_passwort")
        updated = get_user(user["id"])
        assert verify_password("neues_passwort", updated["password_hash"]) is True

    def test_update_user_not_found(self, tmp_project):
        from core.storage import update_user
        result = update_user("nonexistent", username="new")
        assert result is None

    def test_delete_user(self, tmp_project):
        from core.storage import create_user, delete_user, get_user
        user = create_user("max", "pw")
        delete_user(user["id"])
        assert get_user(user["id"]) is None

    def test_delete_nonexistent_user_no_error(self, tmp_project):
        from core.storage import delete_user
        delete_user("nonexistent")  # Should not raise


class TestAPIKeyCRUD:
    """Tests für API-Key-Operationen."""

    def test_create_key(self, tmp_project):
        from core.storage import create_user, create_key
        user = create_user("admin", "pw")
        key_obj, raw = create_key(user["id"], "Test-Key")
        assert "llmw_" in raw
        assert key_obj["name"] == "Test-Key"
        assert key_obj["user_id"] == user["id"]
        assert key_obj["active"] is True

    def test_create_key_with_scopes(self, tmp_project):
        from core.storage import create_user, create_key
        user = create_user("admin", "pw")
        key_obj, _ = create_key(user["id"], "Scoped-Key", scopes=["read"])
        assert key_obj["scopes"] == ["read"]

    def test_create_key_default_scopes(self, tmp_project):
        from core.storage import create_user, create_key
        user = create_user("admin", "pw")
        key_obj, _ = create_key(user["id"], "Default-Key")
        assert key_obj["scopes"] == ["read", "write"]

    def test_create_key_require_password(self, tmp_project):
        from core.storage import create_user, create_key
        user = create_user("admin", "pw")
        key_obj, _ = create_key(user["id"], "Secure-Key", require_password=True)
        assert key_obj["require_password"] is True

    def test_list_keys(self, tmp_project):
        from core.storage import create_user, create_key, list_keys
        user = create_user("admin", "pw")
        create_key(user["id"], "Key1")
        create_key(user["id"], "Key2")
        keys = list_keys()
        assert len(keys) == 2

    def test_delete_key(self, tmp_project):
        from core.storage import create_user, create_key, delete_key, list_keys
        user = create_user("admin", "pw")
        key_obj, _ = create_key(user["id"], "ToDelete")
        delete_key(key_obj["id"])
        assert len(list_keys()) == 0

    def test_get_key_by_hash(self, tmp_project):
        from core.storage import create_user, create_key, get_key_by_hash
        from core.security import gen_api_key
        user = create_user("admin", "pw")
        key_obj, raw = create_key(user["id"], "FindMe")
        found = get_key_by_hash(key_obj["hash"])
        assert found is not None
        assert found["name"] == "FindMe"

    def test_get_key_by_hash_not_found(self, tmp_project):
        from core.storage import get_key_by_hash
        assert get_key_by_hash("nonexistent_hash") is None

    def test_encrypted_key_is_reversible(self, tmp_project):
        from core.security import decrypt_api_key
        from core.storage import create_user, create_key
        user = create_user("admin", "pw")
        key_obj, raw = create_key(user["id"], "EncKey")
        decrypted = decrypt_api_key(key_obj["encrypted_key"])
        assert decrypted == raw
