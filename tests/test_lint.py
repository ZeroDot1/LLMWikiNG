"""Tests für services.lint – Wiki-Gesundheitscheck."""

from __future__ import annotations

import pytest


class TestRunLint:
    """Tests für run_lint()."""

    def test_returns_all_keys(self, wiki_with_pages):
        from services.lint import run_lint
        result = run_lint("main")
        expected_keys = {"orphans", "missing", "stale", "missing_raw",
                         "missing_type", "broken_links", "no_tags",
                         "short_pages", "link_suggestions", "issue_count"}
        assert set(result.keys()) == expected_keys

    def test_finds_missing_pages(self, wiki_with_pages):
        """index.md verlinkt 'nonexistent' – sollte als fehlend erkannt werden."""
        from services.lint import run_lint
        result = run_lint("main")
        missing_slugs = [m["slug"] for m in result["missing"]]
        assert "nonexistent" in missing_slugs

    def test_empty_wiki_no_issues(self, tmp_project):
        from services.lint import run_lint
        result = run_lint("main")
        assert result["issue_count"] == 0

    def test_nonexistent_wiki(self, tmp_project):
        from services.lint import run_lint
        result = run_lint("nonexistent")
        assert result["issue_count"] == 0
        assert result["orphans"] == []

    def test_detects_missing_type(self, tmp_project):
        """Seiten ohne type-Feld im Frontmatter."""
        wiki_root = tmp_project / "wikis" / "main"
        (wiki_root / "no-type.md").write_text(
            "# No Type\n\nInhalt ohne Frontmatter.",
            encoding="utf-8",
        )
        from services.lint import run_lint
        result = run_lint("main")
        slugs = [p["slug"] for p in result["missing_type"]]
        assert "no-type" in slugs
