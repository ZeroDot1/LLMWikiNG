# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Export helpers for wiki pages.

Extends HTML export with PDF generation via weasyprint.
"""

from __future__ import annotations

from pathlib import Path

from core.config import EXPORT_DIR


async def export_html(wiki: str, slug: str) -> Path:
    """Export a wiki page as HTML file."""
    from services.wiki import get_wiki_page
    from api.routes.pages import templates
    from fastapi import Request

    page_data = get_wiki_page(wiki, slug)
    if not page_data:
        raise FileNotFoundError(f"Page '{slug}' not found in wiki '{wiki}'")

    html = templates.get_template("wiki/page.html").render(
        request=Request(scope={"type": "http"}),
        wiki=wiki,
        page=page_data,
    )

    out = EXPORT_DIR / wiki / f"{slug}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


async def export_pdf(wiki: str, slug: str) -> Path:
    """Export a wiki page as PDF via weasyprint.

    Requires weasyprint: pip install weasyprint>=62.0
    Falls back to HTML-only if weasyprint is not available.
    """
    html_path = await export_html(wiki, slug)
    pdf_path = html_path.with_suffix(".pdf")

    try:
        from weasyprint import HTML
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return pdf_path
    except ImportError:
        raise ImportError(
            "weasyprint is required for PDF export. Install: pip install weasyprint>=62.0"
        )
