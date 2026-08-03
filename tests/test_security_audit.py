# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for security audit fixes: paths, timing-safety, rate-limiting, and XSS sanitization."""

import pytest
from core.paths import safe_wiki_root, safe_page_path, UnsafePathError
from core.security import verify_api_key, verify_mcp_key, create_csrf_token, verify_csrf_token
from services.rate_limit import is_rate_limited, record_failure, clear_failures
from services.markdown import sanitize_html


def test_safe_paths():
    root = safe_wiki_root("main")
    assert root.name == "main"
    
    page = safe_page_path("main", "test-concept")
    assert page.name == "test-concept.md"

    with pytest.raises(UnsafePathError):
        safe_page_path("main", "../../../etc/passwd")


def test_timing_safe_keys():
    import hashlib
    raw = "llmw_testkey12345"
    h = hashlib.sha256(raw.encode()).hexdigest()
    
    assert verify_api_key(raw, h) is True
    assert verify_api_key("wrong_key", h) is False
    assert verify_mcp_key(raw, h) is True
    assert verify_mcp_key("wrong_key", h) is False


def test_csrf_tokens():
    token = create_csrf_token("user_123")
    assert verify_csrf_token(token, "user_123") is True
    assert verify_csrf_token(token, "user_456") is False
    assert verify_csrf_token("invalid_token", "user_123") is False


def test_rate_limiting():
    test_ip = "192.168.1.99"
    clear_failures(test_ip)
    assert is_rate_limited(test_ip) is False
    
    for _ in range(8):
        record_failure(test_ip)
        
    assert is_rate_limited(test_ip) is True
    clear_failures(test_ip)
    assert is_rate_limited(test_ip) is False


def test_sanitize_html():
    raw_xss = '<script>alert(1)</script><p>Hello <a href="https://example.com" onclick="alert(1)">World</a></p>'
    clean = sanitize_html(raw_xss)
    assert "<script>" not in clean
    assert "onclick" not in clean
    assert "Hello" in clean
