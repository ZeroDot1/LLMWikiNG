"""Tests für services.wiki – Wiki-Dateisystem-Operationen."""

from __future__ import annotations

import pytest


class TestSlugifyPath:
    """Tests für slugify_path()."""

    def test_simple_name(self):
        from services.wiki import slugify_path
        assert slugify_path("MyPage") == "mypage"

    def test_with_spaces(self):
        from services.wiki import slugify_path
        assert slugify_path("My Page Name") == "my-page-name"

    def test_with_underscores(self):
        from services.wiki import slugify_path
        assert slugify_path("my_page") == "my-page"

    def test_removes_md_extension(self):
        from services.wiki import slugify_path
        assert slugify_path("page.md") == "page"

    def test_backslash_to_slash(self):
        from services.wiki import slugify_path
        assert slugify_path("sub\\page") == "sub/page"

    def test_mixed_case(self):
        from services.wiki import slugify_path
        assert slugify_path("MyPage") == "mypage"


class TestSlugifyGerman:
    """Tests für slugify_german()."""

    def test_umlauts(self):
        from services.wiki import slugify_german
        assert slugify_german("Übergrößen") == "uebergroessen"

    def test_ss(self):
        from services.wiki import slugify_german
        assert slugify_german("Straße") == "strasse"

    def test_special_chars_to_hyphens(self):
        from services.wiki import slugify_german
        assert slugify_german("Hello World!") == "hello-world"

    def test_consecutive_hyphens_collapsed(self):
        from services.wiki import slugify_german
        assert slugify_german("a---b") == "a-b"

    def test_strip_hyphens(self):
        from services.wiki import slugify_german
        assert slugify_german("-test-") == "test"


class TestExtractLinks:
    """Tests für extract_links_from_content()."""

    def test_simple_links(self):
        from services.wiki import extract_links_from_content
        content = "[Seite](./page.md) und [Andere](other.md)"
        links = extract_links_from_content(content)
        assert "page" in links
        assert "other" in links

    def test_ignores_external_links(self):
        from services.wiki import extract_links_from_content
        content = "[Google](https://google.com) und [Local](local.md)"
        links = extract_links_from_content(content)
        assert len(links) == 1
        assert "local" in links

    def test_ignores_anchors(self):
        from services.wiki import extract_links_from_content
        content = "[Link](#section)"
        links = extract_links_from_content(content)
        assert links == []

    def test_ignores_mailto(self):
        from services.wiki import extract_links_from_content
        content = "[Email](mailto:test@test.com)"
        links = extract_links_from_content(content)
        assert links == []

    def test_frontmatter_excluded(self):
        from services.wiki import extract_links_from_content
        content = "---\ntitle: Test\n---\n[Link](./page.md)"
        links = extract_links_from_content(content)
        assert "page" in links

    def test_absolute_paths(self):
        from services.wiki import extract_links_from_content
        content = "[Link](/path/to/page.md)"
        links = extract_links_from_content(content)
        assert "path/to/page" in links

    def test_no_links(self):
        from services.wiki import extract_links_from_content
        content = "Kein Link hier, nur Text."
        links = extract_links_from_content(content)
        assert links == []

    def test_empty_content(self):
        from services.wiki import extract_links_from_content
        links = extract_links_from_content("")
        assert links == []


class TestReadWikiFile:
    """Tests für read_wiki_file()."""

    def test_read_existing_file(self, wiki_with_pages):
        from services.wiki import read_wiki_file
        data = read_wiki_file("python.md", "main")
        assert data is not None
        assert "Python" in data["content"]
        assert data["name"] == "python"
        assert data["filename"] == "python.md"
        assert data["wiki"] == "main"

    def test_read_nonexistent_file(self, wiki_with_pages):
        from services.wiki import read_wiki_file
        assert read_wiki_file("nonexistent.md", "main") is None

    def test_read_auto_adds_md_extension(self, wiki_with_pages):
        from services.wiki import read_wiki_file
        data = read_wiki_file("python", "main")
        assert data is not None

    def test_read_returns_modified_date(self, wiki_with_pages):
        from services.wiki import read_wiki_file
        from datetime import datetime
        data = read_wiki_file("python.md", "main")
        assert isinstance(data["modified"], datetime)


