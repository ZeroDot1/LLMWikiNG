"""LLMWikiNG – Wiki-Dateisystem-Operationen und Helfer (Multi-Wiki-fähig).

Portiert aus llmWiki.py. Alle Funktionen akzeptieren einen optionalen `wiki`-Namen
(Default "main") und operieren auf dem entsprechenden Verzeichnis wiki_path(wiki).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from core.config import WIKI_DIR, RAW_DIR, PROJECT_ROOT, wiki_path

SYSTEM_PAGES = ("index", "log", "ingestlater")


def slugify_path(value: str) -> str:
    """Normalisiert einen Dateinamen/Slug zu Kleinbuchstaben mit Bindestrichen."""
    slug = value.lower().replace("\\", "/").replace(" ", "-").replace("_", "-")
    slug = re.sub(r"\.md$", "", slug)
    return slug


def slugify_german(value: str) -> str:
    """Deutsche Slugification für Redirects (ä->ae, ü->ue, ß->ss)."""
    slug = value.lower()
    slug = slug.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    slug = re.sub(r"[^a-z0-9]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def extract_links_from_content(content: str) -> list[str]:
    """Extrahiert alle lokalen Wiki-Verknüpfungen aus dem Markdown-Body."""
    body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
    raw_links = re.findall(r"\[.*?\]\((/.*?\.md|\./.*?\.md|.*?\.md|[^#:\s\)]+)\)", body)

    slugs: list[str] = []
    for link in raw_links:
        if link.startswith(("http://", "https://", "mailto:", "#")):
            continue
        # Führende Punkte und Slashes entfernen (z.B. ./ oder ../)
        clean = re.sub(r"^\.+/", "", link)
        clean = clean.lstrip("/")
        clean = re.sub(r"\.md$", "", clean)
        slug = clean.lower().replace(" ", "-").replace("_", "-")
        slugs.append(slug)
    return slugs


def get_all_wiki_pages(wiki: str = "main") -> list[dict]:
    """Listet alle Markdown-Seiten im Wiki auf (ohne System-Seiten)."""
    root = wiki_path(wiki)
    pages: list[dict] = []
    if not root.exists():
        return pages
    for f in sorted(root.rglob("*.md")):
        if f.stem in SYSTEM_PAGES:
            continue
        rel_path = f.relative_to(root)
        slug = str(rel_path.with_suffix("")).lower().replace("\\", "/").replace(" ", "-").replace("_", "-")

        content = f.read_text(encoding="utf-8", errors="replace")
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else f.stem.replace("-", " ").title()

        desc = ""
        page_type = "concept"

        fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            try:
                fm = _yaml_minimal(fm_match.group(1)) or {}
                if isinstance(fm, dict):
                    page_type = str(fm.get("type", "concept")).lower()
                    desc = fm.get("description", "")
                    title = fm.get("title", title)
            except Exception:
                pass

        if not desc:
            desc_match = re.search(r"^([^.]+\.)", content.replace("#", "", 1).strip(), re.MULTILINE)
            desc = desc_match.group(1)[:120] if desc_match else title

        pages.append({
            "slug": slug,
            "name": slug,
            "title": title,
            "desc": desc,
            "filename": f.name,
            "path": str(f.relative_to(PROJECT_ROOT)),
            "type": page_type,
            "wiki": wiki,
        })
    return pages


def _yaml_minimal(text: str) -> dict:
    """Sehr einfaches YAML-Frontmatter-Parsing (nur flache Key: Value)."""
    import yaml

    try:
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_wiki_stats(wiki: str = "main") -> dict:
    """Ermittelt Wiki-Statistiken."""
    page_count = 0
    word_count = 0
    raw_count = 0
    export_count = 0

    root = wiki_path(wiki)
    if root.exists():
        for f in root.rglob("*.md"):
            if f.stem not in SYSTEM_PAGES:
                page_count += 1
                word_count += len(f.read_text(encoding="utf-8", errors="replace").split())

    if RAW_DIR.exists():
        raw_count = sum(1 for _ in RAW_DIR.iterdir() if _.is_file())

    export_dir = PROJECT_ROOT / "output_docs"
    if export_dir.exists():
        export_count = sum(1 for _ in export_dir.iterdir() if _.is_file())

    return {
        "page_count": page_count,
        "word_count": word_count,
        "raw_count": raw_count,
        "export_count": export_count,
    }


def read_wiki_file(filename: str, wiki: str = "main") -> dict | None:
    """Liest eine Wiki-Datei und gibt Inhalt + Metadaten zurück."""
    root = wiki_path(wiki)
    filepath = root / filename
    if not filepath.exists():
        filepath_md = root / f"{filename}.md"
        if filepath_md.exists():
            filepath = filepath_md
        else:
            return None
    if not filepath.is_file():
        return None
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        return {
            "content": content,
            "path": str(filepath.relative_to(PROJECT_ROOT)),
            "name": filepath.stem,
            "filename": filepath.name,
            "modified": datetime.fromtimestamp(filepath.stat().st_mtime),
            "wiki": wiki,
        }
    except Exception:
        return None


def is_text_file(filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    return suffix in (
        ".md", ".txt", ".json", ".sh", ".yaml", ".yml", ".py", ".html", ".css", ".ini", ".conf", ""
    )


def find_wiki_slug_for_raw(filename: str, wiki: str = "main") -> str | None:
    root = wiki_path(wiki)
    if not root.exists():
        return None
    for f in root.iterdir():
        if f.suffix == ".md":
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("source:"):
                            src = line.split(":", 1)[1].strip().strip('"').strip("'")
                            if src == filename:
                                return f.stem
            except Exception:
                pass
    return None


def get_pending_files() -> list[dict]:
    """Gibt eine Liste aller un-ingestierten Dateien in raw/ zurück."""
    files: list[dict] = []
    if RAW_DIR.exists():
        for f in sorted(RAW_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep":
                wiki_slug = find_wiki_slug_for_raw(f.name)
                if not wiki_slug:
                    stat = f.stat()
                    size_kb = stat.st_size / 1024
                    size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
                    mtime_formatted = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    files.append({
                        "name": f.name,
                        "size_formatted": size_formatted,
                        "mtime_formatted": mtime_formatted,
                    })
    return files


def save_to_ingestlater(item_type: str, title: str, content: str, wiki: str = "main") -> None:
    """Speichert eine URL oder einen Text in der Datei <wiki>/ingestlater.md."""
    from services.sync import do_sync

    file_path = wiki_path(wiki) / "ingestlater.md"

    if not file_path.exists():
        template = (
            "# Ingest Later\n\n"
            "> Liste von URLs und Text-Schnipseln, die später ins Wiki eingepflegt werden sollen.\n\n"
            "## 🔗 Gemerkte URLs\n\n"
            "## 📝 Gemerkte Texte und Notizen\n\n"
        )
        file_path.write_text(template, encoding="utf-8")

    lines = file_path.read_text(encoding="utf-8").splitlines()

    new_lines: list[str] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if item_type == "url":
        inserted = False
        for line in lines:
            new_lines.append(line)
            if "## 🔗 Gemerkte URLs" in line and not inserted:
                desc = title if title else content
                new_lines.append(f"- [ ] [{desc}]({content}) (Hinzugefügt: {timestamp})")
                inserted = True
        if not inserted:
            new_lines.append("## 🔗 Gemerkte URLs")
            new_lines.append(f"- [ ] [{title or content}]({content}) (Hinzugefügt: {timestamp})")

    elif item_type == "text":
        inserted = False
        for line in lines:
            new_lines.append(line)
            if "## 📝 Gemerkte Texte und Notizen" in line and not inserted:
                new_lines.append(f"### {title} (Hinzugefügt: {timestamp})\n")
                new_lines.append(f"{content}\n")
                inserted = True
        if not inserted:
            new_lines.append("## 📝 Gemerkte Texte und Notizen")
            new_lines.append(f"### {title} (Hinzugefügt: {timestamp})\n")
            new_lines.append(f"{content}\n")

    file_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    do_sync(wiki)


def get_recent_logs(wiki: str = "main", limit: int = 5) -> list[dict]:
    """Liest die neuesten Logbuch-Einträge aus <wiki>/log.md."""
    log_path = wiki_path(wiki) / "log.md"
    logs: list[dict] = []
    if log_path.exists():
        try:
            content = log_path.read_text(encoding="utf-8")
            sections = re.split(r"^##\s+(\d{4}-\d{2}-\d{2})", content, flags=re.MULTILINE)
            if len(sections) > 1:
                for i in range(len(sections) - 2, 0, -2):
                    date_str = sections[i].strip()
                    section_body = sections[i + 1].strip()
                    items = re.findall(
                        r"^\*\s+\*\*([^*]+)\*\*:\s*([^-\n]+)(?:-\s*([^\n]+))?",
                        section_body,
                        re.MULTILINE,
                    )
                    for action, title, details in items:
                        logs.append({
                            "date": date_str,
                            "action": action.strip(),
                            "details": details.strip() if details else "",
                            "body": title.strip(),
                        })
                        if len(logs) >= limit:
                            return logs
        except Exception:
            pass
    return logs


def get_wiki_trails(wiki: str = "main") -> list[dict]:
    """Sucht nach Seiten vom Typ 'trail' und parst ihren Pfad."""
    trails: list[dict] = []
    wiki_pages = get_all_wiki_pages(wiki)
    root = wiki_path(wiki)
    for page in wiki_pages:
        filepath = root / f"{page['slug']}.md"
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                if fm_match:
                    is_trail = False
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("type:") and "trail" in line.split(":", 1)[1].lower():
                            is_trail = True

                    if is_trail:
                        path_section = ""
                        m = re.search(r"^##\s+Path\s*$", content, re.MULTILINE)
                        if m:
                            start = m.end()
                            nxt = re.search(r"^##\s+", content[start:], re.MULTILINE)
                            path_section = content[start:start + nxt.start()] if nxt else content[start:]

                        matches = re.findall(
                            r"\[(.*?)\]\((/.*?\.md|\./.*?\.md|.*?\.md|[^#:\s\)]+)\)",
                            path_section,
                        )
                        path_slugs: list[tuple[str, str]] = []
                        for display, target in matches:
                            t_slug = target.lstrip("/").replace(".md", "").lower().replace(" ", "-").replace("_", "-")
                            path_slugs.append((display.strip(), t_slug))

                        trails.append({
                            "slug": page["slug"],
                            "title": page["title"],
                            "path": path_slugs,
                        })
            except Exception:
                pass
    return trails
