# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Audit-Logging Service (SQLite-basiert).

Protokolliert alle sicherheitsrelevanten Aktionen (Logins, API-Zugriffe, Wiki-Änderungen, etc.)
inklusive IPv4/IPv6-Adressen und Metadaten.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from starlette.requests import Request
from core.config import DATA_DIR, load_app_config

AUDIT_DB = DATA_DIR / "audit_log.db"

ALL_CATEGORIES = sorted(["auth", "users", "api_keys", "pages", "wikis", "search", "ingest", "system", "audit", "mcp", "matrix", "tailscale"])

ACTION_CATEGORIES = {
    # auth
    "login": "auth",
    "login_success": "auth",
    "login_failed": "auth",
    "logout": "auth",
    "setup_admin": "auth",
    
    # users
    "user_create": "users",
    "user_edit": "users",
    "user_delete": "users",
    "user_change_password": "users",
    
    # api_keys
    "api_key_create": "api_keys",
    "api_key_delete": "api_keys",
    "api_key_reveal": "api_keys",
    "system_secret_reveal": "api_keys",
    "system_secret_regenerate": "api_keys",
    "mcp_key_create": "api_keys",
    "mcp_key_delete": "api_keys",
    "mcp_key_reveal": "api_keys",
    
    # pages
    "page_create": "pages",
    "page_save": "pages",
    "page_delete": "pages",
    "page_export": "pages",
    "page_upload": "pages",
    
    # wikis
    "wiki_create": "wikis",
    "wiki_sync": "wikis",
    "wiki_delete": "wikis",
    "activity_log_clear": "wikis",
    "api_ingest_upload": "wikis",
    
    # search
    "search": "search",

    # matrix
    "matrix_search": "search",
    "matrix_ingest": "matrix",
    "matrix_bulk_ingest": "matrix",
    "matrix_document_delete": "matrix",
    "matrix_rebuild": "matrix",
    "matrix_prune": "matrix",
    "matrix_sync": "matrix",

    # ingest
    "ingest": "ingest",
    "ingest_save_later": "ingest",
    
    # system
    "settings_change": "system",
    "theme_change": "system",
    "system_startup": "system",
    "system_shutdown": "system",
    
    # audit
    "audit_prune": "audit",
    "audit_export": "audit",

    # mcp
    "mcp_tool_call": "mcp",
    "mcp_write_concept": "mcp",
    "mcp_delete_page": "mcp",
    "mcp_create_wiki": "mcp",
    "mcp_delete_wiki": "mcp",
    "mcp_sync": "mcp",
    "mcp_update": "mcp",
    "mcp_clear_cache": "mcp",
    "mcp_create_backup": "mcp",
    "mcp_restore_backup": "mcp",

    # tailscale
    "tailscale_setup": "tailscale",
    "tailscale_save": "tailscale",
    "tailscale_up": "tailscale",
    "tailscale_down": "tailscale",
    "tailscale_apply": "tailscale",
    "tailscale_reset": "tailscale",
    "tailscale_restart": "tailscale",
    "tailscale_reveal": "tailscale",
}

_db_initialized: bool = False


def is_audit_enabled(action: str) -> bool:
    """Prüft, ob Logging generell und für die spezifische Kategorie aktiviert ist."""
    config = load_app_config()
    
    if not config.get("audit_enabled", True):
        return False
        
    category = ACTION_CATEGORIES.get(action, "system")
    disabled_categories = config.get("audit_disabled_categories", [])
    
    if category in disabled_categories:
        return False
        
    return True

