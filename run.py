#!/usr/bin/env python3
# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMWikiNG – Einstiegspunkt.

Stellt sicher, dass das backend/-Paket auf dem Python-Pfad steht und startet
die FastAPI-Anwendung (uvicorn).
"""

import sys
from pathlib import Path

BACKEND_DIR = str(Path(__file__).resolve().parent / "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from main import main

if __name__ == "__main__":
    main()
