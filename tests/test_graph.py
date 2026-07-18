"""Tests für services.graph – Wissensgraph-Daten."""

from __future__ import annotations

import pytest


class TestBuildGraphData:
    """Tests für build_graph_data()."""

    def test_returns_nodes_and_edges(self, wiki_with_pages):
        from services.graph import build_graph_data
        data = build_graph_data("main")
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_nodes_contain_all_pages(self, wiki_with_pages):
        from services.graph import build_graph_data
        data = build_graph_data("main")
        node_ids = [n["id"] for n in data["nodes"]]
        assert "python" in node_ids
        assert "rust" in node_ids

    def test_edges_from_links(self, wiki_with_pages):
        from services.graph import build_graph_data
        data = build_graph_data("main")
        # python.md links to rust.md and vice versa
        edge_pairs = {(e["from"], e["to"]) for e in data["edges"]}
        assert ("python", "rust") in edge_pairs
        assert ("rust", "python") in edge_pairs

    def test_node_structure(self, wiki_with_pages):
        from services.graph import build_graph_data
        data = build_graph_data("main")
        for node in data["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "group" in node
            assert "url" in node

    def test_empty_wiki(self, tmp_project):
        from services.graph import build_graph_data
        data = build_graph_data("main")
        assert data["nodes"] == []
        assert data["edges"] == []


class TestBuildGraphPaginated:
    """Tests für build_graph_data_paginated()."""

    def test_returns_paginated_data(self, wiki_with_pages):
        from services.graph import build_graph_data_paginated
        data = build_graph_data_paginated("main", page=0, page_size=2)
        assert "nodes" in data
        assert "total_nodes" in data
        assert "page" in data
        assert "total_pages" in data

    def test_page_size_limits_nodes(self, wiki_with_pages):
        from services.graph import build_graph_data_paginated
        data = build_graph_data_paginated("main", page=0, page_size=1)
        assert len(data["nodes"]) <= 1

    def test_total_pages_calculation(self, wiki_with_pages):
        from services.graph import build_graph_data_paginated
        full = build_graph_data_paginated("main", page=0, page_size=1000)
        total = full["total_nodes"]
        paginated = build_graph_data_paginated("main", page=0, page_size=2)
        assert paginated["total_pages"] == max(1, (total + 1) // 2)

    def test_page_bounds(self, wiki_with_pages):
        from services.graph import build_graph_data_paginated
        # Page beyond max should clamp to last page
        data = build_graph_data_paginated("main", page=9999, page_size=2)
        assert data["page"] >= 0
