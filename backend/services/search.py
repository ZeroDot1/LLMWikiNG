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
    """Fallback Volltextsuche falls qmd nicht verfügbar ist. Unterstützt 'all' für Cross-Wiki-Suche."""
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

    # Zu durchsuchende Wikis bestimmen
    wikis_to_search = []
    if wiki == "all":
        from core.config import list_wikis
        wikis_to_search = [w["name"] for w in list_wikis()]
    else:
        wikis_to_search = [wiki]

    for w in wikis_to_search:
        root = wiki_path(w)
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
                            "wiki": w,
                            "url": f"{BASE_PATH}/wiki/{w}/{f.stem}",
                            "snippet": snippet_of(clean_content, query_lower),
                            "score": score,
                        })
                except Exception:
                    pass

    # Rohdateien (raw/) durchsuchen
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
                            "wiki": "global",
                            "url": f"/raw/{f.name}",
                            "snippet": snippet_of(content, query_lower),
                            "score": score,
                        })
                except Exception:
                    pass

    # Exportierte Dateien (output_docs/) durchsuchen
    if EXPORT_DIR.exists():
        for f in sorted(EXPORT_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep" and is_text_file(f.name):
                # Falls ein spezifisches Wiki gesucht wird, filtern wir Exporte dieses Wikis (Präfix "wiki__")
                if wiki != "all" and not f.name.startswith(f"{wiki}__"):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    score = 0
                    if query_lower in f.name.lower():
                        score += 8
                    if query_lower in content.lower():
                        score += content.lower().count(query_lower)
                    if score > 0:
                        export_wiki = "global"
                        if "__" in f.name:
                            export_wiki = f.name.split("__")[0]
                        results.append({
                            "title": f"Exportiert: {f.name}",
                            "slug": f.stem,
                            "path": f"output_docs/{f.name}",
                            "wiki": export_wiki,
                            "url": f"/export/{f.name}",
                            "snippet": snippet_of(content, query_lower),
                            "score": score,
                        })
                except Exception:
                    pass

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"results": results, "error": None}


def qmd_search(query: str, wiki: str = "main", num_results: int = 10) -> dict:
    """Führt eine qmd BM25-Suche durch und filtert nach Wiki sowie ungültigen Ergebnissen."""
    try:
        result = subprocess.run(
            [QMD_BIN, "search", query, "-n", str(num_results), "--json"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            return local_search(query, wiki)

        output = result.stdout.strip()
        if not output:
            return local_search(query, wiki)

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

                # Bestimmen, zu welchem Wiki dieses Dokument gehört
                item_wiki = "main"
                if "wikis/" in path or "wikis" in path_obj.parts:
                    # Pfad enthält wikis/<wiki>/...
                    match = re.search(r"wikis/([^/]+)/", path)
                    if match:
                        item_wiki = match.group(1)
                elif "wiki/" in path or path_obj.parent.name == "wiki":
                    item_wiki = "main"
                elif "output_docs/" in path or path_obj.parent.name == "output_docs":
                    if "__" in filename:
                        item_wiki = filename.split("__")[0]
                    else:
                        item_wiki = "global"
                elif "raw/" in path or path_obj.parent.name == "raw":
                    item_wiki = "global"

                # Filterung nach ausgewählter Wiki-Einstellung
                if wiki != "all":
                    # Wenn nicht 'all', dann muss das Ergebnis zum ausgewählten Wiki gehören
                    # (Globale Rohdateien zeigen wir immer, da sie als Basis dienen,
                    #  aber Exporte nur, wenn sie zu diesem Wiki gehören)
                    if item_wiki not in (wiki, "global"):
                        continue

                if "wiki/" in path or "wikis/" in path or path_obj.parent.name in ("wiki", "wikis") or any(p in path_obj.parts for p in ("wiki", "wikis")):
                    url = f"{BASE_PATH}/wiki/{item_wiki}/{slug}"
                    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                    title = title_match.group(1) if title_match else slug.replace("-", " ").title()
                    display_path = f"wikis/{item_wiki}/{filename}"
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
                    "wiki": item_wiki,
                    "url": url,
                    "snippet": snippet,
                    "score": item.get("score", 0),
                })

        if not results:
            return local_search(query, wiki)

        return {"results": results, "error": None}

    except (FileNotFoundError, subprocess.SubprocessError):
        return local_search(query, wiki)
    except subprocess.TimeoutExpired:
        return local_search(query, wiki)
    except Exception as e:
        return {"error": str(e)}
