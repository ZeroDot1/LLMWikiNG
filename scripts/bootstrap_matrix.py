#!/usr/bin/env python3
# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Projekt Matrix: Bootstrap / Vollständiger Index-Aufbau.

Baut den persistenten Volltextindex (SQLite-Shards unter data/matrix/)
für alle Wikis oder ein einzelnes Wiki neu auf. Die Markdown-Dateien
bleiben Quelle der Wahrheit.

Nutzung:
    python scripts/bootstrap_matrix.py [--wiki <slug>]
"""
import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from core.config import MATRIX_DATA_ROOT, WIKIS_ROOT, wiki_path, list_wikis  # noqa: E402
from services.matrix_indexer import MatrixIndexer  # noqa: E402

log = logging.getLogger("llmwiking.matrix.bootstrap")
SYSTEM_STEMS = {"index", "log", "ingestlater"}


def _extract_document(md_file: Path, wiki: str):
    """Extrahiert Titel, Tags, doc_id und md_path aus einer Markdown-Datei."""
    content = md_file.read_text(encoding="utf-8", errors="replace")
    body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else md_file.stem.title()

    rel = md_file.relative_to(wiki_path(wiki))
    doc_id = str(rel.with_suffix("")).replace("\\", "/")
    md_path = str(rel).replace("\\", "/")

    fm = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    tags = ""
    if fm:
        from services.tags import parse_tags_from_fm

        tags = ",".join(parse_tags_from_fm(fm.group(1)))

    return doc_id, title, content, tags, md_path


def _collect_files(wiki: str | None) -> list[tuple[str, Path]]:
    """Sammelt alle zu indexierenden Markdown-Dateien."""
    files: list[tuple[str, Path]] = []
    if wiki:
        candidates = [{"slug": wiki}]
    else:
        candidates = list_wikis() or [{"slug": "main"}]
    for w in candidates:
        slug = w.get("slug", "main")
        root = WIKIS_ROOT / slug
        if not root.exists():
            log.warning("Wiki '%s' nicht gefunden, übersprungen", slug)
            continue
        for md_file in sorted(root.rglob("*.md")):
            rel = md_file.relative_to(root)
            if rel.parts and rel.parts[0].startswith("."):
                continue
            if md_file.stem in SYSTEM_STEMS:
                continue
            files.append((slug, md_file))
    return files


async def bootstrap(wiki: str | None = None) -> int:
    indexer = MatrixIndexer(MATRIX_DATA_ROOT, WIKIS_ROOT)
    await indexer.start()
    indexed = 0
    errors = 0
    try:
        files = _collect_files(wiki)
        total = len(files)
        log.info("Matrix-Bootstrap: %d Datei(en) zu indexieren", total)
        for i, (slug, md_file) in enumerate(files, start=1):
            try:
                doc_id, title, content, tags, md_path = _extract_document(md_file, slug)
                indexer.index_document(
                    wiki_id=slug,
                    doc_id=doc_id,
                    title=title,
                    content=content,
                    tags=tags,
                    md_path=md_path,
                )
                indexed += 1
            except Exception as e:
                errors += 1
                log.error("Fehler bei '%s': %s", md_file, e)
            if i % 50 == 0 or i == total:
                print(f"  → {i}/{total} ({slug})", flush=True)
        await indexer._write_queue.join()
        stats = indexer.get_stats()
        size_mb = stats.get("total_size_bytes", 0) / (1024 * 1024)
        print(f"Fertig: {indexed} Dokumente indexiert, {errors} Fehler.")
        print(f"Shards: {stats['shard_count']}, Größe: {size_mb:.1f} MB")
    finally:
        await indexer.stop()
    return 0 if errors == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Matrix-Index (persistente Volltextsuche) aufbauen")
    parser.add_argument("--wiki", default=None, help="Nur dieses Wiki indexieren (Standard: alle)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        raise SystemExit(asyncio.run(bootstrap(args.wiki)))
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
