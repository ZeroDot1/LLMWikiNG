"""LLMWikiNG – Audit-Logging Service (SQLite-basiert).

Protokolliert alle sicherheitsrelevanten Aktionen (Logins, API-Zugriffe, Wiki-Änderungen, etc.)
inklusive IPv4/IPv6-Adressen und Metadaten.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from fastapi import Request
from core.config import DATA_DIR

AUDIT_DB = DATA_DIR / "audit_log.db"


def init_db():
    """Initialisiert die SQLite-Datenbank für Audit-Logs."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUDIT_DB)
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_logs(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_action ON audit_logs(action)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON audit_logs(username)")
    conn.commit()
    conn.close()


def log_action(
    action: str,
    details: str | None = None,
    user_id: str | None = None,
    username: str | None = None,
    request: Request | None = None,
):
    """Protokolliert eine Aktion in der Datenbank."""
    try:
        init_db()  # Sicherstellen, dass DB existiert
        
        # IP-Adresse ermitteln
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

        # Fallback für aktuellen Benutzer aus Session/State falls nicht übergeben
        # (Kann im Aufrufer übergeben werden)
        
        conn = sqlite3.connect(AUDIT_DB)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_logs (timestamp, user_id, username, action, details, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                datetime.now().isoformat(timespec="seconds"),
                user_id,
                username,
                action,
                details,
                ip_address,
                user_agent,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        # Fehler beim Logging dürfen die Hauptanwendung nicht blockieren
        print(f"[AUDIT ERROR] {e}")


def get_logs(
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    username: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[dict], int]:
    """Ruft Audit-Logs mit Filtern und Pagination ab."""
    try:
        init_db()
        conn = sqlite3.connect(AUDIT_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM audit_logs WHERE 1=1"
        count_query = "SELECT COUNT(*) FROM audit_logs WHERE 1=1"
        params = []

        if action:
            query += " AND action LIKE ?"
            count_query += " AND action LIKE ?"
            params.append(f"%{action}%")
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

        # Gesamtanzahl holen
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        # Paginierte Ergebnisse
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        cursor.execute(query, params + [limit, offset])
        rows = cursor.fetchall()
        
        logs = [dict(r) for r in rows]
        conn.close()
        return logs, total
    except Exception as e:
        print(f"[AUDIT ERROR] {e}")
        return [], 0


def prune_logs(year: int, month: int | None = None) -> int:
    """Löscht Logs vor oder in einem bestimmten Jahr/Monat."""
    try:
        init_db()
        conn = sqlite3.connect(AUDIT_DB)
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
        conn.close()
        return deleted
    except Exception as e:
        print(f"[AUDIT ERROR] {e}")
        return 0
