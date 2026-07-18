"""Tests für services.editor – OKF-Frontmatter."""

from __future__ import annotations

import pytest


class TestEnsureOwfFrontmatter:
    """Tests für ensure_okf_frontmatter()."""

    def test_adds_frontmatter_when_missing(self):
        from services.editor import ensure_okf_frontmatter
        content = "# My Page\n\nInhalt hier."
        result = ensure_okf_frontmatter(content, title="My Page")
        assert result.startswith("---\n")
        assert "type:" in result
        assert "My Page" in result

    def test_keeps_existing_frontmatter_with_type(self):
        from services.editor import ensure_okf_frontmatter
        content = "---\ntype: Concept\ntitle: \"Existing\"\n---\n\nContent"
        result = ensure_okf_frontmatter(content)
        assert result == content  # Should be unchanged

    def test_adds_type_to_existing_frontmatter_without_type(self):
        from services.editor import ensure_okf_frontmatter
        content = "---\ntitle: \"No Type\"\n---\n\nContent"
        result = ensure_okf_frontmatter(content)
        # Frontmatter ohne type wird komplett ersetzt durch neues OKF-Frontmatter
        assert "type: Concept" in result
        # Der ursprüngliche Titel wird durch den Standard ersetzt
        assert "---" in result

    def test_empty_content(self):
        from services.editor import ensure_okf_frontmatter
        result = ensure_okf_frontmatter("", title="Empty")
        assert "---" in result
        assert "type:" in result

    def test_default_title_when_none(self):
        from services.editor import ensure_okf_frontmatter
        result = ensure_okf_frontmatter("Content", title=None)
        assert "Neue Seite" in result

    def test_includes_timestamp(self):
        from services.editor import ensure_okf_frontmatter
        from datetime import date
        result = ensure_okf_frontmatter("Content")
        today = date.today().isoformat()
        assert today in result

    def test_includes_required_fields(self):
        from services.editor import ensure_okf_frontmatter
        result = ensure_okf_frontmatter("Content")
        assert "tags:" in result
        assert "description:" in result
        assert "resource:" in result
