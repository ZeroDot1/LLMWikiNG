"""LLMWikiNG – Volltextsuche (qmd BM25 + lokaler Fallback).

Portiert aus llmWiki.py.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from core.config import WIKI_DIR, RAW_DIR, EXPORT_DIR, PROJECT_ROOT, QMD_BIN, BASE_PATH, wiki_path
from services.wiki import is_text_file


def local_search(query: str, wiki: str = "main") -> dict:
    """Fallback Volltextsuche falls qmd nicht verfügbar ist."""
    results: list[dict] = []
    query_lower = query.lower()

    def snippet_of(content: str, q: str) -> str:
        idx = content.lower().find(q)
        start = max(0, idx - 80)
        end = min(len(content), idx + 120)
        snip = content[start:end].replace("\n", " ").strip()
        if start > 0:
            snip = "..." + snip
        if end < len(content):
            snip = snip + "..."
        return snip

    root = wiki_path(wiki)
    if root.exists():
        for f in sorted(root.iterdir()):
            if f.suffix != ".md" or f.stem in ("index", "log", "ingestlater"):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                clean_content = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
                title_match = re.search(r"^#\s+(.+)$", clean_content, re.MULTILINE)
                title = title_match.group(1) if title_match else f.stem.replace("-", " ").title()

                score = 0
                if query_lower in title.lower():
                    score += 10
                if query_lower in clean_content.lower():
                    score += clean_content.lower().count(query_lower)

                if score > 0:
                    results.append({
                        "title": title,
                        "slug": f.stem,
                        "path": f"wiki/{f.name}",
                        "url": f"{BASE_PATH}/wiki/{wiki}/{f.stem}",
                        "snippet": snippet_of(clean_content, query_lower),
                        "score": score,
                    })
            except Exception:
                pass

    if RAW_DIR.exists():
        for f in sorted(RAW_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep" and is_text_file(f.name):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    score = 0
                    if query_lower in f.name.lower():
                        score += 8
                    if query_lower in content.lower():
                        score += content.lower().count(query_lower)
                    if score > 0:
                        results.append({
                            "title": f"Rohquelle: {f.name}",
                            "slug": f.stem,
                            "path": f"raw/{f.name}",
                            "url": f"/raw/{f.name}",
                            "snippet": snippet_of(content, query_lower),
                            "score": score,
                        })
                except Exception:
                    pass

    if EXPORT_DIR.exists():
        for f in sorted(EXPORT_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep" and is_text_file(f.name):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    score = 0
                    if query_lower in f.name.lower():
                        score += 8
                    if query_lower in content.lower():
                        score += content.lower().count(query_lower)
                    if score > 0:
                        results.append({
                            "title": f"Exportiert: {f.name}",
                            "slug": f.stem,
                            "path": f"output_docs/{f.name}",
                            "url": f"/export/{f.name}",
                            "snippet": snippet_of(content, query_lower),
                            "score": score,
                        })
                except Exception:
                    pass

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"results": results, "error": None}


def qmd_search(query: str, num_results: int = 10) -> dict:
    """Führt eine qmd BM25-Suche durch und filtert 404s heraus."""
    try:
        result = subprocess.run(
            [QMD_BIN, "search", query, "-n", str(num_results), "--json"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            return local_search(query)

        output = result.stdout.strip()
        if not output:
            return local_search(query)

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            data = []
            for line in output.split("\n"):
                line = line.strip()
                if line:
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        results: list[dict] = []
        if isinstance(data, dict):
            data = [data]
        for item in data:
            if isinstance(item, dict):
                path = item.get("metadata", {}).get("path", "") or item.get("path", "")
                content = item.get("content", "") or item.get("text", "") or item.get("snippet", "")
                if not path:
                    continue

                path_obj = Path(path)
                filename = path_obj.name
                slug = path_obj.stem

                if "wiki/" in path or path_obj.parent.name == "wiki":
                    url = f"/wiki/{slug}"
                    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                    title = title_match.group(1) if title_match else slug.replace("-", " ").title()
                    display_path = f"wiki/{filename}"
                elif "raw/" in path or path_obj.parent.name == "raw":
                    url = f"/raw/{filename}"
                    title = f"Rohquelle: {filename}"
                    display_path = f"raw/{filename}"
                elif "output_docs/" in path or path_obj.parent.name == "output_docs":
                    url = f"/export/{filename}"
                    title = f"Exportiert: {filename}"
                    display_path = f"output_docs/{filename}"
                else:
                    continue

                snippet = re.sub(r"<[^>]+>", "", content[:300]) if content else ""
                results.append({
                    "title": title,
                    "slug": slug,
                    "path": display_path,
                    "url": url,
                    "snippet": snippet,
                    "score": item.get("score", 0),
                })

        if not results:
            return local_search(query)

        return {"results": results, "error": None}

    except (FileNotFoundError, subprocess.SubprocessError):
        return local_search(query)
    except subprocess.TimeoutExpired:
        return local_search(query)
    except Exception as e:
        return {"error": str(e)}
