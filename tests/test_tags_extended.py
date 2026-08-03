# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from pathlib import Path

from core.config import wiki_path
from services.tags import (
    normalize_tag,
    parse_tags_from_fm,
    extract_hashtags,
    extract_tags,
    auto_generate_tags_for_content,
    build_tag_index,
    get_pages_by_tag,
    TAGS_STORE_FILE,
)
from services.sync import sync_tags_for_wiki
from services.search import local_search
from services.cache import get_cache


def test_normalize_tag():
    assert normalize_tag("  #KI & Machine-Learning  ") == "ki-machine-learning"
    assert normalize_tag("Python 3") == "python-3"


def test_parse_tags_from_fm_yaml_list():
    fm = """
type: Concept
title: "Test Page"
tags:
  - ki
  - python
  - deep-learning
"""
    tags = parse_tags_from_fm(fm)
    assert "ki" in tags
    assert "python" in tags
    assert "deep-learning" in tags


def test_parse_tags_from_fm_inline_list():
    fm = """
type: Concept
tags: [artificial-intelligence, neural-networks]
"""
    tags = parse_tags_from_fm(fm)
    assert tags == ["artificial-intelligence", "neural-networks"]


def test_extract_hashtags():
    content = """---
tags: [main-tag]
---
# Page Title

Here is some text with inline hashtags like #python and #webdev.
```python
# this is code comment, not hashtag
```
`#not_a_tag`
"""
    hashtags = extract_hashtags(content)
    assert "python" in hashtags
    assert "webdev" in hashtags
    assert "this" not in hashtags


def test_auto_generate_tags():
    content = "Das ist ein Artikel über Künstliche Intelligenz, Machine Learning und neuronale Netze."
    tags = auto_generate_tags_for_content(content, title="KI Übersicht")
    assert len(tags) > 0


def test_tag_index_and_json_persistence():
    wiki_dir = wiki_path("test_tags_wiki")

    page1 = wiki_dir / "page1.md"
    page1.write_text("""---
type: Concept
title: "Seite Eins"
tags: [alpha, beta]
---
Inhalt Eins #inline_tag
""", encoding="utf-8")

    get_cache().clear()
    index = build_tag_index("test_tags_wiki", force_rebuild=True)
    assert "alpha" in index
    assert "beta" in index
    assert "inline-tag" in index

    # Verify data/tags.json file creation
    assert TAGS_STORE_FILE.exists()

    # Cleanup
    import shutil
    shutil.rmtree(wiki_dir, ignore_errors=True)


def test_tag_search():
    res = local_search("tag:alpha", wiki="all")
    assert "results" in res
