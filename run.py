#!/usr/bin/env python3
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
