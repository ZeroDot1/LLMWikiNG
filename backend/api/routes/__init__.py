# backend/api/routes/__init__.py
"""Routen-Paket für LLMWikiNG (FastAPI)."""

from api.routes.pages import router
from api.routes.auth import router as auth_router
from api.routes.api import router as api_router

__all__ = ["router", "auth_router", "api_router"]
