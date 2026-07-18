"""LLMWikiNG – Zentrale Konfiguration, Pfade und Übersetzungssystem.

Port von llmWiki.py auf FastAPI. Diese Module stellt projektweite Konstanten,
das Laden der config.json, das Sprachensystem und die Übersetzungsfunktion
bereit, die in allen Templates und Routen genutzt werden.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Basis-Pfad: example.com/LLMWikiNG/wiki/<Name>/
BASE_PATH = os.getenv("LLMWIKI_BASE_PATH", "/LLMWikiNG").rstrip("/")  # -> "/LLMWikiNG"

# Multi-Wiki-Speicher
WIKIS_ROOT = PROJECT_ROOT / "wikis"
LEGACY_WIKI_DIR = PROJECT_ROOT / "wiki"
WIKI_DIR = WIKIS_ROOT / "main"  # Standard-Wiki (legacy wiki/ wird hierher migriert)

RAW_DIR = PROJECT_ROOT / "raw"
EXPORT_DIR = PROJECT_ROOT / "output_docs"
LANG_DIR = PROJECT_ROOT / "lang"
SCRATCH_DIR = PROJECT_ROOT / "scratch"
CONFIG_FILE = PROJECT_ROOT / "config.json"
DATA_DIR = PROJECT_ROOT / "data"

QMD_BIN = "qmd"
APP_NAME = "LLMWikiNG"
APP_EDITION = "by ZeroDot1"
APP_VERSION = "2.3.0"
DEFAULT_LANG = "en"  # Kann via config.json oder --lang CLI überschrieben werden

# Zur Laufzeit durch run.py gesetzt (CLI --lang / config.json)
_current_lang = {"value": DEFAULT_LANG}


def slugify_wiki(name: str) -> str:
    """Wiki-Namen sicher machen: nur [a-z0-9-]."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "main"


def wiki_path(name: str = "main") -> Path:
    """Liefert (und erstellt) das Verzeichnis eines Wikis."""
    p = WIKIS_ROOT / slugify_wiki(name)
    p.mkdir(parents=True, exist_ok=True)
    return p


def migrate_legacy_wiki() -> None:
    """Beim Start: wiki/ -> wikis/main/ (Daten bleiben erhalten)."""
    if WIKIS_ROOT.exists() and any(WIKIS_ROOT.iterdir()):
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if LEGACY_WIKI_DIR.exists() and any(LEGACY_WIKI_DIR.iterdir()):
        WIKIS_ROOT.mkdir(parents=True, exist_ok=True)
        LEGACY_WIKI_DIR.rename(WIKIS_ROOT / "main")


def list_wikis() -> list[dict]:
    """Listet alle vorhandenen Wikis mit Metadaten."""
    wikis: list[dict] = []
    if WIKIS_ROOT.exists():
        for d in sorted(WIKIS_ROOT.iterdir()):
            if d.is_dir():
                meta = d / "wiki.json"
                name = d.name
                display = name
                desc = ""
                if meta.exists():
                    try:
                        data = json.loads(meta.read_text(encoding="utf-8"))
                        display = data.get("name", name)
                        desc = data.get("description", "")
                    except Exception:
                        pass
                page_count = sum(
                    1 for _ in d.rglob("*.md")
                    if _.stem not in ("index", "log", "ingestlater")
                )
                wikis.append({
                    "slug": name,
                    "name": display,
                    "description": desc,
                    "page_count": page_count,
                })
    return wikis


def save_wiki_meta(name: str, display_name: str, description: str = "") -> None:
    """Speichert Anzeigename/Beschreibung eines Wikis."""
    meta = wiki_path(name) / "wiki.json"
    meta.write_text(
        json.dumps({"name": display_name, "description": description}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def set_default_lang(lang: str) -> None:
    _current_lang["value"] = lang


def get_default_lang() -> str:
    return _current_lang["value"]


# ═══════════════════════════════════════════════════════════════════════════════
# App-Konfiguration (config.json)
# ═══════════════════════════════════════════════════════════════════════════════

def load_app_config() -> dict[str, Any]:
    """Lädt die globale App-Konfiguration aus config.json (inkl. SMTP + Sprache)."""
    default_config = {
        "language": "en",
        "theme": "dark",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_pass": "",
        "use_tls": True,
        "recipients": "",
        "registration_enabled": True,
        "audit_enabled": True,
        "audit_disabled_categories": [],
        "ollama_host": "http://localhost:11434",
        "ollama_model": "llama3.2:3b",

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


def save_app_config(config_dict: dict[str, Any]) -> bool:
    """Speichert App-Konfigurationsparameter in config.json."""
    try:
        current = load_app_config()
        current.update(config_dict)
        CONFIG_FILE.write_text(
            json.dumps(current, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Übersetzungssystem (Mehrsprachigkeit)
# ═══════════════════════════════════════════════════════════════════════════════

_translations_cache: dict[str, dict] = {}


def get_available_languages() -> dict[str, str]:
    """Ermittelt verfügbare Sprachen aus dem lang/-Ordner."""
    langs: dict[str, str] = {}
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


def load_translations(lang_code: str) -> dict:
    """Lädt die Übersetzungsdatei für eine Sprache und gibt ein dict zurück."""
    if lang_code in _translations_cache:
        return _translations_cache[lang_code]
    filepath = LANG_DIR / f"{lang_code}.json"
    if filepath.exists():
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            _translations_cache[lang_code] = data
            return data
        except (json.JSONDecodeError, Exception):
            pass
    if lang_code != DEFAULT_LANG:
        return load_translations(DEFAULT_LANG)
    return {}


class Translator:
    """Einfacher Übersetzer mit Punkt-Notation (z.B. 'sidebar.home').

    Usage in Templates: {{ _('sidebar.home') }} oder {{ _('index.welcome_heading') }}
    """

    def __init__(self, lang_code: str):
        self.lang_code = lang_code
        self.data = load_translations(lang_code)

    def get(self, key: str | None, default: Any = None) -> Any:
        if not key:
            return default or key
        parts = key.split(".")
        current: Any = self.data
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

    def __call__(self, key: str | None, **kwargs: Any) -> Any:
        value = self.get(key)
        if kwargs and isinstance(value, str):
            try:
                return value.format(**kwargs)
            except (KeyError, ValueError):
                return value
        return value


def resolve_lang(request_lang: str | None = None, cookie_lang: str | None = None) -> str:
    """Ermittelt die aktive Sprache (Query > Cookie > config.json > DEFAULT)."""
    cfg = load_app_config()
    if request_lang and request_lang in get_available_languages():
        return request_lang
    if cookie_lang and cookie_lang in get_available_languages():
        return cookie_lang
    return cfg.get("language") or get_default_lang() or DEFAULT_LANG
