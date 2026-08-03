# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Routen-Paket für LLMWikiNG (FastAPI)."""

from api.routes.pages import router
from api.routes.auth import router as auth_router
from api.routes.api import router as api_router

__all__ = ["router", "auth_router", "api_router"]
