# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Quality controls for source freshness, duplicate detection, usage, and readiness."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.config import DATA_DIR, RAW_DIR, wiki_path, _atomic_write

_SOURCE_RE = re.compile(r"\*\*Quelle:\*\*\s*`([^`]+)`", re.IGNORECASE)
_WORD_RE = re.compile(r"[\wäöüß-]{3,}", re.IGNORECASE)
_USAGE_FILE = DATA_DIR / "usage.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes(), usedforsecurity=False).hexdigest()


def _frontmatter(content: str) -> tuple[dict, str] | None:
    match = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*\n", content, re.DOTALL)
    if not match:
        return None
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else {}, content[match.end():]


def stamp_source_fingerprints(content: str) -> str:
    """Store hashes for referenced local raw sources in OKF frontmatter."""
    parsed = _frontmatter(content)
    if not parsed:
        return content
    metadata, body = parsed
    fingerprints: dict[str, str] = {}
    for source in sorted(set(_SOURCE_RE.findall(body))):
        candidate = (RAW_DIR / source).resolve()
        if candidate.is_relative_to(RAW_DIR.resolve()) and candidate.is_file():
            fingerprints[source] = _sha256(candidate)
    if not fingerprints:
        return content
    metadata["source_fingerprints"] = fingerprints
    return f"---\n{yaml.dump(metadata, sort_keys=False, allow_unicode=True)}---\n{body}"


def stale_sources(content: str) -> list[dict[str, str]]:
    """Return source files whose current hash differs from their ingested hash."""
    parsed = _frontmatter(content)
    if not parsed:
        return []
    fingerprints = parsed[0].get("source_fingerprints")
    if not isinstance(fingerprints, dict):
        return []
    stale: list[dict[str, str]] = []
    for source, expected in fingerprints.items():
        candidate = (RAW_DIR / str(source)).resolve()
        if candidate.is_relative_to(RAW_DIR.resolve()) and candidate.is_file():
            current = _sha256(candidate)
            if current != expected:
                stale.append({"source": str(source), "expected_hash": str(expected), "current_hash": current})
    return stale


def _tokens(value: str) -> set[str]:
    return set(_WORD_RE.findall(value.lower()))


def find_similar_pages(wiki: str, title: str, content: str, exclude_slug: str = "") -> list[dict[str, object]]:
    """Find exact and high-overlap pages without an LLM or external service."""
    incoming = _tokens(title + "\n" + re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL))
    if not incoming:
        return []
    matches: list[dict[str, object]] = []
    root = wiki_path(wiki, create=False)
    if not root.exists():
        return matches
    for page in root.glob("*.md"):
        if page.stem in {"index", "log", "ingestlater", exclude_slug}:
            continue
        text = page.read_text(encoding="utf-8", errors="replace")
        parsed = _frontmatter(text)
        existing_title = str(parsed[0].get("title", page.stem)) if parsed else page.stem
        existing = _tokens(existing_title + "\n" + re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL))
        union = incoming | existing
        score = len(incoming & existing) / len(union) if union else 0.0
        if score >= 0.72:
            matches.append({"slug": page.stem, "title": existing_title, "similarity": round(score, 3)})
    return sorted(matches, key=lambda item: float(item["similarity"]), reverse=True)[:5]


def record_usage(wiki: str, slug: str, channel: str) -> None:
    """Record aggregate local page usage without storing request content."""
    try:
        data = json.loads(_USAGE_FILE.read_text(encoding="utf-8")) if _USAGE_FILE.exists() else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    key = f"{wiki}/{slug}"
    entry = data.get(key, {"wiki": wiki, "slug": slug, "reads": 0, "channels": {}})
    entry["reads"] += 1
    entry["channels"][channel] = entry["channels"].get(channel, 0) + 1
    entry["last_read"] = datetime.now(timezone.utc).isoformat()
    data[key] = entry
    _atomic_write(_USAGE_FILE, json.dumps(data, indent=2, ensure_ascii=False))


def usage_summary(wiki: str = "") -> dict[str, object]:
    try:
        entries = json.loads(_USAGE_FILE.read_text(encoding="utf-8")) if _USAGE_FILE.exists() else {}
    except (OSError, json.JSONDecodeError):
        entries = {}
    values = [v for v in entries.values() if not wiki or v.get("wiki") == wiki]
    channels: Counter[str] = Counter()
    for value in values:
        channels.update(value.get("channels", {}))
    return {"pages_tracked": len(values), "total_reads": sum(v.get("reads", 0) for v in values), "channels": dict(channels)}
