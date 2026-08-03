# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests für Per-User MCP-Keys, Tool-Berechtigungen und Zwangspaarung."""

import pytest
from pathlib import Path
import hashlib
from core.storage import create_mcp_key, list_mcp_keys, delete_mcp_key, create_key, create_user


class TestPerUserMcpKeys:
    """Testet die Verwaltung, Zwangspaarung und Tool-Berechtigungsfilterung für Per-User MCP-Keys."""

    def test_mcp_key_creation_and_storage(self, tmp_path_factory):
        """Testet die Erstellung und das Auflisten von MCP-Keys."""
        import uuid
        uname = f"mcp_user_{uuid.uuid4().hex[:8]}"
        user = create_user(uname, "pass123", role="admin")
        key_obj, raw_key = create_mcp_key(user["id"], "Test Agent Key", allowed_tools=["okf_list_wikis", "okf_search"])

        assert key_obj["name"] == "Test Agent Key"
        assert key_obj["user_id"] == user["id"]
        assert key_obj["allowed_tools"] == ["okf_list_wikis", "okf_search"]
        assert raw_key.startswith("mcp_")

        all_keys = list_mcp_keys()
        found = next((k for k in all_keys if k["id"] == key_obj["id"]), None)
        assert found is not None
        assert found["name"] == "Test Agent Key"

        delete_mcp_key(key_obj["id"])
        all_keys_after = list_mcp_keys()
        assert not any(k["id"] == key_obj["id"] for k in all_keys_after)

    def test_mcp_key_user_mismatch_rejected(self, client, sample_api_keys):
        """Sollte 403 Forbidden liefern, wenn MCP-Key und API-Key zu verschiedenen Benutzern gehören."""
        # User A API key
        tmp_path, key_a_info = sample_api_keys
        
        # User B anlegen und MCP Key für User B erstellen
        user_b = create_user("user_b_mcp", "password123", role="editor")
        mcp_key_b_obj, raw_mcp_key_b = create_mcp_key(user_b["id"], "User B MCP Key")

        # Request mit User B MCP Key + User A API Key -> Mismatch
        resp = client.get(
            "/LLMWikiNG/mcp/sse",
            headers={
                "X-MCP-Key": raw_mcp_key_b,
                "X-API-Key": key_a_info["raw_key"]
            }
        )
        assert resp.status_code == 403
        assert "gehoeren nicht demselben Benutzer" in resp.json()["detail"]

    def test_mcp_key_user_match_accepted(self, client, sample_api_keys):
        """Sollte zugelassen werden (Stream startet), wenn MCP-Key und API-Key demselben Benutzer gehören."""
        tmp_path, key_a_info = sample_api_keys
        mcp_key_a_obj, raw_mcp_key_a = create_mcp_key(key_a_info["admin"]["id"], "User A MCP Key")

        import threading
        result = {}

        def do_req():
            try:
                with client.stream(
                    "GET",
                    "/LLMWikiNG/mcp/sse",
                    headers={
                        "X-MCP-Key": raw_mcp_a_key if 'raw_mcp_a_key' in locals() else raw_mcp_key_a,
                        "X-API-Key": key_a_info["raw_key"],
                    },
                ) as resp:
                    result["status"] = resp.status_code
            except Exception as e:
                result["error"] = repr(e)

        t = threading.Thread(target=do_req, daemon=True)
        t.start()
        t.join(timeout=3)
        if t.is_alive():
            # Stream hat gestartet (kein 401/403)
            assert True
        else:
            assert result.get("status") not in (401, 403)

    def test_mcp_tool_permission_filtering(self):
        """Testet die _require_tool Berechtigungsprüfung."""
        from api.routes.mcp import _check_tool_permission, mcp_allowed_tools_ctx

        # Fall 1: Keine Einschränkung (ContextVar ist leer = alle erlaubt)
        token = mcp_allowed_tools_ctx.set([])
        try:
            assert _check_tool_permission("okf_write_concept") is None
        finally:
            mcp_allowed_tools_ctx.reset(token)

        # Fall 2: Nur okf_list_wikis erlaubt
        token = mcp_allowed_tools_ctx.set(["okf_list_wikis"])
        try:
            assert _check_tool_permission("okf_list_wikis") is None
            err = _check_tool_permission("okf_write_concept")
            assert err is not None
            assert "nicht erlaubt" in err
        finally:
            mcp_allowed_tools_ctx.reset(token)

    def test_mcp_key_update(self, client):
        """Testet das Aktualisieren von Name, User und Tool-Berechtigungen eines MCP-Keys via REST & Web Route."""
        from core.storage import create_mcp_key, list_mcp_keys, update_mcp_key, create_user
        import uuid

        admin_user = create_user(f"admin_up_{uuid.uuid4().hex[:6]}", "pass123", role="admin")
        key_obj, _ = create_mcp_key(admin_user["id"], "Old Key Name", allowed_tools=["okf_list_wikis"])
        
        # 1. Direct storage update
        updated = update_mcp_key(key_obj["id"], name="New Key Name", allowed_tools=["okf_search", "okf_graph"])
        assert updated is not None
        assert updated["name"] == "New Key Name"
        assert set(updated["allowed_tools"]) == {"okf_search", "okf_graph"}

        # 2. REST API PUT update
        from core.storage import create_key
        _, admin_api_raw = create_key(admin_user["id"], "Admin API Key Test")
        resp = client.put(
            f"/LLMWikiNG/api/v1/mcp-keys/{key_obj['id']}",
            headers={"X-API-Key": admin_api_raw},
            json={"name": "API Updated Name", "tool_groups": ["wiki_read"]}
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["mcp_key"]["name"] == "API Updated Name"
        assert "okf_read_concept" in resp.json()["mcp_key"]["allowed_tools"]

