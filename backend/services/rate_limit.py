# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Simple IP-based Rate Limiter for Login/Auth.
"""

from __future__ import annotations

import time
from collections import defaultdict

_failures: dict[str, list[float]] = defaultdict(list)
WINDOW = 300      # 5 Minuten
MAX_ATTEMPTS = 8  # Max. 8 Fehlversuche pro Fenster


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _failures[ip] if now - t < WINDOW]
    _failures[ip] = hits
    return len(hits) >= MAX_ATTEMPTS


def record_failure(ip: str) -> None:
    _failures[ip].append(time.time())


def clear_failures(ip: str) -> None:
    _failures.pop(ip, None)
