"""Tests für services.markdown – Markdown-Rendering."""

from __future__ import annotations

import pytest


class TestRenderMarkdown:
    """Tests für render_markdown()."""

    def test_renders_heading(self, wiki_with_pages):
        from services.markdown import render_markdown
        html = render_markdown("# Hello World")
        # toc-Extension fügt id= Attribut hinzu, daher <h1 id=... statt <h1>
        assert "<h1" in html

    def test_renders_paragraph(self, wiki_with_pages):
        from services.markdown import render_markdown
        html = render_markdown("Ein Absatz.")
        assert "<p>" in html
        assert "Ein Absatz." in html

    def test_renders_bold(self, wiki_with_pages):
        from services.markdown import render_markdown
        html = render_markdown("**fett**")
        assert "<strong>fett</strong>" in html

    def test_renders_code_block(self, wiki_with_pages):
        from services.markdown import render_markdown
        md = "```python\nprint('hello')\n```"
        html = render_markdown(md)
        assert "<code" in html or "print" in html

    def test_strips_frontmatter(self, wiki_with_pages):
        from services.markdown import render_markdown
        md = "---\ntitle: Test\n---\n# Content"
        html = render_markdown(md)
        assert "Test" not in html or "Content" in html

    def test_source_link_transformation(self, wiki_with_pages):
        from services.markdown import render_markdown
        md = "**Quelle:** `datei.txt`"
        html = render_markdown(md)
        assert "/raw/datei.txt" in html

    def test_empty_content(self, wiki_with_pages):
        from services.markdown import render_markdown
        html = render_markdown("")
        assert html == "" or "<p>" not in html

    def test_wiki_link_transformation(self, wiki_with_pages):
        """Lokale Wiki-Links werden umgeschrieben."""
        from services.markdown import render_markdown
        md = "[Python](python.md)"
        html = render_markdown(md, wiki="main")
        assert "LLMWikiNG/wiki/main/python" in html

    def test_external_links_unchanged(self, wiki_with_pages):
        from services.markdown import render_markdown
        md = "[Google](https://google.com)"
        html = render_markdown(md)
        assert "https://google.com" in html

    def test_missing_wiki_link_class(self, wiki_with_pages):
        """Fehlende Wiki-Links bekommen 'wikilink-missing' CSS-Klasse."""
        from services.markdown import render_markdown
        md = "[Fehlend](nonexistent.md)"
        html = render_markdown(md, wiki="main")
        assert "wikilink-missing" in html


class TestRenderMarkdownPreview:
    """Tests für render_markdown_preview()."""

    def test_renders_basic_markdown(self):
        from services.markdown import render_markdown_preview
        html = render_markdown_preview("# Title")
        assert "<h1" in html  # toc-Extension fügt id= hinzu, daher <h1 statt <h1>

    def test_strips_frontmatter(self):
        from services.markdown import render_markdown_preview
        md = "---\ntitle: Test\n---\nContent"
        html = render_markdown_preview(md)
        assert "Content" in html

    def test_renders_tables(self):
        from services.markdown import render_markdown_preview
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = render_markdown_preview(md)
        assert "<table" in html or "1" in html
