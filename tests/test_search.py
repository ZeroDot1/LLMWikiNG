"""Tests für services.search – Lokale Volltextsuche."""

from __future__ import annotations

import pytest


class TestLocalSearch:
    """Tests für local_search()."""

    def test_finds_page_by_content(self, wiki_with_pages):
        from services.search import local_search
        result = local_search("interpreted", "main")
        assert len(result["results"]) > 0
        assert result["results"][0]["slug"] == "python"

    def test_finds_page_by_title(self, wiki_with_pages):
        from services.search import local_search
        result = local_search("Rust Programmiersprache", "main")
        assert len(result["results"]) > 0

    def test_no_results(self, wiki_with_pages):
        from services.search import local_search
        result = local_search("xyznonexistent", "main")
        assert result["results"] == []
        assert result["error"] is None

    def test_empty_query(self, wiki_with_pages):
        from services.search import local_search
        result = local_search("", "main")
        # Ein leerer String wird in jedem Inhalt gefunden ("in" Operator
        # liefert True für "" in "beliebiger Text"), daher Treffer.
        # Wichtig: Es soll nicht abstürzen.
        assert isinstance(result["results"], list)

    def test_case_insensitive(self, wiki_with_pages):
        from services.search import local_search
        result = local_search("PYTHON", "main")
        assert len(result["results"]) > 0

    def test_results_sorted_by_score(self, wiki_with_pages):
        from services.search import local_search
        result = local_search("python", "main")
        if len(result["results"]) > 1:
            for i in range(len(result["results"]) - 1):
                assert result["results"][i]["score"] >= result["results"][i + 1]["score"]

    def test_result_has_required_fields(self, wiki_with_pages):
        from services.search import local_search
        result = local_search("python", "main")
        assert len(result["results"]) > 0
        r = result["results"][0]
        for field in ("title", "slug", "path", "wiki", "url", "snippet", "score"):
            assert field in r

    def test_search_includes_raw_files(self, raw_files):
        from services.search import local_search
        result = local_search("Testdokument", "main")
        # Raw files should be searched
        assert len(result["results"]) > 0

    def test_title_match_gets_higher_score(self, wiki_with_pages):
        """Seiten mit Treffer im Titel sollten höhere Scores haben."""
        from services.search import local_search
        result = local_search("Programmiersprache", "main")
        # Both python and rust have this in their title
        assert len(result["results"]) >= 2
        for r in result["results"]:
            assert r["score"] >= 10  # Title bonus is 10
