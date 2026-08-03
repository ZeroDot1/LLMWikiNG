# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Zentrales Fehler-Logging – data/error.log.

Erfasst jeden Fehler app-weit:

- unbehandelte HTTP-Exceptions (500er) über ``append_error``,
- asyncio-Task-Ausnahmen über einen Event-Loop-Exception-Handler,
- uncaught Exceptions in Haupt-Thread und Neben-Threads über excepthooks,
- alle ``logging.error``/``logging.exception``-Aufrufe über einen an den
  Root-Logger angehängten File-Handler (Matrix-Indexer, Watcher, Rebuild,
  uvicorn/starlette inkl. Background-Tasks).

Alle Schreibzugriffe sind thread-sicher und werfen nie (der Error-Log darf
niemals selbst einen Fehler verursachen).
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import sys
import threading
import traceback
from pathlib import Path


def log_path() -> Path:
    """data/error.log – lazy aus core.config auflösen (Tests patchen DATA_DIR)."""
    from core.config import DATA_DIR

    return DATA_DIR / "error.log"


_lock = threading.Lock()


def append_error(
    component: str,
    message: str,
    exc: BaseException | None = None,
    request=None,
    extra: str = "",
) -> None:
    """Hängt einen strukturierten Fehlereintrag an data/error.log an.

    Args:
        component: Herkunft des Fehlers (z. B. "http", "sync", "matrix").
        message: Kurze Fehlerbeschreibung.
        exc: Optional die ausgelöste Exception (mit Traceback).
        request: Optional der betroffene Request (Method, URL, Client-IP).
        extra: Optional zusätzlicher Kontext als Freitext.
    """
    try:
        lines = [
            f"=================== {datetime.datetime.now()} ===================",
            f"Komponente: {component}",
            f"Nachricht: {message}",
        ]
        if request is not None:
            ip = getattr(request, "client", None)
            ip = ip.host if ip else "-"
            lines.append(
                f"Request: {getattr(request, 'method', '')} "
                f"{getattr(request, 'url', '')} (IP {ip})"
            )
        if exc is not None:
            lines.append("Traceback:")
            lines.append(
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()
            )
        if extra:
            lines.append(f"Kontext: {extra}")
        lines.append("-" * 50)
        payload = "\n".join(lines) + "\n"
        with _lock:
            with open(log_path(), "a", encoding="utf-8") as fh:
                fh.write(payload)
    except Exception:
        try:
            print("[ERRORLOG] Fehler beim Schreiben des Error-Logs", flush=True)
        except Exception:
            pass


class _ErrorLogHandler(logging.Handler):
    """Leitet ``logging.error``/``logging.exception`` an data/error.log weiter."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = record.getMessage()
            with _lock:
                with open(log_path(), "a", encoding="utf-8") as fh:
                    fh.write(
                        f"{datetime.datetime.now()} [{record.levelname}] "
                        f"{record.name}: {text}\n"
                    )
                    if record.exc_info and record.exc_info[0] is not None:
                        fh.write(
                            "".join(traceback.format_exception(*record.exc_info)).rstrip() + "\n"
                        )
                    fh.write("-" * 50 + "\n")
        except Exception:
            pass


_installed_handler: logging.Handler | None = None


def install_file_handler(level: int = logging.ERROR) -> logging.Handler | None:
    """Hängt einen File-Handler an den Root-Logger (idempotent).

    Erfasst damit auch Logger, die nur ``log.error``/``log.exception`` rufen
    (Matrix-Indexer, Watcher, Rebuild, uvicorn, starlette Background-Tasks).
    """
    global _installed_handler
    if _installed_handler is not None:
        return _installed_handler
    try:
        handler = _ErrorLogHandler(level=level)
        logging.getLogger().addHandler(handler)
        _installed_handler = handler
        return handler
    except Exception:
        return None


_orig_sys_excepthook = None
_orig_thread_excepthook = None


def install_global_hooks(loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Installiert Exception-Hooks für asyncio-Tasks, Haupt-Thread und Neben-Threads."""
    # --- asyncio: uncaught Exceptions in Tasks / Background-Tasks ---
    def _loop_exc_handler(loop_: asyncio.AbstractEventLoop, context: dict) -> None:
        try:
            exc = context.get("exception")
            append_error(
                "asyncio",
                context.get("message", "Unbehandelte asyncio-Exception"),
                exc=exc,
                extra=str(context.get("future") or context.get("task") or ""),
            )
        except Exception:
            pass
        try:
            loop_.default_exception_handler(context)
        except Exception:
            pass

    try:
        loop = loop or asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        try:
            loop.set_exception_handler(_loop_exc_handler)
        except Exception:
            pass

    # --- Haupt-Thread: uncaught Exceptions ---
    global _orig_sys_excepthook
    if _orig_sys_excepthook is None:
        _orig_sys_excepthook = sys.excepthook

        def _sys_excepthook(exc_type, exc_value, exc_tb) -> None:
            try:
                with _lock:
                    with open(log_path(), "a", encoding="utf-8") as fh:
                        fh.write(
                            f"=================== {datetime.datetime.now()} ===================\n"
                            "Komponente: sys.excepthook\n"
                            "Nachricht: Uncaught Exception im Haupt-Thread\n"
                            + "".join(traceback.format_exception(exc_type, exc_value, exc_tb)).rstrip()
                            + "\n" + "-" * 50 + "\n"
                        )
            except Exception:
                pass
            if _orig_sys_excepthook is not None:
                _orig_sys_excepthook(exc_type, exc_value, exc_tb)

        sys.excepthook = _sys_excepthook

    # --- Neben-Threads: uncaught Exceptions ---
    global _orig_thread_excepthook
    if _orig_thread_excepthook is None:
        _orig_thread_excepthook = threading.excepthook

        def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
            try:
                append_error(
                    "thread",
                    "Uncaught Exception in Thread",
                    exc=args.exc_value,
                    extra=f"Thread: {args.thread.name if args.thread else '-'}",
                )
            except Exception:
                pass
            if _orig_thread_excepthook is not None:
                _orig_thread_excepthook(args)

        threading.excepthook = _thread_excepthook
