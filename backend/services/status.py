# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Short-lived snapshots for the expensive status dashboard."""

from __future__ import annotations

import threading
import time

from services.analytics import get_wiki_analytics
from services.lint import run_lint
from services.quality import usage_summary
from services.sync import is_sync_needed
from services.wiki import get_wiki_stats

_TTL_SECONDS = 30
_snapshots: dict[str, tuple[float, dict]] = {}
_lock = threading.RLock()


def get_status_snapshot(wiki: str) -> dict:
    """Return one consistent, short-lived status snapshot per wiki."""
    now = time.monotonic()
    with _lock:
        cached = _snapshots.get(wiki)
        if cached and now - cached[0] < _TTL_SECONDS:
            return cached[1]

    lint = run_lint(wiki)
    try:
        sync_needed = is_sync_needed(wiki)
    except OSError:
        sync_needed = True
    snapshot = {
        "stats": get_wiki_stats(wiki),
        "analytics": get_wiki_analytics(wiki),
        "sync_needed": sync_needed,
        "readiness": {
            "ready": not sync_needed and lint.get("issue_count", 0) == 0,
            "issues": lint.get("issue_count", 0),
            "changed_sources": len(lint.get("changed_sources", [])),
            "usage": usage_summary(wiki),
        },
    }
    with _lock:
        _snapshots[wiki] = (now, snapshot)
    return snapshot


def invalidate_status_snapshot(wiki: str) -> None:
    """Drop a wiki snapshot after a mutation when immediate freshness matters."""
    with _lock:
        _snapshots.pop(wiki, None)