def init_db():
    """Initialisiert die SQLite-Datenbank für Audit-Logs und führt ggf. Migrationen durch."""
    global _db_initialized
    if _db_initialized:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(AUDIT_DB) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id TEXT,
                username TEXT,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT
            )
        """)

        # Migration: category column
        cursor.execute("PRAGMA table_info(audit_logs)")
        columns = [col[1] for col in cursor.fetchall()]
        if "category" not in columns:
            cursor.execute("ALTER TABLE audit_logs ADD COLUMN category TEXT DEFAULT 'system'")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_action ON audit_logs(action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON audit_logs(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_category ON audit_logs(category)")
    _db_initialized = True


def log_action(
    action: str,
    details: str | None = None,
    user_id: str | None = None,
    username: str | None = None,
    request: Request | None = None,
):
    """Protokolliert eine Aktion in der Datenbank, falls sie nicht deaktiviert ist."""
    if not is_audit_enabled(action):
        return
        
    category = ACTION_CATEGORIES.get(action, "system")

    try:
        init_db()  # Sicherstellen, dass DB existiert
        
        ip_address = "unknown"
        user_agent = None
        if request:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                ip_address = forwarded.split(",")[0].strip()
            else:
                real_ip = request.headers.get("x-real-ip")
                if real_ip:
                    ip_address = real_ip
                elif request.client:
                    ip_address = request.client.host
            user_agent = request.headers.get("user-agent")

        conn = sqlite3.connect(AUDIT_DB)
        conn.execute("PRAGMA journal_mode=WAL;")
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_logs (timestamp, user_id, username, action, details, ip_address, user_agent, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    datetime.now().isoformat(timespec="seconds"),
                    user_id,
                    username,
                    action,
                    details,
                    ip_address,
                    user_agent,
                    category
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        # Fehler beim Logging dürfen die Hauptanwendung nicht blockieren
        print(f"[AUDIT ERROR] {e}")
        try:
            from services.errorlog import append_error
            append_error("audit", f"Audit-Eintrag fehlgeschlagen (action={action})", exc=e)
        except Exception:
            pass


def get_logs(
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    category: str | None = None,
    username: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    """Ruft Audit-Logs mit Filtern und Pagination ab."""
    try:
        init_db()
        conn = sqlite3.connect(AUDIT_DB)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            query = "SELECT * FROM audit_logs WHERE 1=1"
            count_query = "SELECT COUNT(*) FROM audit_logs WHERE 1=1"
            params = []

            if action:
                query += " AND action LIKE ?"
                count_query += " AND action LIKE ?"
                params.append(f"%{action}%")
            if category:
                query += " AND category = ?"
                count_query += " AND category = ?"
                params.append(category)
            if username:
                query += " AND username = ?"
                count_query += " AND username = ?"
                params.append(username)
            if start_date:
                query += " AND timestamp >= ?"
                count_query += " AND timestamp >= ?"
                params.append(start_date)
            if end_date:
                query += " AND timestamp <= ?"
                count_query += " AND timestamp <= ?"
                params.append(end_date)

            if search:
                search_term = f"%{search}%"
                search_clause = " AND (details LIKE ? OR username LIKE ? OR action LIKE ? OR ip_address LIKE ?)"
                query += search_clause
                count_query += search_clause
                params.extend([search_term, search_term, search_term, search_term])

            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            cursor.execute(query, params + [limit, offset])
            rows = cursor.fetchall()

            logs = [dict(r) for r in rows]
            return logs, total
        finally:
            conn.close()
    except Exception as e:
        print(f"[AUDIT ERROR] {e}")
        return [], 0


def get_all_logs(
    action: str | None = None,
    category: str | None = None,
    username: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """Ruft ALLE passenden Audit-Logs ohne Limit ab (fuer Export)."""
    try:
        init_db()
        conn = sqlite3.connect(AUDIT_DB)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            query = "SELECT * FROM audit_logs WHERE 1=1"
            params = []

            if action:
                query += " AND action LIKE ?"
                params.append(f"%{action}%")
            if category:
                query += " AND category = ?"
                params.append(category)
            if username:
                query += " AND username = ?"
                params.append(username)
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            if search:
                search_term = f"%{search}%"
                query += " AND (details LIKE ? OR username LIKE ? OR action LIKE ? OR ip_address LIKE ?)"
                params.extend([search_term, search_term, search_term, search_term])

            query += " ORDER BY timestamp DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            logs = [dict(r) for r in rows]
            return logs
        finally:
            conn.close()
    except Exception as e:
        print(f"[AUDIT ERROR] {e}")
        return []


def get_recent_audit_logs(limit: int = 5) -> list[dict]:
    """Gibt die neuesten Log-Einträge für das Dashboard zurück."""
    logs, _ = get_logs(limit=limit)
    return logs


def get_category_stats() -> dict[str, int]:
    """Gibt die Anzahl der Logs pro Kategorie zurück."""
    try:
        init_db()
        with sqlite3.connect(AUDIT_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT category, COUNT(*) FROM audit_logs GROUP BY category")
            rows = cursor.fetchall()
            return {row[0] or "system": row[1] for row in rows}
    except Exception as e:
        print(f"[AUDIT ERROR] {e}")
        return {}


def get_total_count() -> int:
    """Gibt die Gesamtanzahl aller Audit-Logs zurück."""
    try:
        init_db()
        with sqlite3.connect(AUDIT_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM audit_logs")
            total = cursor.fetchone()[0]
            return total
    except Exception as e:
        print(f"[AUDIT ERROR] {e}")
        return 0


def prune_logs(year: int, month: int | None = None) -> int:
    """Löscht Logs vor oder in einem bestimmten Jahr/Monat."""
    try:
        init_db()
        conn = sqlite3.connect(AUDIT_DB)
        try:
            cursor = conn.cursor()

            if month:
                # Löscht alles vor dem Ende des angegebenen Monats (z. B. vor YYYY-MM-31T23:59:59)
                target = f"{year}-{month:02d}-31T23:59:59"
            else:
                # Löscht alles vor dem angegebenen Jahr
                target = f"{year}-01-01T00:00:00"

            cursor.execute("DELETE FROM audit_logs WHERE timestamp < ?", (target,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        finally:
            conn.close()
    except Exception as e:
        print(f"[AUDIT ERROR] {e}")
        return 0


def export_logs_csv(logs: list[dict]) -> str:
    """Konvertiert eine Liste von Audit-Logs in ein CSV-Format."""
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Timestamp", "User ID", "Username", "Category", "Action", "Details", "IP Address", "User Agent"])
    for log in logs:
        writer.writerow([
            log.get("id"),
            log.get("timestamp"),
            log.get("user_id") or "",
            log.get("username") or "",
            log.get("category") or "",
            log.get("action"),
            log.get("details") or "",
            log.get("ip_address") or "",
            log.get("user_agent") or "",
        ])
    return output.getvalue()
