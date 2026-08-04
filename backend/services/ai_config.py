# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Konfiguration der AI-Integration (Ollama + lokale Agent-Tools).

Gespeichert in einer eigenen Datei `ai.config.json`:
- Docker-Betrieb:  `<data>/ai.config.json`
- Normaler Betrieb: `<Projektwurzel>/ai.config.json`

Die Pfade zu opencode / hermes / agy werden mit shutil.which() aufgelöst
(Arch-Linux-Standard: /usr/bin/…) – im Docker-Container sind diese Tools
in der Regel nicht verfügbar, dort bleiben die Pfade leer.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from core.config import DATA_DIR, PROJECT_ROOT

AI_CONFIG_FILENAME = "ai.config.json"

DEFAULT_OLLAMA_MODEL = "llama3.2:3b"


def in_docker() -> bool:
    """Erkennt den Betrieb innerhalb eines Docker-Containers."""
    if os.getenv("LLMWIKI_DOCKER", "").strip() == "1":
        return True
    try:
        return Path("/.dockerenv").exists()
    except Exception:
        return False


def ai_config_path() -> Path:
    """Pfad der AI-Konfigurationsdatei (Docker: data/, sonst Projektwurzel)."""
    if in_docker():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DATA_DIR / AI_CONFIG_FILENAME
    return PROJECT_ROOT / AI_CONFIG_FILENAME


def _resolve_tool_path(name: str, fallback: str) -> str:
    """Auflösung eines Tool-Pfads; im Docker-Betrieb bleibt er leer."""
    if in_docker():
        return ""
    found = shutil.which(name)
    return found or fallback


def default_ai_config() -> dict:
    """Standardwerte für Arch-Linux-Systeme (ohne Docker)."""
    return {
        "ollama_host": "127.0.0.1",
        "ollama_port": 11434,
        "ollama_username": "",
        "ollama_password": "",
        "ollama_model": DEFAULT_OLLAMA_MODEL,
        "opencode_path": _resolve_tool_path("opencode", "/usr/bin/opencode"),
        "hermes_path": _resolve_tool_path("hermes", "/usr/bin/hermes"),
        "agy_path": _resolve_tool_path("agy", "/usr/bin/agy"),
        "tools_available_in_docker": False,
    }


def load_ai_config() -> dict:
    """Lädt die AI-Konfiguration; fehlende Schlüssel werden mit Defaults ergänzt."""
    cfg = default_ai_config()
    path = ai_config_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in cfg.items():
                if k not in saved:
                    saved[k] = v
            cfg = saved
        except Exception:
            pass
    return cfg


def save_ai_config(updates: dict) -> bool:
    """Speichert die AI-Konfiguration (nur bekannte Schlüssel)."""
    try:
        from core.config import _atomic_write
        current = load_ai_config()
        known = {k: v for k, v in updates.items() if k in current}
        current.update(known)
        path = ai_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps(current, indent=2, ensure_ascii=False))
        return True
    except Exception:
        return False
