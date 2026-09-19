# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests for local knowledge quality controls."""

from __future__ import annotations


def test_source_change_is_detected_and_usage_is_aggregated(tmp_path, monkeypatch):
    import services.quality as quality

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    source = raw_dir / "article.md"
    source.write_text("first revision", encoding="utf-8")
    monkeypatch.setattr(quality, "RAW_DIR", raw_dir)
    monkeypatch.setattr(quality, "_USAGE_FILE", tmp_path / "usage.json")

    stamped = quality.stamp_source_fingerprints(
        "---\ntype: Reference\ntitle: Article\n---\n**Quelle:** `article.md`\n"
    )
    assert "source_fingerprints:" in stamped
    assert quality.stale_sources(stamped) == []

    source.write_text("second revision", encoding="utf-8")
    assert quality.stale_sources(stamped)[0]["source"] == "article.md"

    quality.record_usage("main", "article", "api")
    quality.record_usage("main", "article", "mcp")
    assert quality.usage_summary("main")["total_reads"] == 2


def test_duplicate_page_detection(tmp_project):
    from core.config import wiki_path
    from services.quality import find_similar_pages

    root = wiki_path("main")
    (root / "existing.md").write_text(
        "---\ntype: Concept\ntitle: Search Index\n---\n# Search Index\n\nMatrix search index stores documents.",
        encoding="utf-8",
    )
    matches = find_similar_pages("main", "Search Index", "Matrix search index stores documents.")
    assert matches and matches[0]["slug"] == "existing"
