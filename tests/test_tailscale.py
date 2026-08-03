# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Tests for Tailscale & Funnel Integration.

Tests configuration saving, encryption, status parsing, and API endpoints.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.security import encrypt_tailscale_key, decrypt_tailscale_key, hash_password
from services.tailscale import (
    load_config,
    save_config,
    build_serve_config,
    get_status,
    reveal_auth_key,
    DEFAULTS,
)


def test_tailscale_key_encryption():
    raw_key = "tskey-auth-k1234567890abcdef-123456789"
    encrypted = encrypt_tailscale_key(raw_key)
    assert encrypted != raw_key
    decrypted = decrypt_tailscale_key(encrypted)
    assert decrypted == raw_key


def test_tailscale_config_roundtrip(tmp_path, monkeypatch):
    test_cfg_path = tmp_path / "tailscale.json"
    monkeypatch.setattr("services.tailscale.CONFIG_PATH", test_cfg_path)
    monkeypatch.setattr("services.tailscale.DATA_DIR", tmp_path)

    cfg = load_config()
    assert cfg["hostname"] == "llmwiking"
    assert cfg["funnel_enabled"] is False

    cfg["hostname"] = "my-wiki-node"
    cfg["funnel_enabled"] = True
    save_config(cfg)

    loaded = load_config()
    assert loaded["hostname"] == "my-wiki-node"
    assert loaded["funnel_enabled"] is True


def test_build_serve_config():
    cfg = {
        "funnel_port": 443,
        "app_port": 8080,
        "serve_path": "/",
        "funnel_enabled": True,
    }
    serve_cfg = build_serve_config(cfg)
    assert "TCP" in serve_cfg
    assert "443" in serve_cfg["TCP"]
    assert serve_cfg["AllowFunnel"]["${TS_CERT_DOMAIN}:443"] is True

    custom_domain_cfg = build_serve_config(cfg, cert_domain="node.tailnet.ts.net")
    assert "node.tailnet.ts.net:443" in custom_domain_cfg["Web"]


@pytest.mark.asyncio
async def test_get_status_missing_binary(monkeypatch):
    monkeypatch.setattr("services.tailscale._which_tailscale", lambda: None)
    status = await get_status()
    assert status["available"] is False
    assert status["backend_state"] == "NotInstalled"


@pytest.mark.asyncio
async def test_get_status_mocked(monkeypatch):
    monkeypatch.setattr("services.tailscale._which_tailscale", lambda: "/usr/bin/tailscale")

    mock_status_out = '{"BackendState": "Running", "Self": {"DNSName": "node.tailnet.ts.net.", "TailscaleIPs": ["100.64.0.1"], "Online": true}}'

    async def mock_run(cmd, timeout=60.0):
        if "funnel" in cmd or "serve" in cmd:
            return 0, "{}", ""
        return 0, mock_status_out, ""

    monkeypatch.setattr("services.tailscale._run", mock_run)

    status = await get_status()
    assert status["available"] is True
    assert status["backend_state"] == "Running"
    assert status["dns_name"] == "node.tailnet.ts.net"
    assert status["tailscale_ips"] == ["100.64.0.1"]
    assert status["online"] is True
    assert status["funnel_urls"] == ["https://node.tailnet.ts.net"]


def test_reveal_auth_key(tmp_path, monkeypatch):
    test_cfg_path = tmp_path / "tailscale.json"
    monkeypatch.setattr("services.tailscale.CONFIG_PATH", test_cfg_path)
    monkeypatch.setattr("services.tailscale.DATA_DIR", tmp_path)

    raw_key = "tskey-auth-secret123"
    enc_key = encrypt_tailscale_key(raw_key)

    cfg = load_config()
    cfg["auth_key_encrypted"] = enc_key
    save_config(cfg)

    pw_hash = hash_password("secretpass123")

    # Invalid password
    assert reveal_auth_key("wrongpass", pw_hash) is None

    # Valid password
    revealed = reveal_auth_key("secretpass123", pw_hash)
    assert revealed == raw_key
