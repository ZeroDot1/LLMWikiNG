"""Regression tests for Matrix filtering and result limits."""

import pytest


@pytest.mark.asyncio
async def test_filters_are_applied_before_shard_limit(tmp_path):
    from services.matrix_indexer import MatrixIndexer
    from services.matrix_searcher import MatrixSearcher

    indexer = MatrixIndexer(data_root=tmp_path / "matrix")
    indexer.shards = 1
    await indexer.start()
    try:
        for number in range(15):
            indexer.index_document("main", f"ordinary-{number}", "Needle", "needle", tags="ordinary")
        indexer.index_document("main", "wanted", "Needle", "needle extra words", tags="wanted")
        await indexer.join()
        searcher = MatrixSearcher(data_root=indexer.data_root)
        all_results = await searcher.search(["main"], "needle", limit=20)
        assert len(all_results["results"]) == 16
        filtered = await searcher.search(["main"], "needle", tags=["wanted"])
        assert [item["doc_id"] for item in filtered["results"]] == ["wanted"]
        with pytest.raises(ValueError):
            await searcher.search(["main"], "needle", limit=-1)
    finally:
        await indexer.stop()


def test_unknown_wiki_validation_does_not_create_directory(tmp_project):
    from api.deps import require_wiki
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        require_wiki("missing-wiki")
    assert error.value.status_code == 404
    assert not (tmp_project / "wikis" / "missing-wiki").exists()


@pytest.mark.asyncio
async def test_registry_keeps_same_document_id_in_different_wikis(tmp_path):
    import sqlite3
    from services.matrix_indexer import MatrixIndexer

    indexer = MatrixIndexer(data_root=tmp_path / "matrix")
    await indexer.start()
    try:
        for wiki in ("first", "second"):
            indexer.index_document(wiki, "shared", "Shared", "Content")
        await indexer.join()
        with sqlite3.connect(indexer._registry_path) as conn:
            assert conn.execute("SELECT count(*) FROM doc_registry").fetchone()[0] == 2
        indexer.remove_document("first", "shared")
        await indexer.join()
        with sqlite3.connect(indexer._registry_path) as conn:
            assert conn.execute("SELECT wiki_id FROM doc_registry").fetchall() == [("second",)]
    finally:
        await indexer.stop()


def test_legacy_registry_migration_preserves_existing_rows(tmp_path):
    import sqlite3
    from services.matrix_indexer import MatrixIndexer

    root = tmp_path / "matrix"
    root.mkdir()
    with sqlite3.connect(root / "registry.db") as conn:
        conn.execute("CREATE TABLE doc_registry (doc_id TEXT PRIMARY KEY, wiki_id TEXT NOT NULL, "
                     "md_path TEXT NOT NULL, shard_name TEXT NOT NULL, last_updated TEXT NOT NULL)")
        conn.execute("INSERT INTO doc_registry VALUES ('shared', 'first', 'shared.md', 'first.db', '2026')")
    indexer = MatrixIndexer(data_root=root)
    indexer._init_registry()
    indexer._init_registry()
    with sqlite3.connect(root / "registry.db") as conn:
        conn.execute("INSERT INTO doc_registry VALUES ('shared', 'second', 'shared.md', 'second.db', '2026')")
        assert conn.execute("SELECT wiki_id FROM doc_registry ORDER BY wiki_id").fetchall() == [("first",), ("second",)]
