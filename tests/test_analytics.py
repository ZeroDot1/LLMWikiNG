"""Tests für services.analytics – Wiki-Analytik."""

from __future__ import annotations

import pytest


class TestGetWikiAnalytics:
    """Tests für get_wiki_analytics()."""

    def test_returns_all_keys(self, wiki_with_pages):
        from services.analytics import get_wiki_analytics
        result = get_wiki_analytics("main")
        expected_keys = {"hubs", "dead_ends", "top_tags", "bridges"}
        assert set(result.keys()) == expected_keys

    def test_finds_hubs(self, wiki_with_pages):
        """Seiten die von vielen anderen verlinkt werden."""
        from services.analytics import get_wiki_analytics
        result = get_wiki_analytics("main")
        # Both python and rust link to each other
        hub_slugs = [h["slug"] for h in result["hubs"]]
        assert len(hub_slugs) > 0

    def test_finds_dead_ends(self, wiki_with_pages):
        """Seiten die keine outgoing Links haben."""
        from services.analytics import get_wiki_analytics
        result = get_wiki_analytics("main")
        # simple.md has no outgoing links (system pages like log.md are excluded)
        dead_slugs = [d["slug"] for d in result["dead_ends"]]
        assert "simple" in dead_slugs

    def test_finds_tags(self, wiki_with_pages):
        from services.analytics import get_wiki_analytics
        result = get_wiki_analytics("main")
        assert len(result["top_tags"]) > 0
        tag_names = [t[0] for t in result["top_tags"]]
        assert "programmierung" in tag_names

    def test_empty_wiki(self, tmp_project):
        from services.analytics import get_wiki_analytics
        result = get_wiki_analytics("main")
        assert result["hubs"] == []
        assert result["dead_ends"] == []
        assert result["top_tags"] == []
        assert result["bridges"] == []
