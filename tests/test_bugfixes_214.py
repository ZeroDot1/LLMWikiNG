# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Tests for Bugfixes & Python 3.14 Compatibility."""

import os
import pytest
from datetime import datetime, timezone
from pathlib import Path

from core.config import WIKIS_ROOT, wiki_path, list_wikis
from core.security import encrypt_api_key, decrypt_api_key, encrypt_mcp_key, decrypt_mcp_key
from core.storage import create_user, delete_user, list_users, create_key, list_keys
from services.search import parse_search_tags, local_search
from services.wiki import read_wiki_file, get_recent_logs
from services.editor import detect_conflict


def test_bug1_search_tags_and_snippet():
    cleaned, tags = parse_search_tags("hello world #tag1 tag:foo test")
    assert cleaned == "hello world test"
    assert "tag1" in tags
    assert "foo" in tags

    # Verify 's' is not stripped
    cleaned_s, _ = parse_search_tags("hello  world  test")
    assert cleaned_s == "hello world test"


def test_bug2_fernet_encryption():
    raw_key = "llmw_test12345"
    enc = encrypt_api_key(raw_key)
    assert enc != raw_key
    dec = decrypt_api_key(enc)
    assert dec == raw_key

    raw_mcp = "mcp_test12345"
    enc_mcp = encrypt_mcp_key(raw_mcp)
    dec_mcp = decrypt_mcp_key(enc_mcp)
    assert dec_mcp == raw_mcp


def test_bug3_log_parsing_with_hyphens(tmp_path):
    wiki_name = "test-log-wiki"
    root = WIKIS_ROOT / wiki_name
    root.mkdir(parents=True, exist_ok=True)
    log_file = root / "log.md"
    log_content = (
        "## 2026-07-30\n"
        "* **Creation**: my-awesome-page.md - Created new page with hyphen\n"
        "* **Update**: test.md\n"
    )
    log_file.write_text(log_content, encoding="utf-8")

    try:
        logs = get_recent_logs(wiki_name)
        assert len(logs) == 2
        assert logs[0]["body"] == "my-awesome-page.md"
        assert logs[0]["details"] == "Created new page with hyphen"
        assert logs[0]["action"] == "Creation"
    finally:
        if log_file.exists():
            log_file.unlink()
        if root.exists():
            root.rmdir()


def test_bug4_path_traversal_prevention():
    res = read_wiki_file("../../etc/passwd", wiki="main")
    assert res is None


def test_bug5_detect_conflict_logic():
    # If client_loaded_hash matches stored_hash or is None, no conflict
    no_conflict = detect_conflict("main", "nonexistent_page_123", "some text")
    assert no_conflict is None

    p = wiki_path("main") / "test_conflict_page.md"
    content = "---\ntitle: Test\ncontent_hash: hash123\n---\nBody text"
    p.write_text(content, encoding="utf-8")
    try:
        conf = detect_conflict("main", "test_conflict_page", "new content", client_loaded_hash="hash_different")
        assert conf is not None
        assert conf["detail"] == "Seite wurde seit dem letzten Laden extern bearbeitet."

        no_conf = detect_conflict("main", "test_conflict_page", "new content", client_loaded_hash="hash123")
        assert no_conf is None
    finally:
        if p.exists():
            p.unlink()


def test_bug6_wiki_path_create_flag():
    p = wiki_path("non_existent_wiki_xyz_123", create=False)
    assert not p.exists()
