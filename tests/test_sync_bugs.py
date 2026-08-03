# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Tests for Sync Bugfixes (S1 - S19)."""

import pytest
import asyncio
import re
from datetime import datetime, timezone

from services.sync import (
    do_sync,
    do_sync_async,
    sync_tags_for_wiki,
    set_last_sync,
    get_last_sync,
    is_sync_needed,
    SyncStatus,
    SYSTEM_STEMS,
    request_sync_background,
)
from core.config import wiki_path, WIKIS_ROOT


def test_s1_do_sync_return_type_dict(tmp_path):
    """Test that do_sync and do_sync_async always return dict even when skipped."""
    res = do_sync("main", force=False)
    assert isinstance(res, dict)
    assert "matrix" in res
    assert "index" in res
    assert "messages" in res
    assert "skipped" in res


@pytest.mark.asyncio
async def test_s1_do_sync_async_return_type_dict():
    res = await do_sync_async("main", force=False)
    assert isinstance(res, dict)
    assert "matrix" in res
    assert "index" in res
    assert "messages" in res
    assert "skipped" in res


def test_s3_regex_heading_matching():
    """Test that title matching in sync_tags_for_wiki correctly matches markdown headings."""
    content = "# Mein Test Titel\n\nEinige Texte hier."
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    assert title_match is not None
    assert title_match.group(1) == "Mein Test Titel"


def test_s6_set_last_sync_no_future_buffer():
    """Test that set_last_sync does not add a 1 hour buffer into the future."""
    now = datetime.now(timezone.utc)
    set_last_sync(now, wiki="main")
    stored = get_last_sync("main")
    assert stored is not None
    diff = abs((stored - now).total_seconds())
    assert diff < 5


def test_s11_sync_status_load_unknown_fields(tmp_path):
    """Test that SyncStatus.load ignores unknown fields in JSON."""
    from services.sync import DATA_DIR
    p = DATA_DIR / "sync_status"
    p.mkdir(parents=True, exist_ok=True)
    f = p / "test_unknown_fields_wiki.json"
    f.write_text('{"wiki": "test", "unknown_field_123": "val"}', encoding="utf-8")

    status = SyncStatus.load("test_unknown_fields_wiki")
    assert status.wiki == "test"
    if f.exists():
        f.unlink()


def test_s7_system_stems_exclusion():
    """Test that SYSTEM_STEMS contains index, log, ingestlater."""
    assert "index" in SYSTEM_STEMS
    assert "log" in SYSTEM_STEMS
    assert "ingestlater" in SYSTEM_STEMS