class TestGetAllWikiPages:
    """Tests für get_all_wiki_pages()."""

    def test_lists_pages(self, wiki_with_pages):
        from services.wiki import get_all_wiki_pages
        pages = get_all_wiki_pages("main")
        slugs = [p["slug"] for p in pages]
        assert "python" in slugs
        assert "rust" in slugs
        assert "trail" in slugs

    def test_excludes_system_pages(self, wiki_with_pages):
        from services.wiki import get_all_wiki_pages
        pages = get_all_wiki_pages("main")
        slugs = [p["slug"] for p in pages]
        assert "index" not in slugs
        assert "log" not in slugs
        assert "ingestlater" not in slugs

    def test_page_metadata(self, wiki_with_pages):
        from services.wiki import get_all_wiki_pages
        pages = get_all_wiki_pages("main")
        python_page = next(p for p in pages if p["slug"] == "python")
        assert python_page["title"] == "Python Programmiersprache"
        assert python_page["type"] == "concept"
        assert python_page["wiki"] == "main"

    def test_empty_wiki(self, tmp_project):
        from services.wiki import get_all_wiki_pages
        pages = get_all_wiki_pages("main")
        assert pages == []


class TestIsTextFile:
    """Tests für is_text_file()."""

    @pytest.mark.parametrize("filename", [
        "test.md", "test.txt", "test.json", "test.sh", "test.yaml",
        "test.yml", "test.py", "test.html", "test.css", "test.ini",
        "test.conf", "noext",
    ])
    def test_text_files(self, filename):
        from services.wiki import is_text_file
        assert is_text_file(filename) is True

    @pytest.mark.parametrize("filename", [
        "test.pdf", "test.exe", "test.png", "test.jpg", "test.zip",
    ])
    def test_non_text_files(self, filename):
        from services.wiki import is_text_file
        assert is_text_file(filename) is False


class TestGetPendingFiles:
    """Tests für get_pending_files()."""

    def test_returns_pending_files(self, raw_files):
        from services.wiki import get_pending_files
        files = get_pending_files()
        names = [f["name"] for f in files]
        assert "test_doc.txt" in names
        assert "another_file.md" in names

    def test_empty_when_no_raw(self, tmp_project):
        from services.wiki import get_pending_files
        assert get_pending_files() == []

    def test_file_metadata(self, raw_files):
        from services.wiki import get_pending_files
        files = get_pending_files()
        for f in files:
            assert "name" in f
            assert "size_formatted" in f
            assert "mtime_formatted" in f


class TestGetRecentLogs:
    """Tests für get_recent_logs()."""

    def test_parses_log_entries(self, wiki_with_pages):
        from services.wiki import get_recent_logs
        logs = get_recent_logs("main", limit=10)
        assert len(logs) > 0
        # get_recent_logs iteriert rückwärts durch die Sektionen;
        # der erste Eintrag ist der älteste (2025-01-10), nicht der neueste.
        dates = [log["date"] for log in logs]
        assert "2025-01-15" in dates
        assert "2025-01-10" in dates

    def test_respects_limit(self, wiki_with_pages):
        from services.wiki import get_recent_logs
        logs = get_recent_logs("main", limit=1)
        assert len(logs) <= 1

    def test_empty_when_no_log(self, tmp_project):
        from services.wiki import get_recent_logs
        assert get_recent_logs("main") == []


class TestGetWikiStats:
    """Tests für get_wiki_stats()."""

    def test_returns_stats(self, wiki_with_pages):
        from services.wiki import get_wiki_stats
        stats = get_wiki_stats("main")
        assert stats["page_count"] >= 3  # python, rust, trail
        assert stats["word_count"] > 0

    def test_empty_wiki(self, tmp_project):
        from services.wiki import get_wiki_stats
        stats = get_wiki_stats("main")
        assert stats["page_count"] == 0
        assert stats["word_count"] == 0
