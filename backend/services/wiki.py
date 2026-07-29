"""LLMWikiNG – Wiki-Dateisystem-Operationen und Helfer (Multi-Wiki-fähig).

Portiert aus llmWiki.py. Alle Funktionen akzeptieren einen optionalen `wiki`-Namen
(Default "main") und operieren auf dem entsprechenden Verzeichnis wiki_path(wiki).
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from core.config import WIKI_DIR, RAW_DIR, EXPORT_DIR, PROJECT_ROOT, wiki_path
from services.cache import get_cache

SYSTEM_PAGES = ("index", "log", "ingestlater")

CHUNK_THRESHOLD = 6000
CHUNK_MIN = 2000


def chunk_content(
    text: str,
    title: str,
    max_chars: int = 8000,
    min_chunk: int = 2000,
) -> list[tuple[str, str]]:
    """Zerlegt großen Text in mehrere Blöcke.

    Teilt an Absatzgrenzen (doppelter Zeilenumbruch), damit jeder Block
    separat ingestiert werden kann.

    Args:
        text:      Der vollständige Text.
        title:     Basis-Titel für die Benennung.
        max_chars: Maximale Zeichenzahl pro Chunk.
        min_chunk: Mindestgröße eines Chunks (sonst wird er mit dem vorigen
                   zusammengelegt).

    Returns:
        Liste von (Titel, Inhalt)-Tupeln.
    """
    if len(text) <= max_chars:
        return [(title, text)]

    paragraphs = re.split(r"\n\n+", text)
    chunks: list[tuple[str, str]] = []
    current_lines: list[str] = []
    current_len = 0
    chunk_num = 1

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_len = len(para) + 2  # +2 für die zwei Newlines

        if current_len + para_len > max_chars and current_len >= min_chunk:
            chunk_title = f"{title} – Teil {chunk_num}" if len(chunks) > 0 or chunk_num > 1 else title
            chunks.append((chunk_title, "\n\n".join(current_lines)))
            current_lines = [para]
            current_len = para_len
            chunk_num += 1
        else:
            current_lines.append(para)
            current_len += para_len

    if current_lines:
        chunk_title = f"{title} – Teil {chunk_num}" if (chunk_num > 1 or len(chunks) > 0) else title
        chunks.append((chunk_title, "\n\n".join(current_lines)))

    return chunks


def suggest_tags_from_content(
    content: str,
    wiki: str = "main",
    max_tags: int = 5,
) -> list[str]:
    """Schlägt Tags basierend auf Inhaltsanalyse vor.

    Sucht nach häufigen Wörtern und gleicht sie mit vorhandenen Tags ab.

    Args:
        content: Der Textinhalt.
        wiki:    Wiki-Slug.
        max_tags: Maximale Anzahl Vorschläge.

    Returns:
        Liste von Tag-Vorschlägen.
    """
    from services.tags import get_tag_cloud

    tag_cloud = get_tag_cloud(wiki)
    if not tag_cloud:
        return []

    words = re.findall(r"[a-zA-ZäöüßÄÖÜ][a-zA-ZäöüßÄÖÜ-]{2,}", content.lower())
    word_counts: dict[str, int] = {}
    for w in words:
        word_counts[w] = word_counts.get(w, 0) + 1

    scored: list[tuple[int, str]] = []
    for entry in tag_cloud:
        tag = entry["tag"]
        if tag.lower() in word_counts:
            scored.append((word_counts[tag.lower()], tag))

    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored[:max_tags]]


def clean_ingest_content(text: str, title: str = "") -> str:
    """Bereinigt rohen Ingest-Text (Web-Scrapes, Paste, Blog-Exports) für
    menschenlesbare Wiki-Seiten.

    Entfernt typische Scrape-Artefakte und repariert häufige Markdown-Fehler:

    * Navigation/Menü-Reste (``Direkt zum Hauptbereich``, ``Suchen``,
      ``Mehr…``, Blog-Menüs, "Dieses Blog durchsuchen")
    * Kaputte URLs durch Zeilenumbrüche in Markdown-Links
      (``https://der-\\nhoerold.blogspot.com/`` → ``https://der-hoerold.blogspot.com/``)
    * Doppelte Überschriften (wenn die erste H1 == Seitentitel)
    * Überflüssige Leerzeilen-Häufungen

    Args:
        text:  Der rohe Quelltext (Markdown oder Plaintext).
        title: Optionaler Seitentitel, dessen Duplikat-Überschrift entfernt wird.

    Returns:
        Bereinigter Markdown-Text.
    """
    if not text:
        return text

    lines = text.splitlines()
    cleaned: list[str] = []
    skipped_menu = False

    for line in lines:
        stripped = line.strip()

        if stripped in (
            "Direkt zum Hauptbereich",
            "Suchen",
            "Mehr…",
            "Mehr...",
            "Dieses Blog durchsuchen",
            "Startseite",
            "Impressum, Haftungsauschluss und Datenschutz",
        ):
            continue
        if stripped.startswith("Suchen") or stripped.startswith("Mehr"):
            continue
        if re.match(r"^[\*\-]\s*\[(?:Startseite|Neuer Blog|Hörspiele|Hörbücher|Podcasts|Impressum)[^\]]*\]\(https?://", stripped):
            continue
        if re.match(r"^#{1,4}\s*Dieses Blog durchsuchen\s*$", stripped):
            continue
        if re.match(r"^#\s*\[\s*[^]]*\]\s*\(https?://", stripped):
            continue

        cleaned.append(line)

    text = "\n".join(cleaned)

    # --- Kaputte URLs durch Zeilenumbrüche reparieren ----------------------
    # Markdown-Links: [text](url\nmit umbruch) -> [text](urlmitumbruch)
    text = re.sub(
        r"\]\((\s*https?://[^\n]*?)\n\s*([^\n]*?)\)",
        lambda m: f"]({m.group(1).strip()}{m.group(2).strip()})",
        text,
    )
    # Nackte URLs mit Umbruch: https://der-\nhoerold... -> https://der-hoerold...
    text = re.sub(
        r"(https?://[^\s)\]]*?)\n\s*([^\s)\]]+)",
        lambda m: f"{m.group(1).rstrip('-_')}{m.group(2)}",
        text,
    )

    if title:
        title_norm = title.strip().lower()
        def _h1_match(l: str) -> bool:
            m = re.match(r"^#\s+(.+)$", l.strip())
            return bool(m) and m.group(1).strip().lower() == title_norm

        first_h1_idx = None
        for i, l in enumerate(text.splitlines()):
            if _h1_match(l):
                first_h1_idx = i
                break
        if first_h1_idx is not None:
            # Entferne diese eine Zeile (der Seitentitel wird ohnehin als H1 gesetzt)
            text_lines = text.splitlines()
            del text_lines[first_h1_idx]
            text = "\n".join(text_lines)

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text.endswith("\n"):
        text += "\n"

    return text


async def run_ingest_async(
    filepath: str | Path,
    *,
    title: str | None = None,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Führt `wiki.sh ingest` asynchron aus, ohne den Event-Loop zu blockieren.

    Der blockierende ``subprocess.run``-Aufruf wird via ``asyncio.to_thread``
    in einen Worker-Thread ausgelagert, sodass die asyncio-Event-Loop während
    des (potenziell langsamen) Ingest-Prozesses frei bleibt und weitere
    Requests bedienen kann.

    Args:
        filepath: Pfad zur zu ingestierenden Datei.
        title:    Optionale Überschrift (``--title``).
        timeout:  Timeout in Sekunden für den Subprozess.
        env:      Optionale Umgebungsvariablen (kopiert + ergänzt).

    Returns:
        Das ``subprocess.CompletedProcess``-Ergebnis.
    """
    path = Path(filepath).resolve()
    base_proj = PROJECT_ROOT.resolve()
    if not str(path).startswith(str(base_proj)):
        raise ValueError("Ingest-Pfad außerhalb des Projekt-Verzeichnisses verboten")
    if not path.is_file():
        raise FileNotFoundError(f"Ingest-Datei nicht gefunden: {path}")

    cmd = ["./wiki.sh", "ingest", str(path)]
    if title:
        safe_title = re.sub(r"[\x00-\x1f\x7f]", "", title)[:200]
        cmd += ["--title", safe_title]
    run_env = env if env is not None else os.environ.copy()
    run_env["PROJECT_ROOT"] = str(PROJECT_ROOT)
    return await asyncio.to_thread(
        subprocess.run,
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
        env=run_env,
    )


async def run_sync_async(wiki: str, force: bool = False) -> dict:
    """Führt den Sync asynchron aus, ohne den Event-Loop zu blockieren.

    Nutzt :func:`services.sync.do_sync_async`. Gibt das Ergebnis-Dict von
    ``do_sync`` zurück (``{"qmd": bool, "index": bool, "messages": [...]}``).
    """
    from services.sync import do_sync_async

    return await do_sync_async(wiki, force=force)


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
    raw_links = re.findall(r"\[.*?\]\((/.*?\.md|\./.*?\.md|[^\[\]()\s]+\.md|[^#:\s\)\[\]()]+)\)", body)

    slugs: list[str] = []
    for link in raw_links:
        if link.startswith(("http://", "https://", "mailto:", "#")):
            continue
        clean = re.sub(r"^\.+/", "", link)
        clean = clean.lstrip("/")
        clean = re.sub(r"\.md$", "", clean)
        slug = clean.lower().replace(" ", "-").replace("_", "-")
        slugs.append(slug)
    return slugs


def get_all_wiki_pages(wiki: str = "main") -> list[dict]:
    """Listet alle Markdown-Seiten im Wiki auf (ohne System-Seiten).

    Ergebnis wird in-memory gecached und bei Datei-Änderungen automatisch
    invalidiert (mtime-basierter Fingerabdruck des Wiki-Verzeichnisses).
    """
    root = wiki_path(wiki)
    cache = get_cache()
    cache_key = f"pages:{wiki}"

    cached = cache.get(cache_key, root)
    if cached is not None:
        return cached

    result = _get_all_wiki_pages_uncached(wiki)
    cache.set(cache_key, result, root)
    return result


def _get_all_wiki_pages_uncached(wiki: str = "main") -> list[dict]:
    """Interne Funktion – liest alle Wiki-Seiten ohne Cache."""
    root = wiki_path(wiki)
    pages: list[dict] = []
    if not root.exists():
        return pages
    for f in sorted(root.rglob("*.md")):
        if f.stem in SYSTEM_PAGES:
            continue
        rel_path = f.relative_to(root)
        if any(p.startswith(".") for p in rel_path.parts):
            continue
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
            content_no_fm = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL).strip()
            desc_match = re.search(r"^([^.]+\.)", content_no_fm.replace("#", "", 1).strip(), re.MULTILINE)
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
    """Ermittelt Wiki-Statistiken isoliert pro Wiki."""
    page_count = 0
    word_count = 0
    raw_count = 0
    export_count = 0

    root = wiki_path(wiki)
    if root.exists():
        for f in root.rglob("*.md"):
            if f.stem in SYSTEM_PAGES:
                continue
            if any(p.startswith(".") for p in f.relative_to(root).parts):
                continue
            page_count += 1
            word_count += len(f.read_text(encoding="utf-8", errors="replace").split())

    wiki_raw_dir = RAW_DIR / wiki if (RAW_DIR / wiki).exists() else RAW_DIR
    if wiki_raw_dir.exists():
        raw_count = sum(1 for _ in wiki_raw_dir.rglob("*") if _.is_file() and not _.name.startswith("."))

    wiki_export_dir = EXPORT_DIR / wiki if (EXPORT_DIR / wiki).exists() else EXPORT_DIR
    if wiki_export_dir.exists():
        export_count = sum(1 for _ in wiki_export_dir.rglob("*") if _.is_file() and not _.name.startswith("."))

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
                        "size": stat.st_size,
                        "size_formatted": size_formatted,
                        "mtime_formatted": mtime_formatted,
                    })
    return files


def save_to_ingestlater(item_type: str, title: str, content: str, wiki: str = "main") -> None:
    """Speichert eine URL oder einen Text in der Datei <wiki>/ingestlater.md."""
    from services.sync import request_sync_background

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
    request_sync_background(wiki)


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
