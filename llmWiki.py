#!/usr/bin/env python3
"""LLMWikiNG – Lokaler Wiki-Webserver (Flask + qmd + Markdown)
by ZeroDot1 | Karpathy LLM-Wiki-Pattern | Dark Wikipedia-Theme"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, date, timedelta

import flask
from flask import Flask, render_template, request, abort, redirect, url_for
import markdown
from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor

# ═══════════════════════════════════════════════════════════════════════════════
# Konfiguration
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parent
WIKI_DIR = PROJECT_ROOT / "wiki"
RAW_DIR = PROJECT_ROOT / "raw"
EXPORT_DIR = PROJECT_ROOT / "output_docs"
LANG_DIR = PROJECT_ROOT / "lang"
COLLECTION_NAME = "my_wiki"
QMD_BIN = "qmd"
APP_NAME = "LLMWikiNG"
APP_EDITION = "by ZeroDot1"
APP_VERSION = "1.1.0"
DEFAULT_LANG = "de"  # Kann via config.json oder --lang CLI überschrieben werden
CONFIG_FILE = PROJECT_ROOT / "config.json"

# ─── App-Konfiguration laden ────────────────────────────────────────────────

def load_app_config():
    """Lädt die globale App-Konfiguration aus config.json.

    Enthält neben SMTP-Einstellungen auch die Standard-Sprache u. a.
    Gibt ein Dict mit Standardwerten zurück, falls die Datei fehlt.
    """
    default_config = {
        "language": "de",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_pass": "",
        "use_tls": True,
        "recipients": "",
    }
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for k, v in default_config.items():
                data.setdefault(k, v)
            return data
        except (json.JSONDecodeError, Exception):
            return default_config
    return default_config


# ─── Übersetzungssystem (Mehrsprachigkeit) ──────────────────────────────────

_translations_cache = {}  # {lang_code: dict}

def get_available_languages():
    """Ermittelt verfügbare Sprachen aus dem lang/-Ordner."""
    langs = {}
    if LANG_DIR.exists():
        for f in sorted(LANG_DIR.iterdir()):
            if f.suffix == ".json":
                code = f.stem
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    name = data.get("_meta", {}).get("name", code)
                    langs[code] = name
                except (json.JSONDecodeError, Exception):
                    langs[code] = code
    if not langs:
        langs[DEFAULT_LANG] = "Deutsch"
    return langs

def load_translations(lang_code):
    """Lädt die Übersetzungsdatei für eine Sprache und gibt ein dict zurück."""
    if lang_code in _translations_cache:
        return _translations_cache[lang_code]
    fallback = {}
    filepath = LANG_DIR / f"{lang_code}.json"
    if filepath.exists():
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            _translations_cache[lang_code] = data
            return data
        except (json.JSONDecodeError, Exception):
            pass
    # Fallback auf Deutsch
    if lang_code != DEFAULT_LANG:
        return load_translations(DEFAULT_LANG)
    return {}

class Translator:
    """Einfacher Übersetzer, der mit Punkt-Notation auf das JSON zugreift.
    Usage in Templates: {{ _('sidebar.home') }} oder {{ _('index.welcome_heading') }}
    """
    def __init__(self, lang_code):
        self.lang_code = lang_code
        self.data = load_translations(lang_code)

    def get(self, key, default=None):
        """Holt einen Wert per Punkt-Notation (z.B. 'sidebar.home')."""
        if not key:
            return default or key
        parts = key.split(".")
        current = self.data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return default or key
            else:
                return default or key
        if isinstance(current, str):
            return current
        return default or key

    def __call__(self, key, **kwargs):
        """Ruft einen übersetzten String ab und führt optional .format() aus."""
        value = self.get(key)
        if kwargs and isinstance(value, str):
            try:
                return value.format(**kwargs)
            except (KeyError, ValueError):
                return value
        return value

# Markdown-Extensions
MD_EXTENSIONS = [
    "extra",            # Tables, Code-Blöcke, Fußnoten, Abkürzungen
    "codehilite",       # Syntax-Highlighting
    "sane_lists",       # Saubere Listen
    "smarty",           # Typografische Anführungszeichen
    "toc",              # Inhaltsverzeichnis
    "wikilinks",        # [[Seitenname]]-Links (wird unten überschrieben)
    "fenced_code",      # ```code``` Blöcke
]

# ═══════════════════════════════════════════════════════════════════════════════
# Custom Markdown Extension: Wikilinks mit Seitenerkennung
# ═══════════════════════════════════════════════════════════════════════════════

class LLMWikiLinkExtension(Extension):
    """Wandelt [[Seitenname]] in Links um.
    Existiert die Seite, wird sie blau/gruen verlinkt.
    Existiert sie nicht, wird sie rot markiert (missing)."""

    def extendMarkdown(self, md):
        md.preprocessors.register(WikiLinkPreprocessor(md), "llm_wikilinks", 175)

class WikiLinkPreprocessor(Preprocessor):
    def __init__(self, md):
        super().__init__(md)
        self.page_cache = self._build_page_cache()

    def _build_page_cache(self):
        """Baut einen Set aller existierenden Wiki-Seiten (ohne .md) auf."""
        cache = set()
        if WIKI_DIR.exists():
            for f in WIKI_DIR.iterdir():
                if f.suffix == ".md":
                    cache.add(f.stem)  # z.B. "llm-wiki" aus "llm-wiki.md"
        return cache

    def run(self, lines):
        new_lines = []
        for line in lines:
            # [[Seitenname]] -> <a href="/wiki/seitenname" class="wikilink">
            # [[Seitenname|Anzeigetext]] -> mit alternativem Text
            def replace_link(match):
                full = match.group(1)
                if "|" in full:
                    target, display = full.split("|", 1)
                else:
                    target = display = full
                target = target.strip()
                display = display.strip()
                slug = target.lower().replace(" ", "-").replace("_", "-")
                # Entferne .md falls vorhanden
                slug = re.sub(r'\.md$', '', slug)
                exists = slug in self.page_cache
                css_class = "wikilink" if exists else "wikilink-missing"
                return f'<a href="/wiki/{slug}" class="{css_class}">{display}</a>'

            line = re.sub(r'\[\[([^\]]+)\]\]', replace_link, line)
            new_lines.append(line)
        return new_lines


# ═══════════════════════════════════════════════════════════════════════════════
# Flask-App
# ═══════════════════════════════════════════════════════════════════════════════

app = Flask(APP_NAME,
            template_folder=str(PROJECT_ROOT / "templates"),
            static_folder=str(PROJECT_ROOT / "static"),
            static_url_path="/static")

# Templates immer neu laden (auch im Produktionsmodus)
app.config["TEMPLATES_AUTO_RELOAD"] = True


# ─── Hilfsfunktionen ────────────────────────────────────────────────────────

def get_all_wiki_pages():
    """Listet alle Markdown-Seiten im Wiki auf (ohne index.md, log.md)."""
    pages = []
    if not WIKI_DIR.exists():
        return pages
    for f in sorted(WIKI_DIR.iterdir()):
        if f.suffix != ".md":
            continue
        if f.name in ("index.md", "log.md"):
            continue
        # Erste Überschrift als Titel
        content = f.read_text(encoding="utf-8", errors="replace")
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = title_match.group(1) if title_match else f.stem.replace("-", " ").title()
        
        # Ersten Satz als Beschreibung
        desc_match = re.search(r'^([^.]+\.)', content.replace("#", "", 1).strip(), re.MULTILINE)
        desc = desc_match.group(1)[:120] if desc_match else title
        
        # YAML-Frontmatter parsen für 'type'
        page_type = "page"
        fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).split("\n"):
                if line.startswith("type:"):
                    page_type = line.split(":", 1)[1].strip().lower().strip('"\'')
                    break
                    
        pages.append({
            "slug": f.stem,
            "name": f.stem,
            "title": title,
            "desc": desc,
            "filename": f.name,
            "path": str(f.relative_to(PROJECT_ROOT)),
            "type": page_type
        })
    return pages


def get_wiki_stats():
    """Ermittelt Wiki-Statistiken."""
    page_count = 0
    word_count = 0
    raw_count = 0
    export_count = 0

    if WIKI_DIR.exists():
        for f in WIKI_DIR.iterdir():
            if f.suffix == ".md" and f.name not in ("index.md", "log.md"):
                page_count += 1
                word_count += len(f.read_text(encoding="utf-8", errors="replace").split())

    if RAW_DIR.exists():
        raw_count = sum(1 for _ in RAW_DIR.iterdir() if _.is_file())

    if EXPORT_DIR.exists():
        export_count = sum(1 for _ in EXPORT_DIR.iterdir() if _.is_file())

    return {
        "page_count": page_count,
        "word_count": word_count,
        "raw_count": raw_count,
        "export_count": export_count,
    }


def render_markdown(text, page_name=None):
    """Wandelt Markdown in HTML um, mit angepassten Wikilinks."""
    # YAML-Frontmatter entfernen
    text = re.sub(r'^---.*?---\s*', '', text, flags=re.DOTALL)

    # Quelle klickbar machen: **Quelle:** `filename` -> **Quelle:** [filename](/raw/filename)
    text = re.sub(r'\*\*Quelle:\*\*\s*`([^`]+)`', r'**Quelle:** [\1](/raw/\1)', text)

    # Wikilinks-Erweiterung mit aktuellem Seiten-Cache
    ext = LLMWikiLinkExtension()

    html = markdown.markdown(
        text,
        extensions=MD_EXTENSIONS + [ext],
        extension_configs={
            "toc": {
                "marker": "[TOC]",
                "permalink": True,
            },
        },
    )

    # Cleanup: Leere <p>-Tags
    html = re.sub(r'<p>\s*</p>', '', html)

    return html


def local_search(query):
    """Fallback Volltextsuche falls qmd nicht verfügbar ist oder einen Fehler wirft."""
    results = []
    query_lower = query.lower()

    # 1. Wiki-Seiten durchsuchen
    if WIKI_DIR.exists():
        for f in sorted(WIKI_DIR.iterdir()):
            if f.suffix != ".md" or f.name in ("index.md", "log.md"):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                # YAML-Frontmatter entfernen
                clean_content = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL)
                
                title_match = re.search(r'^#\s+(.+)$', clean_content, re.MULTILINE)
                title = title_match.group(1) if title_match else f.stem.replace("-", " ").title()
                
                score = 0
                if query_lower in title.lower():
                    score += 10
                if query_lower in clean_content.lower():
                    score += clean_content.lower().count(query_lower)
                    
                if score > 0:
                    idx = clean_content.lower().find(query_lower)
                    start = max(0, idx - 80)
                    end = min(len(clean_content), idx + 120)
                    snippet = clean_content[start:end].replace("\n", " ").strip()
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(clean_content):
                        snippet = snippet + "..."
                    
                    results.append({
                        "title": title,
                        "slug": f.stem,
                        "path": f"wiki/{f.name}",
                        "url": f"/wiki/{f.stem}",
                        "snippet": snippet,
                        "score": score
                    })
            except Exception:
                pass

    # 2. Rohquellen durchsuchen
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
                        idx = content.lower().find(query_lower)
                        start = max(0, idx - 80)
                        end = min(len(content), idx + 120)
                        snippet = content[start:end].replace("\n", " ").strip()
                        if start > 0:
                            snippet = "..." + snippet
                        if end < len(content):
                            snippet = snippet + "..."
                        
                        results.append({
                            "title": f"Rohquelle: {f.name}",
                            "slug": f.stem,
                            "path": f"raw/{f.name}",
                            "url": f"/raw/{f.name}",
                            "snippet": snippet,
                            "score": score
                        })
                except Exception:
                    pass

    # 3. Exportierte Dokumente durchsuchen
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
                        idx = content.lower().find(query_lower)
                        start = max(0, idx - 80)
                        end = min(len(content), idx + 120)
                        snippet = content[start:end].replace("\n", " ").strip()
                        if start > 0:
                            snippet = "..." + snippet
                        if end < len(content):
                            snippet = snippet + "..."
                        
                        results.append({
                            "title": f"Exportiert: {f.name}",
                            "slug": f.stem,
                            "path": f"output_docs/{f.name}",
                            "url": f"/export/{f.name}",
                            "snippet": snippet,
                            "score": score
                        })
                except Exception:
                    pass

    # Nach Score absteigend sortieren
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"results": results, "error": None}


def qmd_search(query, num_results=10):
    """Führt eine schnelle qmd BM25-Suche durch und filtert 404s heraus. Fallback auf lokale Suche bei Fehlern."""
    try:
        # qmd search ist deutlich schneller als qmd query (BM25 vs hybrid Vektor + Reranking)
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

        # qmd gibt entweder JSON-Array oder JSONL aus
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

        results = []
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
                
                # Prüfen, in welchem Ordner sich die Datei befindet, um 404s zu verhindern
                if "wiki/" in path or path_obj.parent.name == "wiki":
                    # Wiki-Seite
                    url = f"/wiki/{slug}"
                    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                    title = title_match.group(1) if title_match else slug.replace("-", " ").title()
                    display_path = f"wiki/{filename}"
                elif "raw/" in path or path_obj.parent.name == "raw":
                    # Rohquelle
                    url = f"/raw/{filename}"
                    title = f"Rohquelle: {filename}"
                    display_path = f"raw/{filename}"
                elif "output_docs/" in path or path_obj.parent.name == "output_docs":
                    # Exportiertes Dokument
                    url = f"/export/{filename}"
                    title = f"Exportiert: {filename}"
                    display_path = f"output_docs/{filename}"
                else:
                    # Andere Ordner ignorieren, um Systemdateien zu schützen
                    continue

                snippet = re.sub(r'<[^>]+>', '', content[:300]) if content else ""

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


def read_wiki_file(filename):
    """Liest eine Wiki-Datei und gibt Inhalt + Metadaten zurück."""
    filepath = WIKI_DIR / filename
    if not filepath.exists():
        # Auch ohne .md probieren
        filepath_md = WIKI_DIR / f"{filename}.md"
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
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Context Processor: Globale Variablen für ALLE Templates
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# Sync-Status (wann wurde das letzte Mal qmd embed + reindex ausgeführt?)
# ═══════════════════════════════════════════════════════════════════════════════

LAST_SYNC_TIME = None  # Zeitstempel des letzten Syncs

def is_sync_needed():
    """Prüft, ob seit dem letzten Sync neue oder geänderte Dateien im Wiki sind."""
    global LAST_SYNC_TIME
    if LAST_SYNC_TIME is None:
        return True
    if not WIKI_DIR.exists():
        return False
    for f in WIKI_DIR.iterdir():
        if f.suffix == ".md" and f.name not in ("index.md", "log.md"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime > LAST_SYNC_TIME:
                return True
    # Auch raw/ prüfen
    if RAW_DIR.exists():
        for f in RAW_DIR.iterdir():
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime > LAST_SYNC_TIME:
                    return True
    return False


def run_qmd_embed():
    """Führt qmd embed aus. Gibt (success, message) zurück."""
    try:
        result = subprocess.run(
            [QMD_BIN, "embed"],
            capture_output=True, text=True, timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            return True, "qmd-Embeddings aktualisiert"
        else:
            return False, result.stderr.strip() or "qmd embed fehlgeschlagen"
    except FileNotFoundError:
        return False, "qmd nicht installiert"
    except subprocess.TimeoutExpired:
        return False, "qmd embed Zeitüberschreitung (>60s)"
    except Exception as e:
        return False, str(e)


def regenerate_index():
    """Baut wiki/index.md aus allen vorhandenen Seiten neu auf."""
    idx_path = WIKI_DIR / "index.md"
    pages = get_all_wiki_pages()

    lines = [
        "# Wiki-Index",
        "",
        "> Automatisch gepflegtes Inhaltsverzeichnis.",
        f"> Aktualisiert am {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Seiten",
        "",
    ]
    for p in pages:
        lines.append(f"- [[{p['slug']}.md]] – {p['title']}")

    if not pages:
        lines.append("_Noch keine Seiten im Wiki._")

    lines += [
        "",
        "## Statistik",
        "",
        f"- **Seiten gesamt:** {len(pages)}",
        f"- **Letzte Aktualisierung:** {datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]

    idx_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def do_sync():
    """Vollständiger Sync: qmd embed + index.md regenerieren + timestamp setzen."""
    global LAST_SYNC_TIME
    results = {"qmd": False, "index": False, "messages": []}

    # 1. qmd embed
    qmd_ok, qmd_msg = run_qmd_embed()
    results["qmd"] = qmd_ok
    results["messages"].append(qmd_msg)

    # 2. index.md regenerieren
    try:
        regenerate_index()
        results["index"] = True
        results["messages"].append("index.md neu aufgebaut")
    except Exception as e:
        results["messages"].append(f"index.md Fehler: {e}")

    # 3. Zeitstempel setzen
    LAST_SYNC_TIME = datetime.now()

    # 4. Auch wiki/log.md aktualisieren
    try:
        log_path = WIKI_DIR / "log.md"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n## [{datetime.now().strftime('%Y-%m-%d')}] sync | Webserver-Sync\n")
            f.write(f"- qmd: {'✅' if qmd_ok else '❌'} | index: {'✅' if results['index'] else '❌'}\n")
    except Exception:
        pass

    return results


@app.context_processor
def inject_globals():
    # Sprache aus Cookie oder Query-Parameter ermitteln
    lang_code = DEFAULT_LANG
    if hasattr(request, 'args') and request.args.get("lang"):
        lang_code = request.args.get("lang")
    elif hasattr(request, 'cookies') and request.cookies.get("llmwiki_lang"):
        lang_code = request.cookies.get("llmwiki_lang")

    # Verfügbare Sprachen prüfen
    available = get_available_languages()
    if lang_code not in available:
        lang_code = DEFAULT_LANG

    _t = Translator(lang_code)

    return {
        "all_pages": get_all_wiki_pages(),
        "now": datetime.now(),
        "app_name": APP_NAME,
        "app_edition": APP_EDITION,
        "sync_needed": is_sync_needed(),
        "_": _t,                     # Übersetzungsfunktion für Templates
        "current_lang": lang_code,   # Aktueller Sprachcode
        "available_languages": available,  # {code: name}
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════════

def get_recent_logs(limit=5):
    """Liest die neuesten Logbuch-Einträge aus log.md."""
    log_path = WIKI_DIR / "log.md"
    logs = []
    if log_path.exists():
        try:
            content = log_path.read_text(encoding="utf-8")
            # Finde alle H2-Einträge im Format: ## [Datum] Aktion | Details
            matches = re.finditer(r'^##\s+\[([^\]]+)\]\s+([^|\n]+)(?:\|\s*([^\n]+))?', content, re.MULTILINE)
            all_matches = list(matches)
            # Neueste zuerst (stehen meistens unten, also rückwärts durchgehen)
            for i, m in enumerate(reversed(all_matches)):
                date_str = m.group(1).strip()
                action = m.group(2).strip()
                details = m.group(3).strip() if m.group(3) else ""
                
                # Finde den Textkörper bis zum nächsten Match
                # Da we reversed all_matches, let's find the original index
                orig_idx = len(all_matches) - 1 - i
                start_pos = m.end()
                end_pos = all_matches[orig_idx + 1].start() if orig_idx + 1 < len(all_matches) else len(content)
                body = content[start_pos:end_pos].strip()
                # Nur die ersten 3 Aufzählungspunkte anzeigen
                body_lines = [line.strip() for line in body.split("\n") if line.strip()]
                if len(body_lines) > 3:
                    body = "\n".join(body_lines[:3]) + "\n- ..."
                
                logs.append({
                    "date": date_str,
                    "action": action,
                    "details": details,
                    "body": body
                })
                if len(logs) >= limit:
                    break
        except Exception:
            pass
    return logs


@app.route("/")
def index():
    """Startseite mit Wiki-Inhalt und Übersicht."""
    stats = get_wiki_stats()
    pages = get_all_wiki_pages()
    query = request.args.get("q", "")
    sync_status = request.args.get("sync_status", "")
    sync_msg = request.args.get("sync_msg", "")
    recent_logs = get_recent_logs(5)

    # index.md rendern, falls vorhanden
    index_content = ""
    index_file = WIKI_DIR / "index.md"
    if index_file.exists():
        raw_index = index_file.read_text(encoding="utf-8", errors="replace")
        index_content = render_markdown(raw_index)

    if query:
        return redirect(url_for("search", q=query))

    return render_template(
        "index.html",
        active_page="home",
        stats=stats,
        pages=pages,
        index_content=index_content,
        sync_status=sync_status,
        sync_msg=sync_msg,
        recent_logs=recent_logs,
    )


def get_wiki_trails():
    """Sucht nach Seiten vom Typ 'trail' und parst ihren Pfad."""
    trails = []
    wiki_pages = get_all_wiki_pages()
    for page in wiki_pages:
        filepath = WIKI_DIR / f"{page['slug']}.md"
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if fm_match:
                    is_trail = False
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("type:") and "trail" in line.split(":", 1)[1].lower():
                            is_trail = True
                    
                    if is_trail:
                        path_section = ""
                        m = re.search(r'^##\s+Path\s*$', content, re.MULTILINE)
                        if m:
                            start = m.end()
                            nxt = re.search(r'^##\s+', content[start:], re.MULTILINE)
                            path_section = content[start:start+nxt.start()] if nxt else content[start:]
                            
                        matches = re.findall(r'\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]', path_section)
                        path_slugs = []
                        for target_raw in matches:
                            t_slug = target_raw.strip().lower()
                            t_slug = t_slug.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
                            t_slug = re.sub(r'[^a-z0-9]', '-', t_slug)
                            t_slug = re.sub(r'-+', '-', t_slug).strip('-')
                            path_slugs.append((target_raw.strip(), t_slug))
                            
                        trails.append({
                            "slug": page["slug"],
                            "title": page["title"],
                            "path": path_slugs
                        })
            except Exception:
                pass
    return trails


@app.route("/wiki/<path:page_name>")
def wiki_page(page_name):
    """Zeigt eine Wiki-Seite an (gerendertes Markdown)."""
    # .md entfernen falls vorhanden
    page_name = re.sub(r'\.md$', '', page_name)

    data = read_wiki_file(f"{page_name}.md")
    if not data:
        if page_name == "ingestlater":
            file_path = WIKI_DIR / "ingestlater.md"
            template = (
                "# Ingest Later\n\n"
                "> Liste von URLs und Text-Schnipseln, die später ins Wiki eingepflegt werden sollen.\n\n"
                "## 🔗 Gemerkte URLs\n\n"
                "## 📝 Gemerkte Texte und Notizen\n\n"
            )
            file_path.write_text(template, encoding="utf-8")
            # Nach der Erstellung den Index neu synchronisieren, damit die Seite im System registriert wird
            subprocess.run(["./wiki.sh", "sync"], capture_output=True)
            data = read_wiki_file("ingestlater.md")
        else:
            abort(404, f"Seite '{page_name}' nicht im Wiki gefunden.")

    # Wikilinks erkennen (für missing-Links-Warnung)
    all_page_slugs = {p["slug"] for p in get_all_wiki_pages()}
    wikilinks_found = set(re.findall(r'\[\[([^\]]+)\]\]', data["content"]))
    # Nur den Dateinamen-Teil
    wikilinks_slugs = set()
    for link in wikilinks_found:
        target = link.split("|")[0].strip().lower().replace(" ", "-")
        target = re.sub(r'\.md$', '', target)
        wikilinks_slugs.add(target)
    missing_links = sorted(wikilinks_slugs - all_page_slugs)

    is_index = (page_name == "index")
    is_log = (page_name == "log")

    raw_content = data["content"]
    if is_log:
        first_h2 = re.search(r'^##\s+\[', raw_content, re.MULTILINE)
        if first_h2:
            header_part = raw_content[:first_h2.start()]
            body_part = raw_content[first_h2.start():]
            
            matches = list(re.finditer(r'^##\s+\[', body_part, re.MULTILINE))
            log_entries = []
            for i, m in enumerate(matches):
                start = m.start()
                end = matches[i+1].start() if i+1 < len(matches) else len(body_part)
                log_entries.append(body_part[start:end].strip())
            
            log_entries.reverse()
            raw_content = header_part + "\n\n" + "\n\n".join(log_entries)

    html_content = render_markdown(raw_content, page_name)

    # YAML-Frontmatter parsen für source-Angabe
    source_path = None
    fm_match = re.search(r'^---\s*\n(.*?)\n---', data["content"], re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).split("\n"):
            if line.startswith("source:"):
                source_path = line.split(":", 1)[1].strip()
                break

    # Trail-Informationen ermitteln
    trail_info = None
    trails = get_wiki_trails()
    for trail in trails:
        path = trail["path"]
        slugs_only = [item[1] for item in path]
        if page_name in slugs_only:
            idx = slugs_only.index(page_name)
            prev_item = path[idx - 1] if idx > 0 else None
            next_item = path[idx + 1] if idx < len(path) - 1 else None
            trail_info = {
                "title": trail["title"],
                "slug": trail["slug"],
                "prev": prev_item,
                "next": next_item,
                "index": idx + 1,
                "total": len(path)
            }
            break

    return render_template(
        "page.html",
        active_page=page_name,
        page_title=data["name"].replace("-", " ").title(),
        content=html_content,
        is_index=is_index,
        is_log=is_log,
        wikilinks_missing=missing_links,
        show_source=bool(source_path),
        source_path=source_path,
        raw_page_name=data["name"],
        success_msg=request.args.get("success_msg"),
        error_msg=request.args.get("error_msg"),
        trail_info=trail_info,
    )


def is_text_file(filename):
    suffix = Path(filename).suffix.lower()
    return suffix in (".md", ".txt", ".json", ".sh", ".yaml", ".yml", ".py", ".html", ".css", ".ini", ".conf", "")


def find_wiki_slug_for_raw(filename):
    if not WIKI_DIR.exists():
        return None
    for f in WIKI_DIR.iterdir():
        if f.suffix == ".md":
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("source:"):
                            src = line.split(":", 1)[1].strip().strip('"').strip("'")
                            if src == filename:
                                return f.stem
            except Exception:
                pass
    return None


@app.route("/raw")
def raw_list():
    """Listet alle Rohdateien im raw/ Ordner auf."""
    files = []
    if RAW_DIR.exists():
        for f in sorted(RAW_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep":
                stat = f.stat()
                size_kb = stat.st_size / 1024
                size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
                mtime_formatted = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                
                # Zugehörige Wiki-Seite finden
                wiki_slug = find_wiki_slug_for_raw(f.name)
                
                files.append({
                    "name": f.name,
                    "size_formatted": size_formatted,
                    "mtime_formatted": mtime_formatted,
                    "wiki_slug": wiki_slug
                })
    return render_template("raw_list.html", active_page="raw_list", files=files)


@app.route("/raw/<path:filename>")
def raw_page(filename):
    """Zeigt eine Rohdatei an oder serviert sie zum Download."""
    filepath = RAW_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        # Fallback falls es sich um eine alte Route handelt, die eine Wiki-Seite als Raw anzeigen will
        wiki_filepath = WIKI_DIR / filename
        if wiki_filepath.exists() and wiki_filepath.is_file():
            filepath = wiki_filepath
        else:
            abort(404, f"Rohdatei '{filename}' wurde nicht gefunden.")

    # Download erzwingen, falls gewünscht oder falls Binärdatei
    download_requested = request.args.get("download", "0") == "1"
    is_text = is_text_file(filename)

    if download_requested or not is_text:
        return flask.send_from_directory(str(RAW_DIR), filename, as_attachment=True)

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        stat = filepath.stat()
        size_kb = stat.st_size / 1024
        size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
        mtime_formatted = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        
        wiki_slug = find_wiki_slug_for_raw(filename)
        
        return render_template(
            "raw_view.html",
            active_page="raw_list",
            filename=filename,
            content=content,
            size_formatted=size_formatted,
            mtime_formatted=mtime_formatted,
            wiki_slug=wiki_slug,
            is_text=True
        )
    except Exception as e:
        abort(500, f"Fehler beim Lesen der Datei: {e}")


def get_pending_files():
    """Gibt eine Liste aller un-ingestierten Dateien in raw/ zurück."""
    files = []
    if RAW_DIR.exists():
        for f in sorted(RAW_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep":
                # Zugehörige Wiki-Seite suchen
                wiki_slug = find_wiki_slug_for_raw(f.name)
                if not wiki_slug:
                    stat = f.stat()
                    size_kb = stat.st_size / 1024
                    size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
                    mtime_formatted = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    
                    files.append({
                        "name": f.name,
                        "size_formatted": size_formatted,
                        "mtime_formatted": mtime_formatted
                    })
    return files


@app.route("/pending")
def pending_list():
    """Listet alle ausstehenden Dateien auf."""
    files = get_pending_files()
    return render_template(
        "pending_list.html",
        active_page="pending_list",
        files=files,
        success_msg=request.args.get("success_msg"),
        error_msg=request.args.get("error_msg")
    )


@app.route("/pending/ingest/<path:filename>")
def pending_ingest_single(filename):
    """Ingestiert eine einzelne ausstehende Datei."""
    filepath = RAW_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        abort(404, f"Datei '{filename}' nicht im raw/ Ordner gefunden.")
        
    try:
        backend = os.environ.get("LLM_BACKEND", "ollama")
        env = os.environ.copy()
        env["LLM_BACKEND"] = backend
        
        cmd = ["./wiki.sh", "ingest", str(filepath)]
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=120,
            cwd=str(PROJECT_ROOT),
            env=env
        )
        
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"Ingest fehlgeschlagen (Exitcode {result.returncode})")
            
        # Die ursprüngliche Datei löschen, da wiki.sh sie unter raw/$(today)-filename archiviert hat
        today_prefix = datetime.now().strftime("%Y-%m-%d")
        if not filename.startswith(today_prefix):
            try:
                filepath.unlink()
            except Exception:
                pass
                
        # Sync ausführen
        do_sync()
        
        success_msg = f"Datei '{filename}' wurde erfolgreich ingestiert!"
        return redirect(url_for("pending_list") + f"?success_msg={success_msg}")
    except Exception as e:
        return redirect(url_for("pending_list") + f"?error_msg=Fehler beim Ingest von {filename}: {e}")


@app.route("/pending/ingest-all")
def pending_ingest_all():
    """Ingestiert alle ausstehenden Dateien."""
    files = get_pending_files()
    if not files:
        return redirect(url_for("pending_list") + "?error_msg=Keine ausstehenden Dateien zum Ingestieren gefunden.")
        
    success_count = 0
    errors = []
    backend = os.environ.get("LLM_BACKEND", "ollama")
    
    for file in files:
        filename = file["name"]
        filepath = RAW_DIR / filename
        try:
            env = os.environ.copy()
            env["LLM_BACKEND"] = backend
            
            cmd = ["./wiki.sh", "ingest", str(filepath)]
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120,
                cwd=str(PROJECT_ROOT),
                env=env
            )
            
            if result.returncode == 0:
                success_count += 1
                today_prefix = datetime.now().strftime("%Y-%m-%d")
                if not filename.startswith(today_prefix):
                    try:
                        filepath.unlink()
                    except Exception:
                        pass
            else:
                errors.append(f"{filename}: {result.stderr.strip()}")
        except Exception as e:
            errors.append(f"{filename}: {e}")
            
    # Sync ausführen
    do_sync()
    
    if success_count > 0:
        msg = f"{success_count} Datei(en) erfolgreich ingestiert!"
        if errors:
            msg += f" (Fehler bei: {', '.join(errors)})"
        return redirect(url_for("pending_list") + f"?success_msg={msg}")
    else:
        err_msg = f"Ingest fehlgeschlagen: {'; '.join(errors)}"
        return redirect(url_for("pending_list") + f"?error_msg={err_msg}")


@app.route("/export")
def export_list():
    """Listet alle exportierten Dateien im output_docs/ Ordner auf."""
    files = []
    if EXPORT_DIR.exists():
        for f in sorted(EXPORT_DIR.iterdir()):
            if f.is_file() and f.name != ".gitkeep":
                stat = f.stat()
                size_kb = stat.st_size / 1024
                size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
                mtime_formatted = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                
                files.append({
                    "name": f.name,
                    "size_formatted": size_formatted,
                    "mtime_formatted": mtime_formatted
                })
    return render_template("export_list.html", active_page="export_list", files=files)


@app.route("/export/<path:filename>")
def export_view(filename):
    """Zeigt ein exportiertes Dokument an."""
    filepath = EXPORT_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        abort(404, f"Exportiertes Dokument '{filename}' wurde nicht gefunden.")
        
    download_requested = request.args.get("download", "0") == "1"
    is_markdown = filename.lower().endswith(".md")
    
    if download_requested:
        return flask.send_from_directory(str(EXPORT_DIR), filename, as_attachment=True)
        
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        stat = filepath.stat()
        size_kb = stat.st_size / 1024
        size_formatted = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{stat.st_size} Bytes"
        mtime_formatted = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        
        content_html = ""
        if is_markdown:
            content_html = render_markdown(content)
            
        return render_template(
            "export_view.html",
            active_page="export_list",
            filename=filename,
            content=content,
            content_html=content_html,
            size_formatted=size_formatted,
            mtime_formatted=mtime_formatted,
            is_markdown=is_markdown
        )
    except Exception as e:
        abort(500, f"Fehler beim Lesen des Dokuments: {e}")


@app.route("/graph")
def graph_page():
    """Zeigt die interaktive Wissensgraph-Visualisierung an."""
    return render_template("graph.html", active_page="graph")


@app.route("/graph/data")
def graph_data():
    """Liefert Knoten und Kanten des Wikis für vis.js."""
    nodes = []
    edges = []
    
    # Alle Wiki-Seiten laden
    wiki_pages = get_all_wiki_pages()
    wiki_slugs = {page["slug"]: page["title"] for page in wiki_pages}
    
    for page in wiki_pages:
        slug = page["slug"]
        title = page["title"]
        
        group = "page"
        tags = []
        
        # Dateipfad auslesen und Wikilinks extrahieren
        filepath = WIKI_DIR / f"{slug}.md"
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                
                # Frontmatter parsen
                fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("tags:"):
                            t_line = line.split(":", 1)[1].strip()
                            t_line = t_line.strip("[]").replace('"', '').replace("'", "")
                            tags = [t.strip() for t in t_line.split(",") if t.strip()]
                        elif line.startswith("source:"):
                            group = "source"
                
                # Sucht nach [[Zielseite]] mit Kontext-Analyse (Widersprüche finden)
                seen = set()
                for m in re.finditer(r'\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]', content):
                    target_raw = m.group(1).strip()
                    t_slug = target_raw.lower().replace(" ", "-").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
                    t_slug = re.sub(r'[^a-z0-9]', '-', t_slug)
                    t_slug = re.sub(r'-+', '-', t_slug).strip('-')
                    
                    # Zeilen-Kontext extrahieren für Widerspruchs-Suche
                    line_start = content.rfind("\n", 0, m.start()) + 1
                    line_end = content.find("\n", m.start())
                    if line_end == -1:
                        line_end = len(content)
                    line_content = content[line_start:line_end].lower()
                    
                    is_contradiction = any(w in line_content for w in ("contradict", "widerspricht", "widerspruch", "tension", "spannung"))
                    
                    if t_slug in wiki_slugs and t_slug != slug:
                        if t_slug not in seen:
                            seen.add(t_slug)
                            edge = {
                                "from": slug,
                                "to": t_slug
                            }
                            if is_contradiction:
                                edge["color"] = "#f56c6c"
                                edge["dashes"] = True
                                edge["title"] = "Widerspruch / Tension"
                            edges.append(edge)
            except Exception:
                pass
                
        if slug in ("index", "log", "ingestlater"):
            group = "system"
        elif tags:
            group = f"tag-{tags[0]}"
            
        nodes.append({
            "id": slug,
            "label": title,
            "group": group
        })
                
    return flask.jsonify({"nodes": nodes, "edges": edges})


def save_to_ingestlater(item_type, title, content):
    """Speichert eine URL oder einen Text in der Datei wiki/ingestlater.md."""
    file_path = WIKI_DIR / "ingestlater.md"
    
    # Standard-Template, falls Datei nicht existiert
    if not file_path.exists():
        template = (
            "# Ingest Later\n\n"
            "> Liste von URLs und Text-Schnipseln, die später ins Wiki eingepflegt werden sollen.\n\n"
            "## 🔗 Gemerkte URLs\n\n"
            "## 📝 Gemerkte Texte und Notizen\n\n"
        )
        file_path.write_text(template, encoding="utf-8")
        
    lines = file_path.read_text(encoding="utf-8").splitlines()
    
    new_lines = []
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
    
    # Nach Änderung: Index regenerieren und Sync laufen lassen
    do_sync()


@app.route("/ingest", methods=["GET", "POST"])
def ingest():
    """Führt ein Ingest (Datei oder Text) über das Webinterface aus oder speichert für später."""
    success_msg = None
    error_msg = None
    new_slug = None
    is_later = False

    if request.method == "POST":
        ingest_type = request.form.get("type")
        backend = request.form.get("backend", "ollama")
        
        # Temp-Verzeichnis sicherstellen
        temp_dir = PROJECT_ROOT / "scratch"
        temp_dir.mkdir(exist_ok=True)
        
        filepath = None
        orig_filename = None
        
        try:
            if ingest_type == "url_later":
                url = request.form.get("url", "").strip()
                title = request.form.get("title", "").strip()
                if not url:
                    raise ValueError("URL darf nicht leer sein.")
                save_to_ingestlater("url", title, url)
                success_msg = "URL erfolgreich in ingestlater.md gespeichert!"
                is_later = True
                return render_template(
                    "ingest.html",
                    active_page="ingest",
                    success_msg=success_msg,
                    error_msg=error_msg,
                    new_slug=None,
                    is_later=is_later
                )

            elif ingest_type == "text_later":
                title = request.form.get("title", "").strip()
                content = request.form.get("content", "").strip()
                if not title or not content:
                    raise ValueError("Titel und Inhalt dürfen nicht leer sein.")
                save_to_ingestlater("text", title, content)
                success_msg = "Text erfolgreich in ingestlater.md gespeichert!"
                is_later = True
                return render_template(
                    "ingest.html",
                    active_page="ingest",
                    success_msg=success_msg,
                    error_msg=error_msg,
                    new_slug=None,
                    is_later=is_later
                )

            elif ingest_type == "file":
                # Datei-Upload verarbeiten
                file = request.files.get("file")
                if not file or file.filename == "":
                    raise ValueError("Keine Datei ausgewählt.")
                
                orig_filename = file.filename
                # Dateinamen säubern
                safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', orig_filename)
                filepath = temp_dir / safe_name
                file.save(str(filepath))
                
            elif ingest_type == "text":
                # Text-Paste verarbeiten
                title = request.form.get("title", "").strip()
                content = request.form.get("content", "").strip()
                if not title or not content:
                    raise ValueError("Titel und Inhalt dürfen nicht leer sein.")
                
                # Slugify den Titel für den Dateinamen
                safe_title = title.lower().replace(" ", "-").replace("/", "-")
                safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', safe_title) + ".md"
                orig_filename = safe_name
                filepath = temp_dir / safe_name
                
                # Datei schreiben (wenn kein # am Anfang, füge Titel als H1 ein)
                if not content.startswith("#"):
                    content = f"# {title}\n\n{content}"
                filepath.write_text(content, encoding="utf-8")
            
            else:
                raise ValueError("Ungültiger Ingest-Typ.")
                
            # CLI-Script wiki.sh ausführen
            env = os.environ.copy()
            env["LLM_BACKEND"] = backend
            
            # Optionaler Titel-Parameter
            cmd = ["./wiki.sh", "ingest", str(filepath)]
            custom_title = request.form.get("title", "").strip()
            if custom_title and ingest_type == "file":
                cmd += ["--title", custom_title]
                
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120,
                cwd=str(PROJECT_ROOT),
                env=env
            )
            
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or f"Ingest fehlgeschlagen mit Exitcode {result.returncode}")
            
            # Neue Seite im Wiki finden
            title_to_slug = custom_title if (custom_title and ingest_type == "file") else request.form.get("title", "").strip()
            if not title_to_slug and filepath:
                # Versuche H1 zu lesen
                try:
                    f_content = filepath.read_text(encoding="utf-8")
                    h1_match = re.search(r'^#\s+(.+)$', f_content, re.MULTILINE)
                    if h1_match:
                        title_to_slug = h1_match.group(1).strip()
                except Exception:
                    pass
            if not title_to_slug:
                title_to_slug = Path(orig_filename).stem
                
            # Einfache Slugification in Python für Weiterleitung
            new_slug = title_to_slug.lower()
            new_slug = new_slug.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
            new_slug = re.sub(r'[^a-z0-9]', '-', new_slug)
            new_slug = re.sub(r'-+', '-', new_slug).strip('-')
            
            success_msg = f"Quelle erfolgreich eingespielt! ({new_slug}.md)"
            
            # Sync erzwingen, damit qmd und index.md sofort aktuell sind
            do_sync()
            
        except Exception as e:
            error_msg = str(e)
        finally:
            # Temporäre Datei löschen
            if filepath and filepath.exists():
                try:
                    filepath.unlink()
                except Exception:
                    pass

    return render_template(
        "ingest.html",
        active_page="ingest",
        success_msg=success_msg,
        error_msg=error_msg,
        new_slug=new_slug,
        is_later=is_later
    )


def highlight_text(text, query):
    if not query:
        import html
        return html.escape(text)
    import html
    escaped_text = html.escape(text)
    # Case insensitive replacement while preserving original casing
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    return pattern.sub(lambda m: f'<mark class="search-highlight">{m.group(0)}</mark>', escaped_text)


@app.route("/search")
def search():
    """Volltextsuche mit qmd + Sync-Hinweis und Treffer-Hervorhebung."""
    query = request.args.get("q", "").strip()
    results = []
    error = None
    sync_hint = False

    if query:
        # Prüfen: Sync nötig? Wenn Seiten existieren aber qmd nix findet
        page_count = len(get_all_wiki_pages())
        if page_count > 0 and is_sync_needed():
            sync_hint = True

        search_result = qmd_search(query)
        if search_result.get("error"):
            # Bei Fehler: automatisch syncen und erneut versuchen
            if "not found" in search_result.get("error", "").lower() or "timeout" in search_result.get("error", "").lower():
                do_sync()
                search_result = qmd_search(query)
                sync_hint = False
            else:
                error = search_result["error"]
        
        if not error:
            raw_results = search_result.get("results", [])
            for r in raw_results:
                r["title_html"] = highlight_text(r["title"], query)
                r["snippet_html"] = highlight_text(r["snippet"], query)
                results.append(r)

            # Wenn keine Ergebnisse obwohl Seiten existieren → Sync-Hinweis
            if not results and page_count > 0 and is_sync_needed():
                sync_hint = True

        # Berechnen, in wie vielen Rohdateien der Suchbegriff vorkommt (Stub-Erstellungsschwelle)
        raw_mentions_count = 0
        if RAW_DIR.exists():
            for f in RAW_DIR.iterdir():
                if f.is_file() and f.suffix in (".md", ".txt"):
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace").lower()
                        if query.lower() in content:
                            raw_mentions_count += 1
                    except Exception:
                        pass
        # Prüfen ob ein Slug bereits dafür existiert
        target_slug = query.lower().replace(" ", "-").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
        target_slug = re.sub(r'[^a-z0-9-]', '', target_slug)
        target_slug = re.sub(r'-+', '-', target_slug).strip('-')
        slug_exists = target_slug in {p["slug"] for p in get_all_wiki_pages()}

    return render_template(
        "search.html",
        active_page="search",
        query=query,
        results=results,
        error=error,
        sync_hint=sync_hint,
        page_count=len(get_all_wiki_pages()),
        raw_mentions_count=raw_mentions_count if query else 0,
        slug_exists=slug_exists if query else False,
    )


@app.route("/lang/<code>")
def switch_language(code):
    """Schaltet die Sprache um und setzt ein Cookie."""
    available = get_available_languages()
    if code not in available:
        code = DEFAULT_LANG
    referrer = request.referrer or "/"
    response = flask.redirect(referrer)
    response.set_cookie("llmwiki_lang", code, max_age=365*24*3600)  # 1 Jahr
    return response


@app.route("/about")
def about():
    """Über-Seite mit Versionsinfo."""
    try:
        qmd_ver = subprocess.run([QMD_BIN, "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        qmd_ver = "nicht gefunden"

    import markdown as md_lib
    import jinja2
    from importlib.metadata import version as pkg_version

    try:
        md_ver = pkg_version("markdown")
    except Exception:
        md_ver = getattr(md_lib, "__version__", "unbekannt")

    try:
        flask_ver = pkg_version("flask")
    except Exception:
        flask_ver = flask.__version__

    try:
        uvicorn_ver = pkg_version("uvicorn")
    except Exception:
        uvicorn_ver = "unbekannt"

    return render_template(
        "about.html",
        active_page="about",
        app_version=APP_VERSION,
        python_version=sys.version.split()[0],
        flask_version=flask_ver,
        markdown_version=md_ver,
        jinja_version=pkg_version("jinja2"),
        qmd_version=qmd_ver,
        uvicorn_version=uvicorn_ver,
    )


@app.route("/admin/status")
def admin_status():
    """Zeigt den aktuellen Sync-Status als JSON an."""
    return {
        "sync_needed": is_sync_needed(),
        "last_sync": LAST_SYNC_TIME.isoformat() if LAST_SYNC_TIME else None,
        "pages": len(get_all_wiki_pages()),
        "server": APP_VERSION,
    }


@app.route("/admin/sync")
def admin_sync():
    """Führt einen vollständigen Sync aus (qmd embed + index.md neu)."""
    results = do_sync()
    fmt = request.args.get("format", "html")

    if fmt == "json":
        return {
            "success": results["qmd"] and results["index"],
            "qmd": results["qmd"],
            "index": results["index"],
            "messages": results["messages"],
        }

    # HTML-Redirect zurück mit Statusmeldung
    status = "✅ Sync erfolgreich!" if (results["qmd"] and results["index"]) else "⚠ Sync teilweise fehlgeschlagen"
    messages = "; ".join(results["messages"])
    return redirect(url_for("index", _external=True) + f"?sync_status={status}&sync_msg={messages}")


@app.route("/admin/update")
def admin_update():
    """Weiterleitung zur Einstellungsseite (Update-Tab)."""
    return redirect("/settings?tab=update")


@app.route("/admin/update/run", methods=["POST"])
def admin_update_run():
    """Weiterleitung zur Einstellungsseite (Update-Tab). Nutze stattdessen das Formular in den Einstellungen."""
    return redirect("/settings?tab=update")


@app.route("/admin/update/check")
def admin_update_check():
    """Prüft, ob ein Update auf GitHub verfügbar ist."""
    version_file = PROJECT_ROOT / "VERSION"
    local_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unbekannt"

    try:
        proc = subprocess.run(
            ["curl", "-sL", "https://raw.githubusercontent.com/ZeroDot1/LLMWikiNG/main/VERSION"],
            capture_output=True,
            text=True,
            timeout=15
        )
        github_version = proc.stdout.strip()
        if not github_version or proc.returncode != 0:
            github_version = None
    except Exception:
        github_version = None

    if github_version is None:
        return {
            "success": False,
            "error": "Konnte Version von GitHub nicht abrufen."
        }

    update_available = github_version != local_version

    return {
        "success": True,
        "local_version": local_version,
        "github_version": github_version,
        "update_available": update_available,
        "up_to_date": not update_available
    }


def get_wiki_analytics():
    """Berechnet detaillierte Statistiken und Analysen über das Wiki."""
    wiki_pages = get_all_wiki_pages()
    
    inbound_links = {page["slug"]: 0 for page in wiki_pages}
    outbound_count = {page["slug"]: 0 for page in wiki_pages}
    tag_counts = {}
    
    for page in wiki_pages:
        slug = page["slug"]
        filepath = WIKI_DIR / f"{slug}.md"
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                
                # Tags parsen
                fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("tags:"):
                            tags_line = line.split(":", 1)[1].strip()
                            tags_line = tags_line.strip("[]").replace('"', '').replace("'", "")
                            for tag in tags_line.split(","):
                                tag = tag.strip()
                                if tag:
                                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
                                    
                # Links
                matches = re.findall(r'\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]', content)
                for target_raw in matches:
                    t_slug = target_raw.strip().lower()
                    t_slug = t_slug.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
                    t_slug = re.sub(r'[^a-z0-9]', '-', t_slug)
                    t_slug = re.sub(r'-+', '-', t_slug).strip('-')
                    
                    if t_slug in inbound_links:
                        inbound_links[t_slug] += 1
                        outbound_count[slug] += 1
            except Exception:
                pass
                
    # Hubs sortieren
    hubs = []
    for page in wiki_pages:
        slug = page["slug"]
        count = inbound_links.get(slug, 0)
        if count > 0:
            hubs.append({
                "slug": slug,
                "title": page["title"],
                "links": count
            })
    hubs.sort(key=lambda x: x["links"], reverse=True)
    
    # Sackgassen
    dead_ends = [page for page in wiki_pages if outbound_count.get(page["slug"], 0) == 0]
    
    # Top Tags
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    
    # 4. Brücken-Seiten (Bridges) ermitteln - Seiten, deren verlinkte Nachbarn die größte Tag-Vielfalt besitzen
    bridges = []
    # Zuerst Map: page_slug -> tags
    slug_tags = {}
    for page in wiki_pages:
        slug = page["slug"]
        filepath = WIKI_DIR / f"{slug}.md"
        slug_tags[slug] = set()
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("tags:"):
                            t_line = line.split(":", 1)[1].strip()
                            t_line = t_line.strip("[]").replace('"', '').replace("'", "")
                            slug_tags[slug] = {t.strip() for t in t_line.split(",") if t.strip()}
            except Exception:
                pass
                
    for page in wiki_pages:
        slug = page["slug"]
        filepath = WIKI_DIR / f"{slug}.md"
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                matches = re.findall(r'\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]', content)
                seen_tags = set()
                for target_raw in matches:
                    t_slug = target_raw.strip().lower()
                    t_slug = t_slug.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
                    t_slug = re.sub(r'[^a-z0-9]', '-', t_slug)
                    t_slug = re.sub(r'-+', '-', t_slug).strip('-')
                    if t_slug in slug_tags:
                        seen_tags.update(slug_tags[t_slug])
                if len(seen_tags) > 1:
                    bridges.append({
                        "slug": slug,
                        "title": page["title"],
                        "tags_count": len(seen_tags),
                        "connected_tags": sorted(list(seen_tags))
                    })
            except Exception:
                pass
    bridges.sort(key=lambda x: x["tags_count"], reverse=True)
    
    return {
        "hubs": hubs[:8],
        "dead_ends": dead_ends[:8],
        "top_tags": top_tags,
        "bridges": bridges[:5]
    }


@app.route("/status")
def status_dashboard():
    """Zeigt das System-Dashboard mit Konfiguration und Tool-Status."""
    stats = get_wiki_stats()
    analytics = get_wiki_analytics()
    
    # Tool-Verfügbarkeit prüfen
    tools = {}
    for tool in ("qmd", "jq", "ollama", "agy", "opencode"):
        tools[tool] = bool(subprocess.run(["command", "-v", tool], shell=True, capture_output=True).returncode == 0)
        
    config_data = {
        "backend": os.environ.get("LLM_BACKEND", "ollama"),
        "ollama_model": os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
        "wiki_dir": str(WIKI_DIR),
        "raw_dir": str(RAW_DIR),
        "export_dir": str(EXPORT_DIR)
    }
    
    # Version aus VERSION-Datei lesen
    version_file = PROJECT_ROOT / "VERSION"
    app_version_text = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else APP_VERSION

    # Prüfen, ob update.sh verfügbar ist
    update_available = (PROJECT_ROOT / "update.sh").exists()

    return render_template(
        "status.html",
        active_page="status",
        stats=stats,
        tools=tools,
        config=config_data,
        analytics=analytics,
        app_version=app_version_text,
        update_available=update_available
    )


@app.route("/lint")
def lint_dashboard():
    """Führt den Gesundheitscheck (Lint) aus und zeigt die Ergebnisse."""
    run_check = request.args.get("run", "0") == "1"
    orphans = []
    missing_pages = []
    stale_pages = []
    missing_raw_files = []
    issue_count = 0
    
    if run_check and WIKI_DIR.exists():
        pages = get_all_wiki_pages()
        all_slugs = {p["slug"] for p in pages}
        
        # 1. Orphans finden (keine Rückverweise)
        for p in pages:
            if p["slug"] in ("index", "log", "ingestlater"):
                continue
            
            # Suche nach [[slug]] in allen anderen Seiten
            has_backlink = False
            for other in pages:
                if other["slug"] == p["slug"]:
                    continue
                other_file = WIKI_DIR / f"{other['slug']}.md"
                try:
                    other_content = other_file.read_text(encoding="utf-8", errors="replace").lower()
                    if f"[[{p['slug'].replace('-', ' ')}]]" in other_content or f"[[{p['slug']}]]" in other_content:
                        has_backlink = True
                        break
                except Exception:
                    pass
            
            if not has_backlink:
                orphans.append(p)
                issue_count += 1
                
        # 2. Fehlende verlinkte Seiten finden (mit Häufigkeit und Quellen)
        missing_map = {}
        for p in pages:
            file_path = WIKI_DIR / f"{p['slug']}.md"
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                refs = re.findall(r'\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]', content)
                for ref in refs:
                    target_raw = ref.strip()
                    target_slug = target_raw.lower().replace(" ", "-").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
                    target_slug = re.sub(r'[^a-z0-9-]', '', target_slug)
                    target_slug = re.sub(r'-+', '-', target_slug).strip('-')
                    
                    if target_slug and target_slug not in all_slugs and target_slug not in ("index", "log", "ingestlater"):
                        if target_slug not in missing_map:
                            missing_map[target_slug] = {
                                "title": target_raw,
                                "sources": set()
                            }
                        missing_map[target_slug]["sources"].add((p["title"], p["slug"]))
            except Exception:
                pass
                
        # In Liste umwandeln und nach Anzahl der Referenzen sortieren
        for ref_slug, info in missing_map.items():
            sources_list = sorted(list(info["sources"]))
            missing_pages.append({
                "slug": ref_slug,
                "title": info["title"],
                "sources": sources_list,
                "count": len(sources_list)
            })
            issue_count += 1
            
        # 3. Veraltete Seiten (Stale Pages) ermitteln
        stale_pages = []
        for p in pages:
            if p["slug"] in ("index", "log", "ingestlater"):
                continue
            file_path = WIKI_DIR / f"{p['slug']}.md"
            if file_path.exists():
                try:
                    stat = file_path.stat()
                    stale_pages.append({
                        "slug": p["slug"],
                        "title": p["title"],
                        "mtime_formatted": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                        "mtime": stat.st_mtime
                    })
                except Exception:
                    pass
        # Nach mtime aufsteigend sortieren (älteste zuerst)
        stale_pages.sort(key=lambda x: x["mtime"])
        stale_pages = stale_pages[:5]  # Top 5 älteste Seiten
        
        # 4. Fehlende Rohquellen (raw file references) ermitteln
        for p in pages:
            file_path = WIKI_DIR / f"{p['slug']}.md"
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                raw_matches = re.findall(r'\*\*Quelle:\*\*\s*`([^`]+)`', content)
                for raw_file in raw_matches:
                    raw_file = raw_file.strip()
                    raw_path = RAW_DIR / raw_file
                    if not raw_path.exists():
                        missing_raw_files.append({
                            "page_title": p["title"],
                            "page_slug": p["slug"],
                            "raw_file": raw_file
                        })
                        issue_count += 1
            except Exception:
                pass
                
    return render_template(
        "lint.html",
        active_page="lint",
        run_check=run_check,
        orphans=orphans,
        missing=missing_pages,
        stale=stale_pages,
        missing_raw=missing_raw_files,
        issue_count=issue_count
    )


from email_sender import load_smtp_config, save_smtp_config, send_real_email


@app.route("/config", methods=["GET", "POST"])
def config_page():
    """E-Mail Konfigurationsseite."""
    success_msg = None
    error_msg = None
    
    if request.method == "POST":
        smtp_host = request.form.get("smtp_host", "smtp.gmail.com")
        try:
            smtp_port = int(request.form.get("smtp_port", "587"))
        except ValueError:
            smtp_port = 587
        smtp_user = request.form.get("smtp_user", "").strip()
        smtp_pass = request.form.get("smtp_pass", "").strip()
        use_tls = request.form.get("use_tls") == "1"
        recipients = request.form.get("recipients", "").strip()
        
        new_config = {
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_user": smtp_user,
            "smtp_pass": smtp_pass,
            "use_tls": use_tls,
            "recipients": recipients
        }
        
        if save_smtp_config(new_config):
            success_msg = "Konfiguration erfolgreich in config.json gespeichert!"
        else:
            error_msg = "Fehler beim Speichern der Konfiguration."
            
    config_data = load_smtp_config()
    env_user = os.environ.get("GMAIL_USER", "")
    env_pass_exists = bool(os.environ.get("GMAIL_APP_PASSWORD"))
    
    return render_template(
        "config.html",
        active_page="config",
        config=config_data,
        env_user=env_user,
        env_pass_exists=env_pass_exists,
        success_msg=success_msg,
        error_msg=error_msg
    )


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    """Einstellungsseite mit Tabs: Sprache, E-Mail-Konfiguration, Gesundheitscheck, Update."""
    from email_sender import load_smtp_config, save_smtp_config

    config_success_msg = None
    config_error_msg = None

    # Update-Variablen
    version_file = PROJECT_ROOT / "VERSION"
    app_version_text = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else APP_VERSION
    update_available_flag = (PROJECT_ROOT / "update.sh").exists()
    update_log_output = None

    # POST-Handling: SMTP Config ODER Update ausführen
    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "run_update":
            # Update ausführen
            update_script = PROJECT_ROOT / "update.sh"
            if not update_script.exists():
                update_log_output = "FEHLER: update.sh nicht gefunden."
            else:
                try:
                    proc = subprocess.run(
                        [str(update_script)],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        cwd=str(PROJECT_ROOT)
                    )
                    update_log_output = proc.stdout + proc.stderr
                except subprocess.TimeoutExpired:
                    update_log_output = "FEHLER: Update-Skript hat 120 Sekunden überschritten."
                except Exception as e:
                    update_log_output = f"FEHLER: {e}"
        else:
            # SMTP Config speichern
            smtp_host = request.form.get("smtp_host", "smtp.gmail.com")
            try:
                smtp_port = int(request.form.get("smtp_port", "587"))
            except ValueError:
                smtp_port = 587
            smtp_user = request.form.get("smtp_user", "").strip()
            smtp_pass = request.form.get("smtp_pass", "").strip()
            use_tls = request.form.get("use_tls") == "1"
            recipients = request.form.get("recipients", "").strip()

            new_config = {
                "smtp_host": smtp_host,
                "smtp_port": smtp_port,
                "smtp_user": smtp_user,
                "smtp_pass": smtp_pass,
                "use_tls": use_tls,
                "recipients": recipients
            }

            if save_smtp_config(new_config):
                config_success_msg = "Konfiguration erfolgreich in config.json gespeichert!"
            else:
                config_error_msg = "Fehler beim Speichern der Konfiguration."

    smtp_config_data = load_smtp_config()
    env_user = os.environ.get("GMAIL_USER", "")
    env_pass_exists = bool(os.environ.get("GMAIL_APP_PASSWORD"))

    # Gesundheitscheck (Lint)
    health_run_check = request.args.get("run") == "1"
    health_orphans = []
    health_missing = []
    health_stale = []
    health_missing_raw = []
    health_issue_count = 0

    if health_run_check and WIKI_DIR.exists():
        pages = get_all_wiki_pages()
        all_slugs = {p["slug"] for p in pages}

        # 1. Orphans
        for p in pages:
            if p["slug"] in ("index", "log", "ingestlater"):
                continue
            has_backlink = False
            for other in pages:
                if other["slug"] == p["slug"]:
                    continue
                other_file = WIKI_DIR / f"{other['slug']}.md"
                try:
                    other_content = other_file.read_text(encoding="utf-8", errors="replace").lower()
                    if f"[[{p['slug'].replace('-', ' ')}]]" in other_content or f"[[{p['slug']}]]" in other_content:
                        has_backlink = True
                        break
                except Exception:
                    pass
            if not has_backlink:
                health_orphans.append(p)
                health_issue_count += 1

        # 2. Missing pages
        missing_map = {}
        for p in pages:
            file_path = WIKI_DIR / f"{p['slug']}.md"
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                refs = re.findall(r'\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]', content)
                for ref in refs:
                    target_raw = ref.strip()
                    target_slug = target_raw.lower().replace(" ", "-")
                    target_slug = target_slug.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
                    target_slug = re.sub(r'[^a-z0-9-]', '', target_slug)
                    target_slug = re.sub(r'-+', '-', target_slug).strip('-')
                    if target_slug and target_slug not in all_slugs and target_slug not in ("index", "log", "ingestlater"):
                        if target_slug not in missing_map:
                            missing_map[target_slug] = {"title": target_raw, "sources": set()}
                        missing_map[target_slug]["sources"].add((p["title"], p["slug"]))
            except Exception:
                pass

        for ref_slug, info in missing_map.items():
            sources_list = sorted(list(info["sources"]))
            health_missing.append({
                "slug": ref_slug,
                "title": info["title"],
                "sources": sources_list,
                "count": len(sources_list)
            })
            health_issue_count += 1

        # 3. Stale pages
        for p in pages:
            if p["slug"] in ("index", "log", "ingestlater"):
                continue
            file_path = WIKI_DIR / f"{p['slug']}.md"
            if file_path.exists():
                try:
                    stat = file_path.stat()
                    health_stale.append({
                        "slug": p["slug"],
                        "title": p["title"],
                        "mtime_formatted": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                        "mtime": stat.st_mtime
                    })
                except Exception:
                    pass
        health_stale.sort(key=lambda x: x["mtime"])
        health_stale = health_stale[:5]

        # 4. Missing raw refs
        for p in pages:
            file_path = WIKI_DIR / f"{p['slug']}.md"
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                raw_matches = re.findall(r'\*\*Quelle:\*\*\s*`([^`]+)`', content)
                for raw_file in raw_matches:
                    raw_file = raw_file.strip()
                    raw_path = RAW_DIR / raw_file
                    if not raw_path.exists():
                        health_missing_raw.append({
                            "page_title": p["title"],
                            "page_slug": p["slug"],
                            "raw_file": raw_file
                        })
                        health_issue_count += 1
            except Exception:
                pass

    return render_template(
        "settings.html",
        active_page="settings",
        smtp_config=smtp_config_data,
        env_user=env_user,
        env_pass_exists=env_pass_exists,
        config_success_msg=config_success_msg,
        config_error_msg=config_error_msg,
        health_run_check=health_run_check,
        health_orphans=health_orphans,
        health_missing=health_missing,
        health_stale=health_stale,
        health_missing_raw=health_missing_raw,
        health_issue_count=health_issue_count,
        app_version=app_version_text,
        update_available=update_available_flag,
        update_log=update_log_output,
    )


@app.route("/briefings", methods=["GET", "POST"])
def briefings_dashboard():
    """Wöchentliche Zusammenfassungen (Briefings) generieren und versenden."""
    week_arg = request.args.get("week")
    
    # Heutiges Datum holen
    today = date.today()
    if not week_arg:
        iso = today.isocalendar()
        week_arg = f"{iso[0]}-W{iso[1]:02d}"
        
    try:
        year, week_num = parse_week_string(week_arg)
    except Exception:
        iso = today.isocalendar()
        week_arg = f"{iso[0]}-W{iso[1]:02d}"
        year, week_num = iso[0], iso[1]
        
    start_date = date.fromisocalendar(year, week_num, 1)
    end_date = date.fromisocalendar(year, week_num, 7)
    
    pages = get_all_wiki_pages()
    week_pages = []
    
    for p in pages:
        if p["slug"] in ("index", "log", "ingestlater") or p["slug"].startswith("briefing-"):
            continue
        file_path = WIKI_DIR / f"{p['slug']}.md"
        if file_path.exists():
            try:
                stat = file_path.stat()
                mtime_date = date.fromtimestamp(stat.st_mtime)
                
                created_date = None
                content = file_path.read_text(encoding="utf-8", errors="replace")
                fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.startswith("created:"):
                            created_str = line.split(":", 1)[1].strip().strip('"\'')
                            try:
                                created_date = date.fromisoformat(created_str[:10])
                            except ValueError:
                                pass
                
                in_week = False
                if created_date and start_date <= created_date <= end_date:
                    in_week = True
                elif start_date <= mtime_date <= end_date:
                    in_week = True
                    
                if in_week:
                    week_pages.append(p)
            except Exception:
                pass
                
    success_msg = None
    error_msg = None
    email_simulation = None
    
    # Aktuelle Konfiguration laden
    smtp_cfg = load_smtp_config()
    
    if request.method == "POST":
        action = request.form.get("action")
        if action == "generate":
            briefing_slug = f"briefing-{year}-w{week_num:02d}"
            briefing_path = WIKI_DIR / f"{briefing_slug}.md"
            
            list_items = []
            for wp in week_pages:
                list_items.append(f"- **[[{wp['title']}]]** — {wp['desc']}")
            list_text = "\n".join(list_items) if list_items else "- Keine neuen Einträge in dieser Woche."
            
            template = (
                f"---\n"
                f"title: \"Wochenbericht: {year}-W{week_num:02d}\"\n"
                f"type: timeline\n"
                f"created: {today.isoformat()}\n"
                f"---\n\n"
                f"# 📰 Wochenbericht: {year}-W{week_num:02d}\n\n"
                f"Zusammenfassung des Wissenszuwachses vom {start_date.strftime('%d.%m.%Y')} bis zum {end_date.strftime('%d.%m.%Y')}.\n\n"
                f"## 🆕 Neue & geänderte Themen\n\n"
                f"{list_text}\n\n"
                f"## 🔮 Ausblick & Synthese\n"
                f"Automatisch generiertes Briefing für den Wissensspeicher.\n"
            )
            briefing_path.write_text(template, encoding="utf-8")
            do_sync()
            return redirect(url_for("wiki_page", page_name=briefing_slug, success_msg="Wochenbericht erfolgreich generiert!"))
            
        elif action == "email":
            to_emails = request.form.get("to_emails", "").strip()
            recipients = [e.strip() for e in to_emails.split(",") if e.strip()]
            
            subject = f"📰 LLMWikiNG Wochenbericht {year}-W{week_num:02d}"
            
            email_html = (
                f"<div style='font-family: sans-serif; max-width: 600px; margin: auto; padding: 1.5rem; border: 1px solid #ddd; border-radius: 8px; background: #fafafa; color: black;'>"
                f"<h2 style='color: #4f46e5; border-bottom: 2px solid #4f46e5; padding-bottom: 0.5rem;'>📰 LLMWikiNG Wochenbericht {year}-W{week_num:02d}</h2>"
                f"<p style='color: #555;'>Hallo,</p>"
                f"<p style='color: #555;'>hier ist deine wöchentliche Übersicht über die neuen Themen im Recht-Wiki (Zeitraum: {start_date.strftime('%d.%m.%Y')} bis {end_date.strftime('%d.%m.%Y')}):</p>"
                f"<ul style='padding-left: 1.2rem;'>"
            )
            for wp in week_pages:
                email_html += f"<li style='margin-bottom: 0.8rem;'><strong>{wp['title']}</strong> — {wp['desc']}</li>"
            if not week_pages:
                email_html += "<li style='color: #888;'>Keine neuen Einträge in dieser Woche.</li>"
                
            email_html += (
                f"</ul>"
                f"<hr style='border: none; border-top: 1px solid #eee; margin: 1.5rem 0;'>"
                f"<p style='font-size: 0.8rem; color: #888; text-align: center;'>Generiert von LLMWikiNG · Unlicense</p>"
                f"</div>"
            )
            
            try:
                sent_to = send_real_email(subject, email_html, to_list_override=recipients)
                success_msg = f"E-Mail erfolgreich an {', '.join(sent_to)} versendet!"
            except Exception as e:
                error_msg = f"Fehler beim E-Mail-Versand: {e}"
            
            # E-Mail-Entwurf zur Visualisierung behalten
            email_simulation = {
                "to": ", ".join(recipients) if recipients else smtp_cfg.get("recipients", ""),
                "subject": subject,
                "html": email_html
            }
            
    # Initialwerte für Formular
    default_smtp_user = smtp_cfg.get("smtp_user") or os.environ.get("GMAIL_USER", "")
    has_env_creds = bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD")) or bool(smtp_cfg.get("smtp_user") and smtp_cfg.get("smtp_pass"))
    recipients_value = smtp_cfg.get("recipients", "")
            
    return render_template(
        "briefing.html",
        active_page="briefings",
        week=week_arg,
        start_date=start_date,
        end_date=end_date,
        week_pages=week_pages,
        success_msg=success_msg,
        error_msg=error_msg,
        email_simulation=email_simulation,
        default_smtp_user=default_smtp_user,
        has_env_creds=has_env_creds,
        recipients_value=recipients_value,
        smtp_cfg=smtp_cfg
    )


def parse_week_string(s):
    m = re.match(r"^(\d{4})-[Ww](\d{1,2})$", s.strip())
    if not m:
        raise ValueError()
    return int(m.group(1)), int(m.group(2))


@app.route("/wiki/<path:page_name>/export")
def export_page_route(page_name):
    """Exportiert eine Wiki-Seite nach output_docs/."""
    page_name = re.sub(r'\.md$', '', page_name)
    src_file = WIKI_DIR / f"{page_name}.md"
    
    if not src_file.exists():
        abort(404, f"Seite '{page_name}' existiert nicht.")
        
    try:
        EXPORT_DIR.mkdir(exist_ok=True)
        dest_file = EXPORT_DIR / f"{page_name}.md"
        
        # Kopieren
        dest_file.write_text(src_file.read_text(encoding="utf-8"), encoding="utf-8")
        
        # Logbuch eintragen
        try:
            log_path = WIKI_DIR / "log.md"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n## [{datetime.now().strftime('%Y-%m-%d')}] export | {page_name}\n")
                f.write(f"- Seite exportiert nach {dest_file.relative_to(PROJECT_ROOT)}\n")
        except Exception:
            pass
            
        success_msg = f"Seite '{page_name}.md' erfolgreich nach output_docs/ exportiert!"
        return redirect(url_for("wiki_page", page_name=page_name) + f"?success_msg={success_msg}")
    except Exception as e:
        return redirect(url_for("wiki_page", page_name=page_name) + f"?error_msg=Export fehlgeschlagen: {e}")

@app.route("/wiki/<path:page_name>/delete")
def delete_page_route(page_name):
    """Löscht eine Wiki-Seite."""
    page_name = re.sub(r'\.md$', '', page_name)
    
    # Schutz vor Löschen von System-Dateien
    if page_name in ("index", "log", "ingestlater"):
        abort(403, "System-Dateien können nicht gelöscht werden.")
        
    src_file = WIKI_DIR / f"{page_name}.md"
    if not src_file.exists():
        abort(404, f"Seite '{page_name}' existiert nicht.")
        
    try:
        # Datei löschen
        src_file.unlink()
        
        # Logbuch eintragen
        try:
            log_path = WIKI_DIR / "log.md"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n## [{datetime.now().strftime('%Y-%m-%d')}] delete | {page_name}\n")
                f.write(f"- Seite gelöscht\n")
        except Exception:
            pass
            
        # Sync ausführen
        do_sync()
        
        success_msg = f"Seite '{page_name}.md' erfolgreich gelöscht."
        return redirect(url_for("index") + f"?sync_status={success_msg}")
    except Exception as e:
        return redirect(url_for("wiki_page", page_name=page_name) + f"?error_msg=Löschen fehlgeschlagen: {e}")


@app.route("/admin/clear-log")
def clear_log_route():
    """Leert das Logbuch komplett."""
    log_path = WIKI_DIR / "log.md"
    try:
        template = (
            f"---\n"
            f"title: \"Logbuch\"\n"
            f"type: timeline\n"
            f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"---\n\n"
            f"# 📜 Logbuch\n\n"
            f"Protokollierte Wiki-Aktivitäten.\n"
        )
        log_path.write_text(template, encoding="utf-8")
        do_sync()
        return redirect(url_for("wiki_page", page_name="log", success_msg="Logbuch erfolgreich geleert!"))
    except Exception as e:
        return redirect(url_for("wiki_page", page_name="log", error_msg=f"Fehler beim Leeren des Logbuchs: {e}"))


@app.route("/static/<path:filename>")
def static_files(filename):
    """Serviert statische Dateien."""
    return flask.send_from_directory(str(PROJECT_ROOT / "static"), filename)


@app.errorhandler(404)
def not_found(e):
    from html import escape as h_escape
    return render_template("page.html", active_page="404",
                           page_title="Seite nicht gefunden",
                           content=f'<h1>404 – Seite nicht gefunden</h1><p>{h_escape(str(e))}</p><p><a href="/">Zur Startseite</a></p>'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("page.html", active_page="500",
                           page_title="Server-Fehler",
                           content="<h1>500 – Interner Server-Fehler</h1><p>Bitte Logs prüfen.</p>"), 500


# ═══════════════════════════════════════════════════════════════════════════════
# Main / CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    global DEFAULT_LANG
    import argparse
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} {APP_EDITION} – Lokaler Wiki-Webserver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  python3 llmWiki.py                       # Port 8080, Sprache aus config.json\n"
            "  python3 llmWiki.py --port 9090            # Anderer Port\n"
            "  python3 llmWiki.py -p 9090 -d             # Debug + Port 9090\n"
            "  python3 llmWiki.py --lang en              # Englisch als Startsprache\n"
            "  python3 llmWiki.py --lang de -H 127.0.0.1 # Deutsch, nur localhost\n"
        ),
    )
    parser.add_argument("--port", "-p", type=int, default=8080, help="Port (Standard: 8080)")
    parser.add_argument("--host", "-H", default="0.0.0.0", help="Host (Standard: 0.0.0.0)")
    parser.add_argument("--debug", "-d", action="store_true", help="Debug-Modus (Flask, kein Uvicorn)")
    parser.add_argument("--lang", "-l", default=None, help="Startsprache (z. B. de, en) – überschreibt config.json")
    args = parser.parse_args()

    # Sprache ermitteln: CLI-Argument überschreibt config.json
    cfg = load_app_config()
    if args.lang:
        DEFAULT_LANG = args.lang
    elif cfg.get("language"):
        DEFAULT_LANG = cfg["language"]

    available = get_available_languages()
    if DEFAULT_LANG not in available:
        print(f"  ⚠ Sprache '{DEFAULT_LANG}' nicht in lang/ gefunden, Fallback auf Deutsch.")
        DEFAULT_LANG = "de"

    print(f"\n{'='*60}")
    print(f"  {APP_NAME}")
    print(f"  {APP_EDITION}")
    print(f"  Version {APP_VERSION}")
    print(f"{'='*60}")
    print(f"  Wiki-Verzeichnis:  {WIKI_DIR}")
    print(f"  Rohquellen:        {RAW_DIR}")
    print(f"  Startsprache:      {DEFAULT_LANG} ({available.get(DEFAULT_LANG, DEFAULT_LANG)})")
    if args.debug:
        print(f"  Betriebsmodus:     Entwicklung (Flask-Debug)")
        print(f"  Server startet     http://{args.host}:{args.port}")
        print(f"  Drücke Strg+C zum Beenden")
        print(f"{'='*60}\n")
        app.run(host=args.host, port=args.port, debug=True)
    else:
        print(f"  Betriebsmodus:     Produktion (Uvicorn ASGI-Standard)")
        print(f"  Server startet     http://{args.host}:{args.port}")
        print(f"  Drücke Strg+C zum Beenden")
        print(f"{'='*60}\n")
        from asgiref.wsgi import WsgiToAsgi
        import uvicorn
        asgi_app = WsgiToAsgi(app)
        uvicorn.run(asgi_app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
